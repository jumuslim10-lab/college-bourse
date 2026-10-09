"""Middleware: регистрация пользователя, бан-чек, троттлинг."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.db import Database

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """Пишет пользователя в БД и не пускает забаненных дальше.

    Строка пользователя кешируется на `cache_seconds`. При облачной базе (~700 мс на запрос)
    это убирает целый круг обращений на каждое нажатие кнопки: студент жмёт каталог → раздел →
    карточку, и все эти шаги не ходят в базу за одним и тем же пользователем.
    Плата: бан и правки профиля применяются с задержкой до минуты.
    """

    def __init__(self, db: Database, cache_seconds: float = 60.0) -> None:
        self.db = db
        self.cache_seconds = cache_seconds
        self._cache: dict[int, tuple[float, Mapping[str, Any]]] = {}
        self._cache_limit = 5000

    async def _user(self, from_user: Any) -> Mapping[str, Any]:
        now_ts = time.monotonic()
        cached = self._cache.get(from_user.id)
        if cached is not None and now_ts - cached[0] < self.cache_seconds:
            return cached[1]

        user = await self.db.upsert_user(from_user.id, from_user.username, from_user.first_name)
        if len(self._cache) > self._cache_limit:
            self._cache.clear()
        self._cache[from_user.id] = (now_ts, user)
        return user

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return await handler(event, data)

        user = await self._user(from_user)
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
