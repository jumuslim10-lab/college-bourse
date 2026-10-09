"""Проводка: все роутеры собираются в диспетчер, фильтр админа работает."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from aiogram import Dispatcher

from bot.config import Config
from bot.filters import IsAdmin
from bot.handlers import ALL_ROUTERS


def make_config(*admin_ids: int) -> Config:
    return Config(
        bot_token="123456:TEST",
        admin_ids=tuple(admin_ids),
        db_path=Path("data/test.db"),
        digest_hour=8,
        bootstrap_categories=True,
    )


def test_is_admin_filter():
    filter_ = IsAdmin()
    admin_event = SimpleNamespace(from_user=SimpleNamespace(id=5))
    stranger_event = SimpleNamespace(from_user=SimpleNamespace(id=6))

    assert asyncio.run(filter_(admin_event, config=make_config(5))) is True
    assert asyncio.run(filter_(stranger_event, config=make_config(5))) is False
    assert asyncio.run(filter_(admin_event, config=make_config())) is False


def test_dispatcher_assembles_every_router():
    import run  # noqa: F401 — проверяем, что точка входа импортируется без ошибок

    dp = Dispatcher()
    for router in ALL_ROUTERS:
        dp.include_router(router)

    handlers = len(dp.message.handlers) + len(dp.callback_query.handlers)
    handlers += sum(
        len(router.message.handlers) + len(router.callback_query.handlers) for router in ALL_ROUTERS
    )

    assert len(ALL_ROUTERS) == 7
    assert handlers >= 25


class CountingDb:
    """Заглушка базы: считает, сколько раз её дёрнули."""

    def __init__(self) -> None:
        self.calls = 0

    async def upsert_user(self, tg_id: int, username: str | None, first_name: str | None):
        self.calls += 1
        return {"id": tg_id, "tg_id": tg_id, "username": username, "is_banned": 0}


def test_user_middleware_caches_the_row():
    """Повторные нажатия одного студента не ходят в базу за одной и той же строкой."""
    from bot.middlewares import UserMiddleware

    async def scenario():
        db = CountingDb()
        middleware = UserMiddleware(db, cache_seconds=60)  # type: ignore[arg-type]
        person = SimpleNamespace(id=7, username="student", first_name="Студент")

        first = await middleware._user(person)
        second = await middleware._user(person)

        assert first is second
        assert db.calls == 1

        # после истечения кеша строка перечитывается
        middleware.cache_seconds = 0
        await middleware._user(person)
        assert db.calls == 2

    asyncio.run(scenario())
