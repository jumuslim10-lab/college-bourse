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


async def make_listing(
    db: Database,
    user,
    *,
    kind: str = "sell",
    category_code: str = "services",
    title: str = "Печать курсовой",
    description: str = "Напечатаю и сброшу на флешку, свой принтер",
    price: int | None = 100,
    is_negotiable: bool = False,
    status: str = "active",
):
    listing_id = await db.create_listing(
        author_id=user["id"],
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
