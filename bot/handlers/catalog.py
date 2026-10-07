"""Каталог: разделы, страницы, карточка объявления, контакт, поиск."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, services, texts
from bot.categories import get_category
from bot.config import Config
from bot.db import Database
from bot.handlers.states import Search
from bot.keyboards import CATALOG_PAGE_SIZE

router = Router(name="catalog")


async def _safe_edit(callback: CallbackQuery, text: str, markup=None) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=markup)


async def _render_category(callback: CallbackQuery, db: Database, code: str, page: int) -> None:
    category = get_category(code)
    if category is None:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    page = max(0, page)
    total = await db.count_active(code)
    listings = await db.list_active(code, CATALOG_PAGE_SIZE, page * CATALOG_PAGE_SIZE)
    if not listings:
        text = (
            f"{category.emoji} <b>{category.title}</b>\n\n"
            f"Пока пусто. Будь первым: нажми «{texts.BTN_NEW}»."
        )
    else:
        text = (
            f"{category.emoji} <b>{category.title}</b> — {total} шт.\n"
            f"Живые объявления уходят в архив сами: еда через 1 день, услуги через 7, вещи через 14.\n\n"
            "Выбери объявление:"
        )
    await _safe_edit(callback, text, keyboards.catalog_kb(code, page, listings, total))


@router.message(StateFilter(None), F.text == texts.BTN_CATALOG)
async def catalog_root(message: Message, user, db: Database, config: Config) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    visible = await services.category_menu(db, config.bootstrap_categories)
    total = await db.count_all_active()
    await message.answer(
        f"🛒 В каталоге {total} активных объявлений.\nВыбери раздел:",
        reply_markup=keyboards.categories_kb(visible),
    )


@router.callback_query(F.data == "catmenu")
async def back_to_categories(callback: CallbackQuery, db: Database, config: Config) -> None:
    visible = await services.category_menu(db, config.bootstrap_categories)
    total = await db.count_all_active()
    await _safe_edit(
        callback,
        f"🛒 В каталоге {total} активных объявлений.\nВыбери раздел:",
        keyboards.categories_kb(visible),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def open_category(callback: CallbackQuery, db: Database) -> None:
    code = callback.data.split(":")[1]
    await _render_category(callback, db, code, 0)
    await callback.answer()


@router.callback_query(F.data.startswith("page:"))
async def open_page(callback: CallbackQuery, db: Database) -> None:
    _, code, page = callback.data.split(":")
    await _render_category(callback, db, code, int(page))
    await callback.answer()


@router.callback_query(F.data.startswith("card:"))
async def open_card(callback: CallbackQuery, db: Database, user) -> None:
    parts = callback.data.split(":")
    listing_id = int(parts[1])
    code = parts[2] if len(parts) > 2 else None
    page = int(parts[3]) if len(parts) > 3 else 0

    listing = await db.get_listing(listing_id)
    if listing is None or listing["status"] not in {"active", "pending"}:
        await callback.answer("Объявление больше недоступно", show_alert=True)
        return

    card = texts.format_listing_card(listing)
    markup = keyboards.listing_card_kb(listing_id, code, page)
    if callback.message is None:
        await callback.answer()
        return
    if listing["photo_file_id"]:
        await callback.message.answer_photo(
            listing["photo_file_id"], caption=card[:1024], reply_markup=markup
        )
    else:
        await callback.message.answer(card, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("contact:"))
async def show_contact(callback: CallbackQuery, db: Database, user) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None or listing["status"] != "active":
        await callback.answer("Объявление уже неактуально", show_alert=True)
        return
    await db.log_event("contact_shown", user_id=user["id"], listing_id=listing_id)
    handle = (
        f"@{listing['username']}"
        if listing["username"]
        else f"tg://user?id={listing['author_tg_id']}"
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"✍️ Пиши автору: {handle}\n\n"
            "Договорись о цене и встрече. <b>Деньги бот не передаёт</b> — рассчитывайтесь лично."
        )


@router.message(StateFilter(None), F.text == texts.BTN_SEARCH)
async def ask_query(message: Message, state: FSMContext, user) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    await state.set_state(Search.query)
    await message.answer("Что искать? Напиши слово, например «пицца» или «печать».")


@router.message(Search.query, F.text)
async def run_search(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    query = " ".join(message.text.split())
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Напиши хотя бы 2 символа.")
        return
    rows = await db.search_active(query, 10)
    if not rows:
        await message.answer(f"Ничего не нашлось по «{texts.escape(query)}».")
        return
    body = "\n".join(texts.short_listing_line(row) for row in rows)
    await message.answer(
        f"🔍 Нашёл {len(rows)} по «{texts.escape(query)}»:\n\n{body}",
        reply_markup=keyboards.search_results_kb(rows),
    )
