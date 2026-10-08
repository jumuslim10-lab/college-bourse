"""Хелперы для тестов."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from bot.db import Database


def run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def open_db(tmp_path: Path, name: str = "test.db") -> AsyncIterator[Database]:
    db = Database(Path(tmp_path) / name)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()


async def make_user(db: Database, tg_id: int, username: str = "user", first_name: str = "Юзер"):
    return await db.upsert_user(tg_id, username, first_name)


async def bind_community(db: Database, user, community_id: int | None):
    """Привязывает пользователя к площадке и возвращает уже обновлённую строку."""
    await db.set_user_community(user["id"], community_id)
    refreshed = await db.get_user(user["id"])
    assert refreshed is not None
    return refreshed


UNSET = object()


async def make_listing(
    db: Database,
    user,
    *,
    community_id=UNSET,
    kind: str = "sell",
    category_code: str = "services",
    title: str = "Печать курсовой",
    description: str = "Напечатаю и сброшу на флешку, свой принтер",
    price: int | None = 100,
    is_negotiable: bool = False,
    status: str = "active",
):
    """Объявление привязывается к площадке автора — как в submit_listing."""
    resolved_community = user["community_id"] if community_id is UNSET else community_id
    listing_id = await db.create_listing(
        author_id=user["id"],
        community_id=resolved_community,
        kind=kind,
        category_code=category_code,
        title=title,
        description=description,
        price=price,
        is_negotiable=is_negotiable,
        photo_file_id=None,
        status=status,
    )
    return listing_id
