"""Точка входа: запускает бота в режиме long polling и фоновые задачи."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand, ErrorEvent

from bot.config import load_config
from bot.db import Database
from bot.handlers import ALL_ROUTERS
from bot.middlewares import ThrottlingMiddleware, UserMiddleware
from bot.scheduler import scheduler_loop
from bot.storage import create_backend

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать и принять правила"),
    BotCommand(command="menu", description="Меню"),
    BotCommand(command="rules", description="Правила биржи"),
    BotCommand(command="help", description="Как пользоваться"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config()
    if not config.bot_token:
        raise SystemExit(
            "BOT_TOKEN не задан. Открой файл .env в папке проекта и вставь токен от @BotFather."
        )
    if not config.admin_ids:
        logger.warning(
            "ADMIN_IDS пуст: очередь модерации, жалобы и админ-панель будут недоступны никому."
        )

    db = Database(backend=create_backend(config))
    await db.connect()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(ThrottlingMiddleware())
    dp.message.middleware(UserMiddleware(db))
    dp.callback_query.middleware(UserMiddleware(db))

    for router in ALL_ROUTERS:
        dp.include_router(router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("Ошибка при обработке апдейта: %s", event.exception)
        return True

    try:
        await bot.set_my_commands(COMMANDS)
    except TelegramUnauthorizedError:
        await db.close()
        await bot.session.close()
        raise SystemExit(
            "Telegram отклонил токен. Проверь BOT_TOKEN в .env: возможно, он скопирован "
            "не полностью или бот удалён в @BotFather."
        ) from None

    background = asyncio.create_task(scheduler_loop(bot, db, config))

    logger.info("Бот запущен. База: %s. Админы: %s", db.describe(), config.admin_ids or "не заданы")
    try:
        await dp.start_polling(bot, config=config)
    finally:
        background.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено.")
