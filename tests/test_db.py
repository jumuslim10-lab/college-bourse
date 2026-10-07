"""Тесты слоя данных: пользователи, объявления, сделки, отзывы, жалобы, топ."""

from __future__ import annotations

from bot.db import Database, iso_in_days, iso_seconds_ago
from tests.helpers import make_listing, make_user, open_db, run


def test_user_upsert_keeps_same_row(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 111, "vasya", "Вася")
            assert user["tg_id"] == 111
            again = await make_user(db, 111, "vasya_new", "Вася")
            assert again["id"] == user["id"]
            assert again["username"] == "vasya_new"
            assert await db.get_user_by_tg(111) is not None

    run(scenario())


def test_find_user_by_username_and_id(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            await make_user(db, 222, "petya", "Петя")
            assert (await db.find_user("@petya"))["tg_id"] == 222
            assert (await db.find_user("222"))["tg_id"] == 222
            assert await db.find_user("нет_такого") is None

    run(scenario())


def test_activate_sets_expiry_by_category_ttl(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            listing_id = await make_listing(db, user, category_code="food", status="pending")
            listing = await db.get_listing(listing_id)
            assert listing["expires_at"] is None

            await db.set_listing_status(listing_id, "active", expires_at=iso_in_days(1))
            active = await db.get_listing(listing_id)
            assert active["status"] == "active"
            assert active["expires_at"] is not None
            assert await db.count_active("food") == 1

    run(scenario())


def test_archive_expired_only_touches_old_listings(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            old_id = await make_listing(db, user, title="Старое объявление")
            fresh_id = await make_listing(db, user, title="Свежее объявление")
            await db.set_listing_status(old_id, "active", expires_at=iso_seconds_ago(10))
            await db.set_listing_status(fresh_id, "active", expires_at=iso_in_days(3))

            archived = await db.archive_expired()

            assert archived == 1
            assert (await db.get_listing(old_id))["status"] == "archived"
            assert (await db.get_listing(fresh_id))["status"] == "active"

    run(scenario())


def test_bumped_listing_goes_first(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await make_user(db, 1, "one")
            second = await make_user(db, 2, "two")
            plain_id = await make_listing(db, second, title="Обычное объявление")
            bumped_id = await make_listing(db, first, title="Топовое объявление")
            await db.set_listing_status(bumped_id, "active")
            await db.bump_listing(bumped_id, iso_in_days(1))

            rows = await db.list_active("services", limit=10)

            ids = [row["id"] for row in rows]
            assert ids[0] == bumped_id
            assert plain_id in ids

    run(scenario())


def test_deal_is_unique_per_listing_and_buyer(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            seller = await make_user(db, 1, "seller")
            buyer = await make_user(db, 2, "buyer")
            listing_id = await make_listing(db, seller)

            first = await db.create_deal(listing_id, buyer["id"], seller["id"])
            second = await db.create_deal(listing_id, buyer["id"], seller["id"])

            assert first == second
            assert len(await db._fetchall("SELECT * FROM deals")) == 1
            assert (await db.get_deal(first))["status"] == "agreed"

    run(scenario())


def test_review_saved_once_and_updates_rating(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            seller = await make_user(db, 1, "seller")
            buyer = await make_user(db, 2, "buyer")
            listing_id = await make_listing(db, seller)
            deal_id = await db.create_deal(listing_id, buyer["id"], seller["id"])

            assert await db.create_review(deal_id, buyer["id"], seller["id"], 5, "всё ок")
            assert not await db.create_review(deal_id, buyer["id"], seller["id"], 1, "повторный")

            updated_seller = await db.get_user(seller["id"])
            assert updated_seller["rating_sum"] == 5
            assert updated_seller["rating_count"] == 1
            assert await db.has_review(deal_id, buyer["id"])

    run(scenario())


def test_reports_open_and_close(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            author = await make_user(db, 1, "author")
            reporter = await make_user(db, 2, "reporter")
            listing_id = await make_listing(db, author)

            report_id = await db.create_report(listing_id, reporter["id"], "не отдал товар")
            open_reports = await db.list_open_reports()
            assert [row["id"] for row in open_reports] == [report_id]

            await db.close_report(report_id, admin_tg_id=999)
            assert await db.list_open_reports() == []

    run(scenario())


def test_banned_user_is_excluded_from_broadcast(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            good = await make_user(db, 1, "good")
            banned = await make_user(db, 2, "banned")
            await db.set_banned(banned["tg_id"], True)

            tg_ids = await db.active_user_ids(days=30)

            assert good["tg_id"] in tg_ids
            assert banned["tg_id"] not in tg_ids

    run(scenario())


def test_search_finds_by_title_and_description(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            await make_listing(db, user, title="Пицца с собой", description="Привезу горячую к 3 паре")
            await make_listing(db, user, title="Печать", description="Свой принтер, ч/б и цвет")

            assert len(await db.search_active("пицца")) == 1
            assert len(await db.search_active("ПРИНТЕР")) == 1
            assert await db.search_active("самокат") == []

    run(scenario())


def test_reconnect_keeps_data_and_migration_is_idempotent(tmp_path):
    async def scenario():
        db = Database(tmp_path / "again.db")
        await db.connect()
        user = await db.upsert_user(1, "x", "X")
        listing_id = await make_listing(db, user, title="Пицца с собой")
        await db.close()

        again = Database(tmp_path / "again.db")
        await again.connect()
        try:
            assert (await again.get_listing(listing_id))["title"] == "Пицца с собой"
            assert len(await again.search_active("ПИЦЦА")) == 1
        finally:
            await again.close()

    run(scenario())
