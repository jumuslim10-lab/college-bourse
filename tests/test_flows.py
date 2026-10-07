"""Тесты валидации ввода и бизнес-логики публикации объявления."""

from __future__ import annotations

from bot import services
from bot.validation import (
    bad_word_error,
    find_bad_word,
    normalize,
    parse_price,
    validate_description,
    validate_title,
)
from tests.helpers import make_listing, make_user, open_db, run


def test_parse_price():
    assert parse_price("200") == (200, False, None)
    assert parse_price("1 500 ₽") == (1500, False, None)
    assert parse_price("договорная") == (None, True, None)
    assert parse_price("торг") == (None, True, None)
    assert parse_price("0")[2] is not None
    assert parse_price("999999")[2] is not None
    assert parse_price("abc")[2] is not None
    assert parse_price("")[2] is not None


def test_title_and_description_limits():
    assert validate_title("Пиц") is not None
    assert validate_title("Пицца с собой") is None
    assert validate_title("я" * 100) is not None
    assert validate_description("мало") is not None
    assert validate_description("Горячая пицца к третьей паре, принесу в кабинет") is None
    assert normalize("  две   пары  ") == "две пары"


def test_bad_words_filter():
    assert find_bad_word("Продаю пиццу, гарантия свежести") is None
    assert find_bad_word("Гарант сделки, кидайте деньги мне") is not None
    assert find_bad_word("Пишу курсовую на заказ") is not None
    assert find_bad_word("Контент 18+") is not None


def test_structural_validation_ignores_bad_words():
    """Проверки длины не дублируют автофильтр: за слова отвечает submit_listing."""
    assert validate_title("Гарант сделки") is None
    assert validate_description("Проведу сделку через себя и удержу процент") is None
    assert bad_word_error("Гарант сделки") is not None
    assert bad_word_error("Печать курсовой") is None


def test_submit_invalid_title_creates_nothing(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            outcome = await services.submit_listing(
                db,
                user=user,
                kind="sell",
                category_code="services",
                title="ок",
                description="слишком короткое описание для объявления",
                price=100,
                is_negotiable=False,
                photo_file_id=None,
            )
            assert outcome.status == "invalid"
            assert outcome.listing_id is None
            assert await db.count_active("services") == 0

    run(scenario())


def test_submit_bad_word_is_rejected_and_stored(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            outcome = await services.submit_listing(
                db,
                user=user,
                kind="sell",
                category_code="services",
                title="Гарант сделки",
                description="Проведу сделку через себя и удержу процент",
                price=100,
                is_negotiable=False,
                photo_file_id=None,
            )
            assert outcome.status == "rejected"
            stored = await db.get_listing(outcome.listing_id)
            assert stored["status"] == "rejected"
            assert "автофильтр" in stored["reject_reason"]

    run(scenario())


def test_submit_happy_path_pending_then_active(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            outcome = await services.submit_listing(
                db,
                user=user,
                kind="sell",
                category_code="services",
                title="Печать и сшивание курсовой",
                description="Свой принтер, сделаю за пару часов у кабинета 214",
                price=150,
                is_negotiable=False,
                photo_file_id=None,
            )
            assert outcome.status == "pending"

            stored = await db.get_listing(outcome.listing_id)
            assert stored["status"] == "pending"
            assert stored["expires_at"] is None

            activated = await services.activate_listing(db, outcome.listing_id, admin_tg_id=777)
            assert activated["status"] == "active"
            assert activated["expires_at"] is not None
            assert await db.count_active("services") == 1

    run(scenario())


def test_submit_respects_active_limit(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            for index in range(services.MAX_ACTIVE_PER_USER):
                listing_id = await make_listing(db, user, title=f"Объявление {index}")
                await db.set_listing_status(listing_id, "active")

            outcome = await services.submit_listing(
                db,
                user=user,
                kind="sell",
                category_code="services",
                title="Четвёртое объявление",
                description="Описание достаточной длины для проверки лимита",
                price=100,
                is_negotiable=False,
                photo_file_id=None,
            )
            assert outcome.status == "invalid"
            assert "лимит" in outcome.reason

    run(scenario())


def test_submit_respects_rate_limit(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            payload = {
                "kind": "sell",
                "category_code": "goods",
                "title": "Продам бу учебник",
                "description": "Состояние хорошее, забрать можно у входа",
                "price": 300,
                "is_negotiable": False,
                "photo_file_id": None,
            }
            first = await services.submit_listing(db, user=user, **payload)
            assert first.status == "pending"

            second = await services.submit_listing(db, user=user, **payload)
            assert second.status == "invalid"
            assert "Слишком часто" in second.reason

    run(scenario())


def test_reject_listing_sets_reason(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            listing_id = await make_listing(db, user, status="pending")
            rejected = await services.reject_listing(db, listing_id, admin_tg_id=777, reason="нет цены")
            assert rejected["status"] == "rejected"
            assert rejected["reject_reason"] == "нет цены"

    run(scenario())


def test_grant_bump_marks_promotion(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            listing_id = await make_listing(db, user)
            await services.grant_bump(db, listing_id, admin_tg_id=777)
            listing = await db.get_listing(listing_id)
            assert listing["bumped_until"] is not None
            rows = await db._fetchall("SELECT * FROM promotions WHERE listing_id = ?", (listing_id,))
            assert len(rows) == 1
            assert rows[0]["method"] == "manual"

    run(scenario())
