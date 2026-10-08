"""Драйверы БД за одним интерфейсом: SQLite (по умолчанию) и Postgres (Supabase).

Все SQL-запросы проекта живут в `bot/db.py` и пишутся в стиле SQLite — с `?` как плейсхолдером
и без диалектных конструкций. `PostgresBackend` сам переводит `?` в `$1, $2, ...`, поэтому один
и тот же запрос выполняется в обеих базах.

Почему так: у проекта должно быть два режима — локальный и облачный. SQLite работает без интернета
и остаётся аварийным вариантом; Postgres нужен ради сохранности данных, бэкапов и будущего
веб-кабинета. Переключение — одна строка в `.env` (`DB_BACKEND=sqlite|postgres`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import aiosqlite

from bot.config import BASE_DIR, Config

logger = logging.getLogger(__name__)

SQLITE_SCHEMA = "schema.sql"
POSTGRES_SCHEMA = "schema_postgres.sql"
CONNECT_ATTEMPTS = 3
QUERY_ATTEMPTS = 2
ACQUIRE_TIMEOUT = 10.0


class Backend(Protocol):
    """Минимум, который нужен слою данных от конкретной СУБД."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    def describe(self) -> str: ...

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int: ...

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Mapping[str, Any] | None: ...

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Mapping[str, Any]]: ...

    async def insert_id(self, sql: str, params: Sequence[Any] = ()) -> int: ...

    async def column_names(self, table: str) -> set[str]: ...

    async def index_sql(self, name: str) -> str | None: ...


class SqliteBackend:
    """Локальная база: файл рядом с ботом, работает без сети."""

    def __init__(self, path: Path | str, schema_path: Path | None = None) -> None:
        self.path = Path(path)
        self.schema_path = schema_path or BASE_DIR / SQLITE_SCHEMA
        self._conn: aiosqlite.Connection | None = None

    def describe(self) -> str:
        return f"SQLite: {self.path}"

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База не подключена: сначала вызови connect()")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(self.schema_path.read_text(encoding="utf-8"))
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return int(cursor.rowcount or 0)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def insert_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await self.conn.commit()
        return int(row[0]) if row else 0

    async def column_names(self, table: str) -> set[str]:
        rows = await self.fetchall(f"PRAGMA table_info({table})")
        return {str(row["name"]) for row in rows}

    async def index_sql(self, name: str) -> str | None:
        row = await self.fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (name,)
        )
        return None if row is None else str(row["sql"] or "")


class PostgresBackend:
    """Облачная база (Supabase) через asyncpg с пулом соединений."""

    def __init__(
        self,
        dsn: str,
        schema_path: Path | None = None,
        schema: str | None = None,
        drop_schema_on_close: bool = False,
    ) -> None:
        self.dsn = dsn
        self.schema_path = schema_path or BASE_DIR / POSTGRES_SCHEMA
        self.schema = schema
        self.drop_schema_on_close = drop_schema_on_close
        self.pool: Any = None

    def describe(self) -> str:
        target = self.dsn.split("@")[-1] if "@" in self.dsn else "postgres"
        suffix = f" [схема {self.schema}]" if self.schema else ""
        return f"Postgres: {target}{suffix}"

    @staticmethod
    def _asyncpg():
        try:
            import asyncpg
        except ModuleNotFoundError as error:  # pragma: no cover — защита от запуска без зависимости
            raise RuntimeError(
                "Для Postgres нужен пакет asyncpg: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from error
        return asyncpg

    @staticmethod
    def _retryable(asyncpg) -> tuple[type[BaseException], ...]:
        errors: tuple[type[BaseException], ...] = (
            ConnectionError,
            OSError,
            asyncio.TimeoutError,
        )
        for name in (
            "PostgresConnectionError",
            "InterfaceError",
            "CannotConnectNowError",
            "ConnectionDoesNotExistError",
            "TooManyConnectionsError",
        ):
            candidate = getattr(asyncpg, name, None) or getattr(
                getattr(asyncpg, "exceptions", None), name, None
            )
            if isinstance(candidate, type) and issubclass(candidate, BaseException):
                errors += (candidate,)
        return errors

    async def connect(self) -> None:
        asyncpg = self._asyncpg()
        # Транзакционный пулер Supabase (порт 6543) не умеет prepared statements.
        statement_cache = 0 if "pooler.supabase.com" in self.dsn else 100
        server_settings = {"search_path": self.schema} if self.schema else None
        last_error: Exception | None = None

        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            try:
                if self.schema:
                    admin = await asyncpg.connect(self.dsn, timeout=ACQUIRE_TIMEOUT)
                    try:
                        await admin.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                    finally:
                        await admin.close()
                self.pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=1,
                    max_size=5,
                    timeout=ACQUIRE_TIMEOUT,
                    statement_cache_size=statement_cache,
                    server_settings=server_settings,
                )
                async with self.pool.acquire() as conn:
                    await conn.execute(self.schema_path.read_text(encoding="utf-8"))
                logger.info("Postgres подключён: %s", self.describe())
                return
            except Exception as error:  # noqa: BLE001 — нужно пережить «заснувший» бесплатный проект
                last_error = error
                logger.warning(
                    "Postgres: попытка %s из %s не удалась (%s: %s)",
                    attempt,
                    CONNECT_ATTEMPTS,
                    type(error).__name__,
                    error,
                )
                if self.pool is not None:
                    try:
                        await self.pool.close()
                    finally:
                        self.pool = None
                await asyncio.sleep(1.5 * attempt)

        raise RuntimeError(
            f"Не удалось подключиться к Postgres: {last_error}. "
            "Проверь DATABASE_URL и что проект Supabase не на паузе."
        ) from last_error

    async def close(self) -> None:
        if self.pool is None:
            return
        if self.schema and self.drop_schema_on_close:
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            except Exception as error:  # noqa: BLE001
                logger.warning("Не удалось удалить тестовую схему %s: %s", self.schema, error)
        await self.pool.close()
        self.pool = None

    @staticmethod
    def _translate(sql: str) -> str:
        """`?` → `$1, $2, ...`. Кавычек с вопросительными знаками в наших запросах нет."""
        if "?" not in sql:
            return sql
        parts = sql.split("?")
        chunks = [parts[0]]
        for index, part in enumerate(parts[1:], start=1):
            chunks.append(f"${index}")
            chunks.append(part)
        return "".join(chunks)

    async def _run(
        self, action: Callable[[Any], Awaitable[Any]], sql: str, params: Sequence[Any]
    ) -> Any:
        if self.pool is None:
            raise RuntimeError("Postgres не подключён: сначала вызови connect()")
        asyncpg = self._asyncpg()
        retryable = self._retryable(asyncpg)
        last_error: Exception | None = None

        for attempt in range(QUERY_ATTEMPTS):
            try:
                async with self.pool.acquire(timeout=ACQUIRE_TIMEOUT) as conn:
                    return await action(conn)
            except retryable as error:
                last_error = error
                logger.warning(
                    "Postgres: запрос не прошёл (%s: %s), повтор %s/%s",
                    type(error).__name__,
                    error,
                    attempt + 1,
                    QUERY_ATTEMPTS,
                )
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"Postgres недоступен: {last_error}") from last_error

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        async def action(conn: Any) -> int:
            status = str(await conn.execute(self._translate(sql), *params) or "")
            tail = status.split()[-1] if status.split() else "0"
            return int(tail) if tail.isdigit() else 0

        return await self._run(action, sql, params)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return await self._run(
            lambda conn: conn.fetchrow(self._translate(sql), *params), sql, params
        )

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Any]:
        async def action(conn: Any) -> list[Any]:
            return list(await conn.fetch(self._translate(sql), *params))

        return await self._run(action, sql, params)

    async def insert_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        value = await self._run(
            lambda conn: conn.fetchval(self._translate(sql), *params), sql, params
        )
        return int(value or 0)

    async def column_names(self, table: str) -> set[str]:
        rows = await self.fetchall(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
        )
        return {str(row["column_name"]) for row in rows}

    async def index_sql(self, name: str) -> str | None:
        row = await self.fetchone("SELECT indexdef FROM pg_indexes WHERE indexname = ?", (name,))
        return None if row is None else str(row["indexdef"] or "")


def create_backend(config: Config) -> Backend:
    """Выбирает базу по `.env`: sqlite (по умолчанию) или postgres (Supabase)."""
    if config.db_backend == "postgres":
        if not config.database_url:
            raise SystemExit(
                "DB_BACKEND=postgres, но DATABASE_URL пуст. "
                "Вставь строку подключения Supabase в .env (Settings → Database → Connection string)."
            )
        return PostgresBackend(config.database_url)
    return SqliteBackend(config.db_path)
