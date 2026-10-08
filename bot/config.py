"""Конфигурация: читается из .env рядом с корнем проекта."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    return tuple(ids)


def parse_bool(raw: str, default: bool = True) -> bool:
    value = (raw or "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    db_path: Path
    digest_hour: int
    bootstrap_categories: bool
    db_backend: str = "sqlite"
    database_url: str = ""


def load_config() -> Config:
    db_raw = os.getenv("DB_PATH", "").strip()
    digest_raw = os.getenv("DIGEST_HOUR", "").strip()
    backend = os.getenv("DB_BACKEND", "").strip().lower() or "sqlite"
    if backend not in {"sqlite", "postgres"}:
        raise SystemExit(f"DB_BACKEND={backend!r} не поддерживается. Разрешено: sqlite или postgres.")
    return Config(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        db_path=Path(db_raw) if db_raw else BASE_DIR / "data" / "bot.db",
        digest_hour=int(digest_raw) if digest_raw.isdigit() else 8,
        bootstrap_categories=parse_bool(os.getenv("BOOTSTRAP_CATEGORIES", "")),
        db_backend=backend,
        database_url=os.getenv("DATABASE_URL", "").strip(),
    )
