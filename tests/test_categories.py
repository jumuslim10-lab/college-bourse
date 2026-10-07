"""Тесты правила видимости разделов и сроков жизни объявлений."""

from __future__ import annotations

from bot.categories import (
    CATEGORIES,
    MIN_ACTIVE_FOR_VISIBLE,
    get_category,
    is_visible,
    ttl_days,
)
from bot.services import category_menu, visible_categories
from tests.helpers import make_listing, make_user, open_db, run


def test_visibility_rule():
    assert is_visible(0, bootstrap=True)
    assert is_visible(0, bootstrap=False) is False
    assert is_visible(MIN_ACTIVE_FOR_VISIBLE - 1, bootstrap=False) is False
    assert is_visible(MIN_ACTIVE_FOR_VISIBLE, bootstrap=False) is True


def test_ttl_by_category():
    assert ttl_days("food") == 1
    assert ttl_days("services") == 7
    assert ttl_days("goods") == 14
    assert ttl_days("неизвестная") == 7


def test_visible_categories_filters_empty_sections():
    counts = {"food": 1, "services": 5, "goods": 0}
    assert [c.code for c, _ in visible_categories(counts, bootstrap=True)] == [
        "food",
        "services",
        "goods",
    ]
    # без bootstrap-режима показываем только разделы, набравшие минимум объявлений
    assert [c.code for c, _ in visible_categories(counts, bootstrap=False)] == ["services"]


def test_category_menu_reads_counts_from_db(tmp_path):
    async def scenario():
        async with open_db(tmp_path) as db:
            user = await make_user(db, 1)
            await make_listing(db, user, category_code="food", title="Пицца с собой")
            await make_listing(db, user, category_code="goods", title="Учебник по матану")

            bootstrap_menu = await category_menu(db, bootstrap=True)
            strict_menu = await category_menu(db, bootstrap=False)

            counts = {category.code: count for category, count in bootstrap_menu}
            assert counts["food"] == 1
            assert counts["goods"] == 1
            assert counts["services"] == 0
            assert strict_menu == []  # ни один раздел не набрал минимум объявлений

            assert get_category("food").is_food
            assert len(CATEGORIES) == 3

    run(scenario())
