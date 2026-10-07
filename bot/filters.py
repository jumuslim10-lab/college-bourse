"""Кастомные фильтры."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.config import Config


class IsAdmin(BaseFilter):
    """Пускает только админов из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject, config: Config) -> bool:
        from_user = getattr(event, "from_user", None)
        return from_user is not None and from_user.id in config.admin_ids
