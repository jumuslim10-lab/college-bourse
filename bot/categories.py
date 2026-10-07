"""Категории биржи, сроки жизни объявлений и правило видимости раздела."""

from __future__ import annotations

from dataclasses import dataclass

MIN_ACTIVE_FOR_VISIBLE = 5
DEFAULT_TTL_DAYS = 7


@dataclass(frozen=True)
class Category:
    code: str
    title: str
    emoji: str
    ttl_days: int
    sort: int
    is_food: bool = False


CATEGORIES: tuple[Category, ...] = (
    Category("food", "Еда и напитки", "🍕", 1, 10, is_food=True),
    Category("services", "Услуги", "🛠", 7, 20),
    Category("goods", "Вещи и учебники", "📚", 14, 30),
)

BY_CODE: dict[str, Category] = {category.code: category for category in CATEGORIES}


def get_category(code: str) -> Category | None:
    return BY_CODE.get(code)


def ttl_days(code: str) -> int:
    category = BY_CODE.get(code)
    return category.ttl_days if category else DEFAULT_TTL_DAYS


def is_visible(active_count: int, bootstrap: bool) -> bool:
    """Раздел виден, если включён bootstrap-режим или набрался минимум объявлений."""
    return bool(bootstrap) or active_count >= MIN_ACTIVE_FOR_VISIBLE
