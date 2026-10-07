"""Отправка служебных сообщений администраторам."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot.config import Config

logger = logging.getLogger(__name__)


async def notify_user(bot: Bot, tg_id: int, text: str, reply_markup=None) -> bool:
    """Шлёт сообщение одному пользователю, не падая на заблокированном боте."""
    try:
        await bot.send_message(tg_id, text, reply_markup=reply_markup)
        return True
    except TelegramAPIError as error:
        logger.info("Пользователю %s не доставлено: %s", tg_id, error)
        return False


async def send_to_admins(
    bot: Bot,
    config: Config,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    photo: str | None = None,
) -> int:
    """Шлёт сообщение всем админам. Возвращает число успешных отправок."""
    sent = 0
    for admin_id in config.admin_ids:
        try:
            if photo:
                await bot.send_photo(admin_id, photo, caption=text, reply_markup=reply_markup)
            else:
                await bot.send_message(admin_id, text, reply_markup=reply_markup)
            sent += 1
        except TelegramAPIError as error:
            logger.warning("Админу %s не доставлено: %s", admin_id, error)
    return sent
