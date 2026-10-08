"""Фоновые задачи: авто-архив объявлений, истечение рекламы, утренний дайджест."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from bot import services
from bot.config import Config
from bot.db import Database

logger = logging.getLogger(__name__)

DIGEST_META_KEY = "last_digest_date"


async def broadcast(
    bot: Bot, db: Database, text: str, days: int = 30, community_id: int | None = None
) -> tuple[int, int]:
    """Рассылает text активным пользователям. Возвращает (доставлено, ошибок)."""
    delivered = failed = 0
    for tg_id in await db.active_user_ids(days, community_id):
        try:
            await bot.send_message(tg_id, text)
            delivered += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
            try:
                await bot.send_message(tg_id, text)
                delivered += 1
            except TelegramAPIError:
                failed += 1
        except TelegramForbiddenError:
            failed += 1
        except TelegramAPIError as error:
            logger.warning("Не доставлено %s: %s", tg_id, error)
            failed += 1
        await asyncio.sleep(0.05)
    return delivered, failed


async def send_digest_if_due(bot: Bot, db: Database, config: Config) -> bool:
    local_now = datetime.now().astimezone()
    today = local_now.date().isoformat()
    if local_now.hour < config.digest_hour:
        return False
    if await db.meta_get(DIGEST_META_KEY) == today:
        return False

    # Дайджест считается отдельно для каждой площадки, чтобы объявления не перетекали
    # между колледжами. Пользователи без площадки получают общий дайджест.
    targets: list[tuple[int | None, str]] = [(None, "все площадки")]
    for community in await db.list_communities_with_counts(active_only=True):
        targets.append((int(community["id"]), str(community["title"])))

    sent_any = False
    for community_id, title in targets:
        digest = await services.build_digest(db, community_id=community_id)
        if not digest:
            continue
        delivered, failed = await broadcast(bot, db, digest, community_id=community_id)
        logger.info("Дайджест «%s»: %s доставлено, %s ошибок", title, delivered, failed)
        sent_any = True

    await db.meta_set(DIGEST_META_KEY, today)
    return sent_any


async def tick(bot: Bot, db: Database, config: Config) -> None:
    archived = await db.archive_expired()
    if archived:
        logger.info("В архив ушло объявлений: %s", archived)
    await db.expire_ads()
    await send_digest_if_due(bot, db, config)


async def scheduler_loop(bot: Bot, db: Database, config: Config, interval: int = 60) -> None:
    while True:
        try:
            await tick(bot, db, config)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка в фоновом цикле")
        await asyncio.sleep(interval)
