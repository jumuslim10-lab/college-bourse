"""Слой доступа к данным: подключение к SQLite и репозитории."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from bot.categories import CATEGORIES
from bot.config import BASE_DIR
from bot.validation import normalize


def search_key(title: str, description: str) -> str:
    """Ключ поиска: SQLite LIKE не умеет регистронезависимый поиск по кириллице."""
    return normalize(f"{title} {description}").lower()


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def iso_in_days(days: int) -> str:
    return (now() + timedelta(days=days)).isoformat(timespec="seconds")


def iso_in_hours(hours: int) -> str:
    return (now() + timedelta(hours=hours)).isoformat(timespec="seconds")


def iso_seconds_ago(seconds: int) -> str:
    return (now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def iso_days_ago(days: int) -> str:
    return (now() - timedelta(days=days)).isoformat(timespec="seconds")


CARD_COLUMNS = """
    l.*, u.username AS username, u.first_name AS first_name,
    u.tg_id AS author_tg_id,
    u.rating_sum AS rating_sum, u.rating_count AS rating_count,
    u.is_banned AS author_banned
"""


class Database:
    def __init__(self, path: Path | str, schema_path: Path | None = None) -> None:
        self.path = Path(path)
        self.schema_path = schema_path or BASE_DIR / "schema.sql"
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База не подключена: сначала вызови Database.connect()")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(self.schema_path.read_text(encoding="utf-8"))
        await self._conn.commit()
        await self.migrate()
        await self.seed_categories()

    async def migrate(self) -> None:
        """Догоняющие миграции для баз, созданных более ранними версиями."""
        # Миграция 1: search_text
        async with self.conn.execute("PRAGMA table_info(listings)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}
        if "search_text" not in columns:
            await self.conn.execute(
                "ALTER TABLE listings ADD COLUMN search_text TEXT NOT NULL DEFAULT ''"
            )
            rows = await self._fetchall("SELECT id, title, description FROM listings")
            for row in rows:
                await self.conn.execute(
                    "UPDATE listings SET search_text = ? WHERE id = ?",
                    (search_key(row["title"], row["description"]), row["id"]),
                )
            await self.conn.commit()

        # Миграция 2: community_id в users
        async with self.conn.execute("PRAGMA table_info(users)") as cursor:
            user_columns = {row["name"] for row in await cursor.fetchall()}
        if "community_id" not in user_columns:
            await self.conn.execute(
                "ALTER TABLE users ADD COLUMN community_id INTEGER REFERENCES communities(id)"
            )
            await self.conn.commit()

        # Миграция 3: community_id в listings
        async with self.conn.execute("PRAGMA table_info(listings)") as cursor:
            listing_columns = {row["name"] for row in await cursor.fetchall()}
        if "community_id" not in listing_columns:
            await self.conn.execute(
                "ALTER TABLE listings ADD COLUMN community_id INTEGER REFERENCES communities(id)"
            )
            await self.conn.commit()

        # Миграция 4: пересобрать индекс раздела с учётом площадки. CREATE INDEX IF NOT EXISTS
        # не обновляет определение уже существующего индекса, поэтому проверяем руками.
        index_row = await self._fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_listings_cat'"
        )
        if index_row is not None and "community_id" not in (index_row["sql"] or ""):
            await self.conn.execute("DROP INDEX IF EXISTS idx_listings_cat")
            await self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_listings_cat"
                " ON listings(status, category_code, community_id, created_at DESC)"
            )
            await self.conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def seed_categories(self) -> None:
        for category in CATEGORIES:
            await self.conn.execute(
                """
                INSERT INTO categories(code, title, emoji, ttl_days, sort, is_food)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    title = excluded.title,
                    emoji = excluded.emoji,
                    ttl_days = excluded.ttl_days,
                    sort = excluded.sort,
                    is_food = excluded.is_food
                """,
                (
                    category.code,
                    category.title,
                    category.emoji,
                    category.ttl_days,
                    category.sort,
                    int(category.is_food),
                ),
            )
        await self.conn.commit()

    # --- служебное ---------------------------------------------------------
    async def _execute(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Cursor:
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def _scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = await self._fetchone(sql, params)
        return None if row is None else row[0]

    # --- пользователи ------------------------------------------------------
    async def upsert_user(self, tg_id: int, username: str | None, first_name: str | None) -> aiosqlite.Row:
        timestamp = now_iso()
        await self._execute(
            """
            INSERT INTO users(tg_id, username, first_name, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen_at = excluded.last_seen_at
            """,
            (tg_id, username, first_name, timestamp, timestamp),
        )
        user = await self.get_user_by_tg(tg_id)
        assert user is not None
        return user

    async def get_user_by_tg(self, tg_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM users WHERE tg_id = ?", (tg_id,))

    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))

    async def find_user(self, raw: str) -> aiosqlite.Row | None:
        value = (raw or "").strip().lstrip("@")
        if not value:
            return None
        if value.isdigit():
            user = await self.get_user_by_tg(int(value))
            if user is not None:
                return user
        return await self._fetchone(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (value,)
        )

    async def set_agreed(self, tg_id: int) -> None:
        await self._execute("UPDATE users SET agreed_at = ? WHERE tg_id = ?", (now_iso(), tg_id))

    async def set_banned(self, tg_id: int, banned: bool) -> None:
        await self._execute("UPDATE users SET is_banned = ? WHERE tg_id = ?", (int(banned), tg_id))

    async def refresh_rating(self, user_id: int) -> None:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(rating), 0) AS total, COUNT(*) AS amount FROM reviews WHERE target_id = ?",
            (user_id,),
        )
        await self._execute(
            "UPDATE users SET rating_sum = ?, rating_count = ? WHERE id = ?",
            (int(row["total"]), int(row["amount"]), user_id),
        )

    async def active_user_ids(self, days: int = 30, community_id: int | None = None) -> list[int]:
        rows = await self._fetchall(
            """
            SELECT tg_id FROM users
            WHERE is_banned = 0 AND last_seen_at >= ?
                AND (? IS NULL OR community_id = ?)
            """,
            (iso_days_ago(days), community_id, community_id),
        )
        return [int(row["tg_id"]) for row in rows]

    # --- объявления --------------------------------------------------------
    async def create_listing(
        self,
        *,
        author_id: int,
        community_id: int | None = None,
        kind: str,
        category_code: str,
        title: str,
        description: str,
        price: int | None,
        is_negotiable: bool,
        photo_file_id: str | None,
        status: str,
        reject_reason: str | None = None,
    ) -> int:
        cursor = await self._execute(
            """
            INSERT INTO listings(
                author_id, community_id, kind, category_code, title, description, search_text, price,
                is_negotiable, photo_file_id, status, created_at, reject_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                author_id,
                community_id,
                kind,
                category_code,
                title,
                description,
                search_key(title, description),
                price,
                int(is_negotiable),
                photo_file_id,
                status,
                now_iso(),
                reject_reason,
            ),
        )
        return int(cursor.lastrowid or 0)

    async def get_listing(self, listing_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            f"SELECT {CARD_COLUMNS} FROM listings l JOIN users u ON u.id = l.author_id WHERE l.id = ?",
            (listing_id,),
        )

    async def list_user_listings(
        self, user_id: int, statuses: Iterable[str] = ("active",)
    ) -> list[aiosqlite.Row]:
        statuses = tuple(statuses)
        placeholders = ",".join("?" for _ in statuses)
        return await self._fetchall(
            f"""
            SELECT {CARD_COLUMNS}
            FROM listings l JOIN users u ON u.id = l.author_id
            WHERE l.author_id = ? AND l.status IN ({placeholders})
            ORDER BY l.created_at DESC
            """,
            (user_id, *statuses),
        )

    async def count_active_by_user(self, user_id: int) -> int:
        return int(
            await self._scalar(
                "SELECT COUNT(*) FROM listings WHERE author_id = ? AND status IN ('active', 'pending')",
                (user_id,),
            )
            or 0
        )

    async def count_listings_since(self, user_id: int, seconds: int) -> int:
        return int(
            await self._scalar(
                "SELECT COUNT(*) FROM listings WHERE author_id = ? AND created_at >= ?",
                (user_id, iso_seconds_ago(seconds)),
            )
            or 0
        )

    async def list_active(
        self,
        category_code: str,
        limit: int,
        offset: int = 0,
        community_id: int | None = None,
    ) -> list[aiosqlite.Row]:
        """community_id=None — показываем объявления всех площадок (режим одной площадки)."""
        return await self._fetchall(
            f"""
            SELECT {CARD_COLUMNS}
            FROM listings l JOIN users u ON u.id = l.author_id
            WHERE l.status = 'active' AND l.category_code = ?
                AND (? IS NULL OR l.community_id = ?)
            ORDER BY CASE WHEN l.bumped_until IS NOT NULL AND l.bumped_until > ? THEN 1 ELSE 0 END DESC,
                     l.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (category_code, community_id, community_id, now_iso(), limit, offset),
        )

    async def count_active(self, category_code: str, community_id: int | None = None) -> int:
        return int(
            await self._scalar(
                """
                SELECT COUNT(*) FROM listings
                WHERE status = 'active' AND category_code = ?
                    AND (? IS NULL OR community_id = ?)
                """,
                (category_code, community_id, community_id),
            )
            or 0
        )

    async def category_counts(self, community_id: int | None = None) -> dict[str, int]:
        rows = await self._fetchall(
            """
            SELECT category_code, COUNT(*) AS amount
            FROM listings
            WHERE status = 'active' AND (? IS NULL OR community_id = ?)
            GROUP BY category_code
            """,
            (community_id, community_id),
        )
        return {row["category_code"]: int(row["amount"]) for row in rows}

    async def count_all_active(self, community_id: int | None = None) -> int:
        return int(
            await self._scalar(
                """
                SELECT COUNT(*) FROM listings
                WHERE status = 'active' AND (? IS NULL OR community_id = ?)
                """,
                (community_id, community_id),
            )
            or 0
        )

    async def search_active(
        self, query: str, limit: int = 10, community_id: int | None = None
    ) -> list[aiosqlite.Row]:
        key = normalize(query).lower()
        if not key:
            return []
        pattern = f"%{key}%"
        return await self._fetchall(
            f"""
            SELECT {CARD_COLUMNS}
            FROM listings l JOIN users u ON u.id = l.author_id
            WHERE l.status = 'active' AND l.search_text LIKE ?
                AND (? IS NULL OR l.community_id = ?)
            ORDER BY l.created_at DESC
            LIMIT ?
            """,
            (pattern, community_id, community_id, limit),
        )

    async def set_listing_status(
        self,
        listing_id: int,
        status: str,
        *,
        expires_at: str | None = None,
        reject_reason: str | None = None,
        moderated_by: int | None = None,
    ) -> None:
        await self._execute(
            """
            UPDATE listings
            SET status = ?, expires_at = COALESCE(?, expires_at),
                reject_reason = COALESCE(?, reject_reason), moderated_by = COALESCE(?, moderated_by)
            WHERE id = ?
            """,
            (status, expires_at, reject_reason, moderated_by, listing_id),
        )

    async def bump_listing(self, listing_id: int, until_iso: str) -> None:
        await self._execute("UPDATE listings SET bumped_until = ? WHERE id = ?", (until_iso, listing_id))

    async def archive_expired(self) -> int:
        cursor = await self._execute(
            """
            UPDATE listings SET status = 'archived'
            WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?
            """,
            (now_iso(),),
        )
        return int(cursor.rowcount or 0)

    async def list_pending(self, limit: int = 20) -> list[aiosqlite.Row]:
        return await self._fetchall(
            f"""
            SELECT {CARD_COLUMNS}
            FROM listings l JOIN users u ON u.id = l.author_id
            WHERE l.status = 'pending'
            ORDER BY l.created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

    # --- сделки и отзывы ---------------------------------------------------
    async def create_deal(self, listing_id: int, buyer_id: int, seller_id: int) -> int:
        await self._execute(
            """
            INSERT OR IGNORE INTO deals(listing_id, buyer_id, seller_id, status, created_at)
            VALUES (?, ?, ?, 'agreed', ?)
            """,
            (listing_id, buyer_id, seller_id, now_iso()),
        )
        row = await self._fetchone(
            "SELECT id FROM deals WHERE listing_id = ? AND buyer_id = ?", (listing_id, buyer_id)
        )
        return int(row["id"]) if row else 0

    async def get_deal(self, deal_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM deals WHERE id = ?", (deal_id,))

    async def set_deal_status(self, deal_id: int, status: str) -> None:
        closed_at = now_iso() if status in {"done", "cancelled"} else None
        await self._execute(
            "UPDATE deals SET status = ?, closed_at = COALESCE(?, closed_at) WHERE id = ?",
            (status, closed_at, deal_id),
        )

    async def has_review(self, deal_id: int, rater_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM reviews WHERE deal_id = ? AND rater_id = ?", (deal_id, rater_id)
        )
        return row is not None

    async def create_review(
        self, deal_id: int, rater_id: int, target_id: int, rating: int, text: str | None
    ) -> bool:
        cursor = await self._execute(
            """
            INSERT OR IGNORE INTO reviews(deal_id, rater_id, target_id, rating, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (deal_id, rater_id, target_id, rating, text, now_iso()),
        )
        created = bool(cursor.rowcount)
        if created:
            await self.refresh_rating(target_id)
        return created

    async def list_reviews_for(self, user_id: int, limit: int = 5) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT r.*, u.username AS rater_username, u.first_name AS rater_name
            FROM reviews r JOIN users u ON u.id = r.rater_id
            WHERE r.target_id = ?
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

    # --- жалобы, топ, реклама ---------------------------------------------
    async def create_report(self, listing_id: int | None, reporter_id: int, reason: str) -> int:
        cursor = await self._execute(
            """
            INSERT INTO reports(listing_id, reporter_id, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (listing_id, reporter_id, reason, now_iso()),
        )
        return int(cursor.lastrowid or 0)

    async def list_open_reports(self, limit: int = 20) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT r.*, u.username AS reporter_username, l.title AS listing_title
            FROM reports r
            JOIN users u ON u.id = r.reporter_id
            LEFT JOIN listings l ON l.id = r.listing_id
            WHERE r.status = 'open'
            ORDER BY r.created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

    async def close_report(self, report_id: int, admin_tg_id: int) -> None:
        await self._execute(
            "UPDATE reports SET status = 'closed', resolved_by = ? WHERE id = ?",
            (admin_tg_id, report_id),
        )

    async def add_promotion(
        self, listing_id: int, paid_until: str, amount: int, granted_by: int
    ) -> None:
        await self._execute(
            """
            INSERT INTO promotions(listing_id, kind, paid_until, amount, method, granted_by, created_at)
            VALUES (?, 'bump', ?, ?, 'manual', ?, ?)
            """,
            (listing_id, paid_until, amount, granted_by, now_iso()),
        )

    async def create_ad(
        self, partner_name: str, text: str, days: int, price: int, created_by: int
    ) -> int:
        cursor = await self._execute(
            """
            INSERT INTO ads(partner_name, text, starts_at, ends_at, price, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
            """,
            (partner_name, text, now_iso(), iso_in_days(days), price, created_by, now_iso()),
        )
        return int(cursor.lastrowid or 0)

    async def set_ad_status(self, ad_id: int, status: str) -> None:
        await self._execute("UPDATE ads SET status = ? WHERE id = ?", (status, ad_id))

    async def get_ad(self, ad_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM ads WHERE id = ?", (ad_id,))

    async def list_active_ads(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM ads WHERE status = 'active' AND (ends_at IS NULL OR ends_at > ?)",
            (now_iso(),),
        )

    async def expire_ads(self) -> int:
        cursor = await self._execute(
            "UPDATE ads SET status = 'expired' WHERE status = 'active' AND ends_at IS NOT NULL AND ends_at <= ?",
            (now_iso(),),
        )
        return int(cursor.rowcount or 0)

    # --- события, метрики, meta -------------------------------------------
    async def log_event(
        self,
        kind: str,
        *,
        user_id: int | None = None,
        listing_id: int | None = None,
        meta: str | None = None,
    ) -> None:
        await self._execute(
            "INSERT INTO events(kind, user_id, listing_id, meta, created_at) VALUES (?, ?, ?, ?, ?)",
            (kind, user_id, listing_id, meta, now_iso()),
        )

    async def stats(self, days: int = 7, community_id: int | None = None) -> dict[str, Any]:
        """Сводка. community_id=None — по всем площадкам сразу."""
        since = iso_days_ago(days)
        return {
            "users_active": int(
                await self._scalar(
                    """
                    SELECT COUNT(*) FROM users
                    WHERE last_seen_at >= ? AND (? IS NULL OR community_id = ?)
                    """,
                    (since, community_id, community_id),
                )
                or 0
            ),
            "listings_created": int(
                await self._scalar(
                    """
                    SELECT COUNT(*) FROM listings
                    WHERE created_at >= ? AND (? IS NULL OR community_id = ?)
                    """,
                    (since, community_id, community_id),
                )
                or 0
            ),
            "listings_active": await self.count_all_active(community_id),
            "deals_done": int(
                await self._scalar(
                    """
                    SELECT COUNT(*) FROM deals d JOIN listings l ON l.id = d.listing_id
                    WHERE d.status = 'done' AND d.closed_at >= ?
                        AND (? IS NULL OR l.community_id = ?)
                    """,
                    (since, community_id, community_id),
                )
                or 0
            ),
            "deals_total": int(
                await self._scalar(
                    """
                    SELECT COUNT(*) FROM deals d JOIN listings l ON l.id = d.listing_id
                    WHERE (? IS NULL OR l.community_id = ?)
                    """,
                    (community_id, community_id),
                )
                or 0
            ),
            "reports_open": int(
                await self._scalar("SELECT COUNT(*) FROM reports WHERE status = 'open'") or 0
            ),
            "contacts_shown": int(
                await self._scalar(
                    """
                    SELECT COUNT(*) FROM events e JOIN listings l ON l.id = e.listing_id
                    WHERE e.kind = 'contact_shown' AND e.created_at >= ?
                        AND (? IS NULL OR l.community_id = ?)
                    """,
                    (since, community_id, community_id),
                )
                or 0
            ),
            "category_counts": await self.category_counts(community_id),
        }

    async def meta_get(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM meta WHERE key = ?", (key,))
        return None if row is None else str(row["value"])

    async def meta_set(self, key: str, value: str) -> None:
        await self._execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # --- площадки (communities) --------------------------------------------
    async def create_community(
        self, code: str, title: str, city: str, ambassador_user_id: int | None = None
    ) -> int:
        cursor = await self._execute(
            "INSERT INTO communities(code, title, city, ambassador_user_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, title, city, ambassador_user_id, now_iso()),
        )
        return int(cursor.lastrowid or 0)

    async def get_community(self, community_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM communities WHERE id = ?", (community_id,))

    async def get_community_by_code(self, code: str) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM communities WHERE code = ?", (code,))

    async def list_active_communities(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM communities WHERE is_active = 1 ORDER BY created_at ASC"
        )

    async def set_user_community(self, user_id: int, community_id: int | None) -> None:
        await self._execute("UPDATE users SET community_id = ? WHERE id = ?", (community_id, user_id))

    async def count_community_users(self, community_id: int) -> int:
        return int(
            await self._scalar(
                "SELECT COUNT(*) FROM users WHERE community_id = ? AND is_banned = 0",
                (community_id,),
            )
            or 0
        )

    async def count_community_listings(self, community_id: int, status: str = "active") -> int:
        return int(
            await self._scalar(
                "SELECT COUNT(*) FROM listings WHERE community_id = ? AND status = ?",
                (community_id, status),
            )
            or 0
        )

    async def list_communities_with_counts(self, active_only: bool = False) -> list[aiosqlite.Row]:
        """Площадки вместе с числом активных объявлений и активных участников."""
        return await self._fetchall(
            """
            SELECT c.*,
                   (SELECT COUNT(*) FROM listings l
                     WHERE l.community_id = c.id AND l.status = 'active') AS listings_count,
                   (SELECT COUNT(*) FROM users u
                     WHERE u.community_id = c.id AND u.is_banned = 0) AS users_count
            FROM communities c
            WHERE (? = 0 OR c.is_active = 1)
            ORDER BY c.created_at ASC
            """,
            (int(active_only),),
        )

    async def set_community_active(self, community_id: int, is_active: bool) -> None:
        await self._execute(
            "UPDATE communities SET is_active = ? WHERE id = ?", (int(is_active), community_id)
        )

    async def set_community_ambassador(self, community_id: int, user_id: int | None) -> None:
        await self._execute(
            "UPDATE communities SET ambassador_user_id = ? WHERE id = ?", (user_id, community_id)
        )

    async def adopt_unassigned(self, community_id: int) -> tuple[int, int]:
        """Первая площадка забирает всё, что ещё не привязано. Возвращает (людей, объявлений)."""
        users_cursor = await self._execute(
            "UPDATE users SET community_id = ? WHERE community_id IS NULL", (community_id,)
        )
        listings_cursor = await self._execute(
            "UPDATE listings SET community_id = ? WHERE community_id IS NULL", (community_id,)
        )
        return int(users_cursor.rowcount or 0), int(listings_cursor.rowcount or 0)
