"""Middleware: регистрация пользователя, бан-чек, троттлинг."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.db import Database

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """Пишет пользователя в БД и не пускает забаненных дальше."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return await handler(event, data)

        user = await self.db.upsert_user(from_user.id, from_user.username, from_user.first_name)
        data["user"] = user
        data["db"] = self.db

        if user["is_banned"]:
            if isinstance(event, Message):
                await event.answer("🚫 Доступ к боту заблокирован администратором.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Доступ заблокирован", show_alert=True)
            return None

        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Гасит флуд: не чаще одного события в rate_seconds от пользователя."""

    def __init__(self, rate_seconds: float = 0.7) -> None:
        self.rate_seconds = rate_seconds
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return await handler(event, data)

        now_ts = time.monotonic()
        if now_ts - self._last_seen.get(from_user.id, 0.0) < self.rate_seconds:
            return None
        self._last_seen[from_user.id] = now_ts
        return await handler(event, data)
