"""Создание объявления, «Мои объявления», закрытие и заявка на топ."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, services, texts
from bot.categories import get_category
from bot.config import Config
from bot.db import Database
from bot.handlers.states import NewListing
from bot.notify import send_to_admins
from bot.validation import (
    bad_word_error,
    parse_price,
    validate_description,
    validate_title,
)

router = Router(name="listing")

SKIP_WORDS = {"пропустить", "skip", "/skip", "-", "нет", "без фото"}


def _preview(data: dict) -> str:
    category = get_category(data.get("category", ""))
    kind = texts.KIND_LABELS.get(data.get("kind", ""), "?")
    category_label = f"{category.emoji} {category.title}" if category else "?"
    return (
        "👀 <b>Проверь объявление</b>\n\n"
        f"Тип: {kind}\n"
        f"Категория: {category_label}\n"
        f"Название: {texts.escape(data.get('title'))}\n"
        f"Цена: {texts.format_price(data.get('price'), data.get('is_negotiable'))}\n"
        f"Фото: {'есть' if data.get('photo') else 'нет'}\n\n"
        f"{texts.escape(data.get('description'))}"
    )


@router.message(StateFilter(None), F.text == texts.BTN_NEW)
async def start_new(message: Message, state: FSMContext, user, db: Database) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    active = await db.count_active_by_user(user["id"])
    if active >= services.MAX_ACTIVE_PER_USER:
        await message.answer(
            f"У тебя уже {active} активных объявления — это лимит "
            f"({services.MAX_ACTIVE_PER_USER}). Закрой лишнее в «{texts.BTN_MY}»."
        )
        return
    await state.set_state(NewListing.kind)
    await message.answer("Что делаем?", reply_markup=keyboards.new_listing_kind_kb())


@router.callback_query(NewListing.kind, F.data.startswith("nl:kind:"))
async def choose_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[-1]
    if kind not in texts.KIND_LABELS:
        await callback.answer("Непонятный тип", show_alert=True)
        return
    await state.update_data(kind=kind)
    await state.set_state(NewListing.category)
    if callback.message is not None:
        await callback.message.edit_text("Выбери раздел:", reply_markup=keyboards.new_listing_categories_kb())
    await callback.answer()


@router.callback_query(NewListing.category, F.data.startswith("nl:cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.split(":")[-1]
    category = get_category(code)
    if category is None:
        await callback.answer("Нет такого раздела", show_alert=True)
        return
    await state.update_data(category=code)
    await state.set_state(NewListing.photo)
    hint = "Пришли одно фото или напиши «пропустить»."
    if category.is_food:
        hint += "\n\n🍕 Только фабричная упаковка или партнёрская доставка: домашняя еда запрещена правилами."
    if callback.message is not None:
        await callback.message.edit_text(hint, reply_markup=keyboards.cancel_kb())
    await callback.answer()


@router.message(NewListing.photo, F.photo)
async def got_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(NewListing.title)
    await message.answer("Принял фото 📸 Теперь название (5–80 символов), например: «Кофе с собой 100 ₽».")


@router.message(NewListing.photo, F.text)
async def skip_photo(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() not in SKIP_WORDS:
        await message.answer("Пришли фото или напиши «пропустить».")
        return
    await state.update_data(photo=None)
    await state.set_state(NewListing.title)
    await message.answer("Ок, без фото. Напиши название (5–80 символов).")


@router.message(NewListing.title, F.text)
async def got_title(message: Message, state: FSMContext) -> None:
    error = validate_title(message.text) or bad_word_error(message.text)
    if error:
        await message.answer(f"{error}\n\nПопробуй ещё:")
        return
    await state.update_data(title=" ".join(message.text.split()))
    await state.set_state(NewListing.description)
    await message.answer("Теперь описание: что именно, где и когда (10–600 символов).")


@router.message(NewListing.description, F.text)
async def got_description(message: Message, state: FSMContext) -> None:
    error = validate_description(message.text) or bad_word_error(message.text)
    if error:
        await message.answer(f"{error}\n\nПопробуй ещё:")
        return
    await state.update_data(description=" ".join(message.text.split()))
    await state.set_state(NewListing.price)
    await message.answer("Цена числом (например 200) или напиши «договорная».")


@router.message(NewListing.price, F.text)
async def got_price(message: Message, state: FSMContext) -> None:
    price, is_negotiable, error = parse_price(message.text)
    if error:
        await message.answer(f"{error}\n\nПопробуй ещё:")
        return
    await state.update_data(price=price, is_negotiable=is_negotiable)
    await state.set_state(NewListing.confirm)
    data = await state.get_data()
    await message.answer(_preview(data), reply_markup=keyboards.new_listing_confirm_kb())


@router.callback_query(NewListing.confirm, F.data == "nl:send")
async def confirm_send(
    callback: CallbackQuery, state: FSMContext, user, db: Database, bot: Bot, config: Config
) -> None:
    data = await state.get_data()
    await state.clear()
    outcome = await services.submit_listing(
        db,
        user=user,
        kind=data.get("kind", ""),
        category_code=data.get("category", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        price=data.get("price"),
        is_negotiable=bool(data.get("is_negotiable")),
        photo_file_id=data.get("photo"),
    )

    if outcome.status != "pending" or outcome.listing_id is None:
        if callback.message is not None:
            await callback.message.edit_text(
                f"❌ {outcome.reason or 'Не получилось.'}\n\nНачни заново: «{texts.BTN_NEW}»."
            )
        await callback.answer()
        return

    if callback.message is not None:
        await callback.message.edit_text(
            "✅ Объявление ушло на модерацию. Как только админ проверит — оно появится в каталоге."
        )
    await callback.answer()

    listing = await db.get_listing(outcome.listing_id)
    if listing is None:
        return
    await send_to_admins(
        bot,
        config,
        texts.moderation_card(listing),
        keyboards.moderation_kb(listing["id"]),
        photo=listing["photo_file_id"],
    )


@router.callback_query(F.data == "nl:cancel")
async def cancel_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Отменил. Ничего не опубликовано.")
    await callback.answer()


@router.message(StateFilter(None), F.text == texts.BTN_MY)
async def my_listings(message: Message, user, db: Database) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    rows = await db.list_user_listings(user["id"], ("active", "pending"))
    if not rows:
        await message.answer(
            f"Активных объявлений нет. Нажми «{texts.BTN_NEW}», чтобы выложить первое."
        )
        return
    pending = sum(1 for row in rows if row["status"] == "pending")
    header = f"Твои объявления ({len(rows)}):"
    if pending:
        header += f"\n⏳ На модерации: {pending}"
    await message.answer(header, reply_markup=keyboards.my_listings_kb(rows))


@router.callback_query(F.data.startswith("close:"))
async def close_listing(callback: CallbackQuery, user, db: Database) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    if listing["author_id"] != user["id"]:
        await callback.answer("Это не твоё объявление", show_alert=True)
        return
    await db.set_listing_status(listing_id, "archived")
    await db.log_event("listing_closed", user_id=user["id"], listing_id=listing_id)
    await callback.answer("Закрыл ✅", show_alert=True)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("bump:"))
async def request_bump(callback: CallbackQuery, user, db: Database, bot: Bot, config: Config) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None or listing["author_id"] != user["id"]:
        await callback.answer("Это не твоё объявление", show_alert=True)
        return
    await db.log_event("bump_requested", user_id=user["id"], listing_id=listing_id)
    await send_to_admins(
        bot,
        config,
        "⬆️ <b>Заявка на топ</b>\n\n"
        f"#{listing['id']} «{texts.escape(listing['title'])}»\n"
        f"👤 {texts.author_handle(listing['username'], listing['first_name'])}\n\n"
        f"tg://user?id={listing['author_tg_id']}",
        keyboards.admin_bump_kb(listing_id),
    )
    await callback.answer("Заявку отправил админу 👍", show_alert=True)
