"""Тесты мультиплощадочности: создание площадок, инвайты, изоляция каталога."""

from __future__ import annotations

from bot import services, texts
from tests.helpers import bind_community, make_listing, make_user, open_db, run


async def _community(db, code: str, title: str = "Колледж", city: str = "Бишкек"):
    community_id, error = await services.create_community(db, code=code, title=title, city=city)
    assert error is None, error
    return int(community_id)


def test_parse_start_payload():
    assert services.parse_start_payload("/start") is None
    assert services.parse_start_payload("/start   ") is None
    assert services.parse_start_payload(None) is None
    assert services.parse_start_payload("/start college-01") == "college-01"
    assert services.parse_start_payload("/start@my_bot  COLLEGE-01 ") == "college-01"


def test_community_code_validation():
    assert services.is_valid_community_code("college-01")
    assert services.is_valid_community_code("abc")
    assert not services.is_valid_community_code("ab")
    assert not services.is_valid_community_code("-abc")
    assert not services.is_valid_community_code("abc-")
    assert not services.is_valid_community_code("колледж-01")
    assert not services.is_valid_community_code("a" * 40)
    assert services.normalize_community_code(" College 01 ") == "college-01"


def test_can_view_community():
    assert services.can_view_community(None, 5)  # общий вид видит всё
    assert services.can_view_community(None, None)
    assert services.can_view_community(5, 5)
    assert not services.can_view_community(5, 6)
    assert not services.can_view_community(5, None)  # общий пул не виден внутри площадки


def test_create_and_join_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1, "student")
            assert user["community_id"] is None

            community_id = await _community(db, " College 01 ", "Колледж №1", "Бишкек")
            community = await db.get_community(community_id)
            assert community["code"] == "college-01"
            assert community["title"] == "Колледж №1"
            assert community["is_active"] == 1

            _, duplicate_error = await services.create_community(
                db, code="college-01", title="Другой", city="Ош"
            )
            assert duplicate_error is not None

            _, bad_code_error = await services.create_community(
                db, code="ab", title="Колледж", city="Ош"
            )
            assert bad_code_error is not None

            _, bad_city_error = await services.create_community(
                db, code="college-99", title="Колледж", city="   "
            )
            assert bad_city_error is not None

            joined, join_error = await services.join_community(db, user, "COLLEGE-01")
            assert join_error is None
            assert joined["id"] == community_id
            refreshed = await db.get_user(user["id"])
            assert refreshed["community_id"] == community_id

    run(scenario())


def test_join_unknown_and_inactive_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)

            _, error = await services.join_community(db, user, "no-such-college")
            assert error == texts.COMMUNITY_NOT_FOUND

            community_id = await _community(db, "college-02", "Колледж №2", "Ош")
            await db.set_community_active(community_id, False)
            _, error = await services.join_community(db, user, "college-02")
            assert error == texts.COMMUNITY_INACTIVE

    run(scenario())


def test_needs_community_switch_only_with_two_communities(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            assert not await services.needs_community_switch(db)
            await _community(db, "college-40", "Первая")
            assert not await services.needs_community_switch(db)
            await _community(db, "college-41", "Вторая")
            assert await services.needs_community_switch(db)

    run(scenario())


def test_listing_inherits_author_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            community_id = await _community(db, "college-03", "Колледж №3", "Токмок")
            user = await make_user(db, 1)
            user = await bind_community(db, user, community_id)

            outcome = await services.submit_listing(
                db,
                user=user,
                kind="sell",
                category_code="goods",
                title="Продам учебник по матану",
                description="Состояние нормальное, забрать можно у входа",
                price=200,
                is_negotiable=False,
                photo_file_id=None,
            )
            assert outcome.status == "pending"
            listing = await db.get_listing(outcome.listing_id)
            assert listing["community_id"] == community_id

    run(scenario())


def test_first_community_adopts_unassigned(tmp_path):
    """Первая площадка забирает общий пул: у студентов ничего не «пропадает»."""

    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            listing_id = await make_listing(db, user, title="Старое объявление")
            assert (await db.get_listing(listing_id))["community_id"] is None

            community_id = await _community(db, "college-60", "Первая")
            assert (await db.get_user(user["id"]))["community_id"] == community_id
            assert (await db.get_listing(listing_id))["community_id"] == community_id

            # вторая площадка уже никого не забирает
            other_user = await make_user(db, 2)
            other_listing = await make_listing(db, other_user, title="Новое объявление")
            await _community(db, "college-61", "Вторая", "Ош")
            assert (await db.get_user(other_user["id"]))["community_id"] is None
            assert (await db.get_listing(other_listing))["community_id"] is None

    run(scenario())


def test_catalog_is_scoped_by_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await _community(db, "college-10", "Колледж №10")
            second = await _community(db, "college-11", "Колледж №11", "Ош")
            user_first = await bind_community(db, await make_user(db, 1, "one"), first)
            user_second = await bind_community(db, await make_user(db, 2, "two"), second)
            legacy = await make_user(db, 3, "three")

            await make_listing(db, user_first, title="Учебник первой площадки")
            await make_listing(db, user_second, title="Учебник второй площадки")
            await make_listing(db, legacy, title="Старое объявление без площадки")

            first_titles = {
                row["title"] for row in await db.list_active("services", 10, community_id=first)
            }
            second_titles = {
                row["title"] for row in await db.list_active("services", 10, community_id=second)
            }

            assert "Учебник первой площадки" in first_titles
            # объявления без площадки остаются в общем пуле и не подмешиваются в площадку
            assert "Старое объявление без площадки" not in first_titles
            assert "Учебник второй площадки" not in first_titles
            assert "Учебник первой площадки" not in second_titles

            assert len(await db.list_active("services", 10)) == 3  # общий вид видит все
            assert await db.count_active("services", first) == 1
            assert await db.count_all_active(first) == 1
            assert await db.category_counts(first) == {"services": 1}

    run(scenario())


def test_search_is_scoped_by_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await _community(db, "college-12", "Колледж №12")
            second = await _community(db, "college-13", "Колледж №13", "Ош")
            user_first = await bind_community(db, await make_user(db, 1, "one"), first)
            user_second = await bind_community(db, await make_user(db, 2, "two"), second)

            await make_listing(db, user_first, title="Пицца первая")
            await make_listing(db, user_second, title="Пицца вторая")

            assert [row["title"] for row in await db.search_active("пицца", 10, first)] == [
                "Пицца первая"
            ]
            assert len(await db.search_active("пицца", 10)) == 2

    run(scenario())


def test_stats_scoped_by_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await _community(db, "college-20", "Первая")
            second = await _community(db, "college-21", "Вторая", "Ош")
            user_first = await bind_community(db, await make_user(db, 1, "one"), first)
            user_second = await bind_community(db, await make_user(db, 2, "two"), second)

            listing_first = await make_listing(db, user_first, title="Объявление один")
            await make_listing(db, user_second, title="Объявление два")

            deal_id = await db.create_deal(listing_first, user_second["id"], user_first["id"])
            await db.set_deal_status(deal_id, "done")
            await db.log_event("contact_shown", user_id=user_second["id"], listing_id=listing_first)

            scoped = await db.stats(7, first)
            assert scoped["listings_active"] == 1
            assert scoped["listings_created"] == 1
            assert scoped["deals_total"] == 1
            assert scoped["deals_done"] == 1
            assert scoped["contacts_shown"] == 1
            assert scoped["category_counts"] == {"services": 1}

            assert (await db.stats(7))["listings_active"] == 2
            assert (await db.stats(7))["deals_total"] == 1

    run(scenario())


def test_communities_with_counts_and_toggle(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await _community(db, "college-30", "Первая")
            user = await bind_community(db, await make_user(db, 1), first)
            await make_listing(db, user, title="Объявление")

            rows = await db.list_communities_with_counts()
            assert len(rows) == 1
            assert rows[0]["listings_count"] == 1
            assert rows[0]["users_count"] == 1

            await db.set_community_active(first, False)
            assert await db.list_communities_with_counts(active_only=True) == []
            assert len(await db.list_communities_with_counts()) == 1
            assert len(await db.list_active_communities()) == 0

    run(scenario())


def test_index_keeps_community_after_migration(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            row = await db._fetchone(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_listings_cat'"
            )
            assert row is not None
            assert "community_id" in row["sql"]

    run(scenario())


def test_rebroadcast_is_scoped_by_community(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            first = await _community(db, "college-50", "Первая")
            second = await _community(db, "college-51", "Вторая", "Ош")
            user_first = await bind_community(db, await make_user(db, 1, "one"), first)
            user_second = await bind_community(db, await make_user(db, 2, "two"), second)
            unassigned = await make_user(db, 3, "three")

            first_ids = await db.active_user_ids(30, first)
            all_ids = await db.active_user_ids(30)

            assert first_ids == [user_first["tg_id"]]
            assert set(all_ids) == {user_first["tg_id"], user_second["tg_id"], unassigned["tg_id"]}

    run(scenario())
