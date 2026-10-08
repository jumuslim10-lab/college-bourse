"""Клавиатуры бота."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.categories import Category

CATALOG_PAGE_SIZE = 8


def main_menu(show_communities: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=texts.BTN_CATALOG), KeyboardButton(text=texts.BTN_NEW)],
        [KeyboardButton(text=texts.BTN_MY), KeyboardButton(text=texts.BTN_SEARCH)],
    ]
    if show_communities:
        rows.append([KeyboardButton(text=texts.BTN_COMMUNITIES)])
    rows.append([KeyboardButton(text=texts.BTN_HELP)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def rules_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Принимаю", callback_data="rules:accept")]]
    )


def categories_kb(visible: Iterable[tuple[Category, int]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{category.emoji} {category.title} ({count})",
                callback_data=f"cat:{category.code}",
            )
        ]
        for category, count in visible
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Пока пусто", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_kb(code: str, page: int, listings: list[Any], total: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{texts.KIND_LABELS.get(row['kind'], row['kind'])}: {row['title'][:32]} — "
                f"{texts.format_price(row['price'], row['is_negotiable'])}",
                callback_data=f"card:{row['id']}:{code}:{page}",
            )
        ]
        for row in listings
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{code}:{page - 1}"))
    pages = max(1, (total + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{code}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 Категории", callback_data="catmenu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def listing_card_kb(listing_id: int, code: str | None = None, page: int = 0) -> InlineKeyboardMarkup:
    from bot.categories import get_category

    rows = [
        [InlineKeyboardButton(text="✍️ Написать автору", callback_data=f"contact:{listing_id}")],
        [InlineKeyboardButton(text="🤝 Сделка состоялась", callback_data=f"deal:{listing_id}")],
        [InlineKeyboardButton(text="🚩 Жалоба", callback_data=f"report:{listing_id}")],
    ]
    nav: list[InlineKeyboardButton] = []
    if code and get_category(code) is not None:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{code}:{page}"))
    nav.append(InlineKeyboardButton(text="🏠 Категории", callback_data="catmenu"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_kb(listings: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=row["title"][:40], callback_data=f"card:{row['id']}:search:0")]
        for row in listings
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Ничего не нашлось", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_listings_kb(listings: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in listings:
        rows.append(
            [
                InlineKeyboardButton(text=row["title"][:30], callback_data=f"card:{row['id']}:my:0"),
                InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close:{row['id']}"),
                InlineKeyboardButton(text="⬆️ В топ", callback_data=f"bump:{row['id']}"),
            ]
        )
    if not rows:
        rows = [[InlineKeyboardButton(text="Активных объявлений нет", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moderation_kb(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"modok:{listing_id}"),
                InlineKeyboardButton(text="⛔ Отклонить", callback_data=f"modno:{listing_id}"),
            ]
        ]
    )


def new_listing_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить на модерацию", callback_data="nl:send")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="nl:cancel")],
        ]
    )


def deal_seller_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{deal_id}"),
                InlineKeyboardButton(text="🚫 Не состоялось", callback_data=f"cancel:{deal_id}"),
            ]
        ]
    )


def review_stars_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1⭐", callback_data=f"rate:{deal_id}:1"),
                InlineKeyboardButton(text="2⭐", callback_data=f"rate:{deal_id}:2"),
                InlineKeyboardButton(text="3⭐", callback_data=f"rate:{deal_id}:3"),
                InlineKeyboardButton(text="4⭐", callback_data=f"rate:{deal_id}:4"),
                InlineKeyboardButton(text="5⭐", callback_data=f"rate:{deal_id}:5"),
            ]
        ]
    )


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Очередь модерации", callback_data="admin:queue")],
            [InlineKeyboardButton(text="🚩 Жалобы", callback_data="admin:reports")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="🏫 Площадки", callback_data="admin:communities")],
            [InlineKeyboardButton(text="📣 Реклама партнёра", callback_data="admin:ad")],
            [InlineKeyboardButton(text="✉️ Рассылка", callback_data="admin:broadcast")],
        ]
    )


def admin_queue_kb(listings: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{row['id']} {row['title'][:35]}", callback_data=f"mod:{row['id']}")]
        for row in listings
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Очередь пуста", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_reports_kb(reports: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{row['id']} объявление {row['listing_id']}",
                callback_data=f"closereport:{row['id']}",
            )
        ]
        for row in reports
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Открытых жалоб нет", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_publish_kb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Опубликовать всем", callback_data=f"adpub:{ad_id}")],
            [InlineKeyboardButton(text="❌ Не публиковать", callback_data=f"adskip:{ad_id}")],
        ]
    )


def broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить", callback_data="bc:send")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bc:cancel")],
        ]
    )


def new_listing_kind_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💸 Продаю", callback_data="nl:kind:sell"),
                InlineKeyboardButton(text="🛍 Куплю", callback_data="nl:kind:buy"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="nl:cancel")],
        ]
    )


def new_listing_categories_kb() -> InlineKeyboardMarkup:
    from bot.categories import CATEGORIES

    rows = [
        [InlineKeyboardButton(text=f"{c.emoji} {c.title}", callback_data=f"nl:cat:{c.code}")]
        for c in CATEGORIES
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="nl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="nl:cancel")]]
    )


def admin_bump_kb(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️ Выдать топ 24ч", callback_data=f"bumpok:{listing_id}"),
                InlineKeyboardButton(text="🚫 Отказать", callback_data=f"bumpno:{listing_id}"),
            ]
        ]
    )


def review_start_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"review:{deal_id}")]
        ]
    )


def communities_kb(communities: list[Any], current_id: int | None) -> InlineKeyboardMarkup:
    """Выбор площадки. current_id=None означает общий вид (все площадки)."""
    rows: list[list[InlineKeyboardButton]] = []
    for row in communities:
        mark = "✅ " if current_id == row["id"] else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{texts.community_label(row)} — {row['listings_count']} объявл.",
                    callback_data=f"switch_community:{row['id']}",
                )
            ]
        )
    if current_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.COMMUNITY_ALL_BUTTON, callback_data="switch_community:0"
                )
            ]
        )
    if not rows:
        rows = [[InlineKeyboardButton(text="Площадок пока нет", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_communities_kb(communities: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{'🟢' if row['is_active'] else '⚪️'} {row['code']} — "
                    f"{row['title']}: {row['listings_count']} объявл., {row['users_count']} чел."
                ),
                callback_data=f"comm_toggle:{row['id']}",
            )
        ]
        for row in communities
    ]
    rows.append([InlineKeyboardButton(text="➕ Создать площадку", callback_data="comm_new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
