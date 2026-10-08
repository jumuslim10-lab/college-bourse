"""Тесты слоя хранения: паритет схем и диалект-нейтральность SQL."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bot.config import BASE_DIR, Config
from bot.storage import PostgresBackend, SqliteBackend, create_backend

SQLITE_SCHEMA = BASE_DIR / "schema.sql"
POSTGRES_SCHEMA = BASE_DIR / "schema_postgres.sql"

CREATE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", re.DOTALL)
COLUMN_RE = re.compile(r"^ {4}(\w+)\s", re.MULTILINE)

# Конструкции, которые есть только в SQLite: попав в SQL внутри bot/db.py, они сломают Postgres.
# Регулярки, а не подстроки: слово «PRAGMA» встречается в комментариях и это нормально.
FORBIDDEN_PATTERNS = (
    r"INSERT\s+OR\s+IGNORE",
    r"AUTOINCREMENT",
    r"PRAGMA\s+\w+\s*\(",
    r"sqlite_master",
    r"lastrowid",
    r"cursor\.rowcount",
    r"executescript",
)


def _tables(schema_path: Path) -> dict[str, set[str]]:
    text = schema_path.read_text(encoding="utf-8")
    return {name: set(COLUMN_RE.findall(body)) for name, body in CREATE_RE.findall(text)}


def test_both_schemas_define_same_tables_and_columns():
    sqlite_tables = _tables(SQLITE_SCHEMA)
    postgres_tables = _tables(POSTGRES_SCHEMA)

    assert sqlite_tables, "не разобралась схема SQLite — проверь регулярку"
    assert set(sqlite_tables) == set(postgres_tables)
    for table, columns in sqlite_tables.items():
        assert columns, f"в таблице {table} не нашлось колонок"
        assert columns == postgres_tables[table], f"схемы разошлись по таблице {table}"


def test_repository_sql_stays_dialect_neutral():
    source = (BASE_DIR / "bot" / "db.py").read_text(encoding="utf-8")
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, source) is None, (
            f"в bot/db.py появилась конструкция только для SQLite: {pattern}"
        )


def test_postgres_placeholder_translation():
    assert (
        PostgresBackend._translate("SELECT * FROM users WHERE tg_id = ?")
        == "SELECT * FROM users WHERE tg_id = $1"
    )
    assert PostgresBackend._translate("SELECT 1") == "SELECT 1"
    translated = PostgresBackend._translate(
        "WHERE status = 'active' AND (? IS NULL OR community_id = ?) AND search_text LIKE ?"
    )
    assert "(? " not in translated
    assert translated.endswith("search_text LIKE $3")


def test_create_backend_chooses_backend(tmp_path):
    sqlite_config = Config(
        bot_token="t",
        admin_ids=(),
        db_path=tmp_path / "bot.db",
        digest_hour=8,
        bootstrap_categories=True,
    )
    sqlite_backend = create_backend(sqlite_config)
    assert isinstance(sqlite_backend, SqliteBackend)
    assert "SQLite" in sqlite_backend.describe()

    postgres_config = Config(
        bot_token="t",
        admin_ids=(),
        db_path=tmp_path / "bot.db",
        digest_hour=8,
        bootstrap_categories=True,
        db_backend="postgres",
        database_url="postgresql://user:secret@db.example.com:5432/postgres",
    )
    postgres_backend = create_backend(postgres_config)
    assert isinstance(postgres_backend, PostgresBackend)
    assert "Postgres" in postgres_backend.describe()
    assert "secret" not in postgres_backend.describe()  # пароль не попадает в логи


def test_postgres_backend_requires_url(tmp_path):
    config = Config(
        bot_token="t",
        admin_ids=(),
        db_path=tmp_path / "bot.db",
        digest_hour=8,
        bootstrap_categories=True,
        db_backend="postgres",
        database_url="",
    )
    with pytest.raises(SystemExit):
        create_backend(config)
