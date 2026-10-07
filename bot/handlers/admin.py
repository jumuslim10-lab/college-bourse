"""Админ-панель: модерация, жалобы, статистика, реклама, рассылка, баны."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, services, texts
from bot.db import Database
from bot.filters import IsAdmin
from bot.handlers.states import AdForm, Broadcast, ModerateReason
from bot.notify import notify_user
from bot.scheduler import broadcast

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _safe_edit(callback: CallbackQuery, text: str, markup=None) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=markup)


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    await message.answer("🛠 <b>Админ-панель</b>\nВыбери, что нужно:", reply_markup=keyboards.admin_menu_kb())


# --- модерация -------------------------------------------------------------
@router.callback_query(F.data == "admin:queue")
async def show_queue(callback: CallbackQuery, db: Database) -> None:
    rows = await db.list_pending()
    header = f"🗂 На модерации: {len(rows)}" if rows else "🗂 Очередь модерации пуста."
    await _safe_edit(callback, header, keyboards.admin_queue_kb(rows))
    await callback.answer()


@router.callback_query(F.data.startswith("mod:"))
async def open_for_moderation(callback: CallbackQuery, db: Database) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    card = texts.moderation_card(listing)
    markup = keyboards.moderation_kb(listing_id)
    if listing["photo_file_id"]:
        await callback.message.answer_photo(listing["photo_file_id"], caption=card[:1024], reply_markup=markup)
    else:
        await callback.message.answer(card, reply_markup=markup)


@router.callback_query(F.data.startswith("modok:"))
async def approve_listing(callback: CallbackQuery, db: Database, user, bot: Bot) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await services.activate_listing(db, listing_id, user["tg_id"])
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    await callback.answer("Опубликовано ✅")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
    await notify_user(
        bot,
        listing["author_tg_id"],
        f"✅ Твоё объявление «{texts.escape(listing['title'])}» опубликовано. "
        f"Живёт до авто-архива — продлить можно, выложив заново.",
    )


@router.callback_query(F.data.startswith("modno:"))
async def ask_reject_reason(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    await state.set_state(ModerateReason.reason)
    await state.update_data(listing_id=listing_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"⛔ Отклоняем «{texts.escape(listing['title'])}».\nПришли причину одним сообщением."
        )


@router.message(ModerateReason.reason, F.text)
async def do_reject(message: Message, state: FSMContext, db: Database, user, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    listing_id = int(data.get("listing_id", 0))
    reason = " ".join(message.text.split())[:300]
    listing = await services.reject_listing(db, listing_id, user["tg_id"], reason)
    if listing is None:
        await message.answer("Объявление не найдено.")
        return
    await message.answer("⛔ Отклонил.")
    await notify_user(
        bot,
        listing["author_tg_id"],
        f"⛔ Объявление «{texts.escape(listing['title'])}» не прошло модерацию.\nПричина: {texts.escape(reason)}",
    )


# --- жалобы ----------------------------------------------------------------
@router.callback_query(F.data == "admin:reports")
async def show_reports(callback: CallbackQuery, db: Database) -> None:
    rows = await db.list_open_reports()
    if not rows:
        await _safe_edit(callback, "🚩 Открытых жалоб нет.", keyboards.admin_menu_kb())
        await callback.answer()
        return
    lines = [
        f"#{row['id']} • объявление #{row['listing_id']} «{texts.escape(row['listing_title'] or '—')}»\n"
        f"   от {texts.author_handle(row['reporter_username'], '')}: {texts.escape(row['reason'][:120])}"
        for row in rows
    ]
    await _safe_edit(
        callback,
        "🚩 <b>Открытые жалобы</b>\n\n" + "\n\n".join(lines),
        keyboards.admin_reports_kb(rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("closereport:"))
async def close_report(callback: CallbackQuery, db: Database, user) -> None:
    report_id = int(callback.data.split(":")[1])
    await db.close_report(report_id, user["tg_id"])
    await callback.answer("Закрыл ✅")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)


# --- статистика ------------------------------------------------------------
@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery, db: Database) -> None:
    data = await db.stats(7)
    lines = [
        f"👥 Активных за 7 дней: {data['users_active']}",
        f"🆕 Объявлений создано за 7 дней: {data['listings_created']}",
        f"🛒 Активных объявлений сейчас: {data['listings_active']}",
        f"🤝 Закрытых сделок за 7 дней: {data['deals_done']} (всего {data['deals_total']})",
        f"👀 Показов контактов за 7 дней: {data['contacts_shown']}",
        f"🚩 Открытых жалоб: {data['reports_open']}",
    ]
    if data["category_counts"]:
        lines.append("\nПо разделам:")
        lines.extend(f"  • {code}: {count}" for code, count in data["category_counts"].items())
    await _safe_edit(callback, "📊 <b>Статистика</b>\n\n" + "\n".join(lines), keyboards.admin_menu_kb())
    await callback.answer()


# --- реклама ---------------------------------------------------------------
@router.callback_query(F.data == "admin:ad")
async def ad_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdForm.partner)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Название партнёра (для учёта, в пост не попадёт):")


@router.message(AdForm.partner, F.text)
async def ad_partner(message: Message, state: FSMContext) -> None:
    await state.update_data(partner=" ".join(message.text.split())[:60])
    await state.set_state(AdForm.text)
    await message.answer("Текст рекламного поста — его получат студенты:")


@router.message(AdForm.text, F.text)
async def ad_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text.strip()[:900])
    await state.set_state(AdForm.days)
    await message.answer("На сколько дней ставим рекламу? Пришли число (например 7).")


@router.message(AdForm.days, F.text)
async def ad_days(message: Message, state: FSMContext, db: Database, user) -> None:
    digits = "".join(ch for ch in message.text if ch.isdigit()) or "7"
    days = max(1, min(int(digits), 90))
    data = await state.get_data()
    await state.clear()
    ad_id = await db.create_ad(data.get("partner", "партнёр"), data.get("text", ""), days, 0, user["tg_id"])
    await message.answer(
        f"📣 <b>Превью</b> (дней: {days})\n\n{texts.escape(data.get('text'))}",
        reply_markup=keyboards.ad_publish_kb(ad_id),
    )


@router.callback_query(F.data.startswith("adpub:"))
async def ad_publish(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    ad_id = int(callback.data.split(":")[1])
    ad = await db.get_ad(ad_id)
    if ad is None:
        await callback.answer("Реклама не найдена", show_alert=True)
        return
    await db.set_ad_status(ad_id, "active")
    await callback.answer("Рассылаю…")
    delivered, failed = await broadcast(bot, db, ad["text"])
    if callback.message is not None:
        await callback.message.edit_text(
            f"📣 Реклама «{texts.escape(ad['partner_name'])}» запущена.\n"
            f"Доставлено: {delivered}, ошибок: {failed}."
        )


@router.callback_query(F.data.startswith("adskip:"))
async def ad_skip(callback: CallbackQuery, db: Database) -> None:
    ad_id = int(callback.data.split(":")[1])
    await db.set_ad_status(ad_id, "disabled")
    await callback.answer("Не публикуем")
    if callback.message is not None:
        await callback.message.edit_text("📣 Реклама сохранена как черновик, публиковать не стали.")


# --- рассылка --------------------------------------------------------------
@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Пришли текст рассылки одним сообщением.")


@router.message(Broadcast.text, F.text)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    text = message.text.strip()[:900]
    await state.update_data(text=text)
    await message.answer(
        f"Отправить всем активным за 30 дней?\n\n{texts.escape(text)}",
        reply_markup=keyboards.broadcast_kb(),
    )


@router.callback_query(F.data == "bc:send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    body = data.get("text")
    if not body:
        await callback.answer("Текст потерялся, начни заново", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_text("📤 Рассылаю…")
    delivered, failed = await broadcast(bot, db, body)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(f"📤 Доставлено: {delivered}, ошибок: {failed}.")


@router.callback_query(F.data == "bc:cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменил")
    if callback.message is not None:
        await callback.message.edit_text("Рассылка отменена.")


# --- топ и баны ------------------------------------------------------------
@router.callback_query(F.data.startswith("bumpok:"))
async def bump_ok(callback: CallbackQuery, db: Database, user, bot: Bot) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    await services.grant_bump(db, listing_id, user["tg_id"], services.BUMP_HOURS)
    await callback.answer("Топ выдан ⬆️")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
    await notify_user(
        bot,
        listing["author_tg_id"],
        f"⬆️ Твоё объявление «{texts.escape(listing['title'])}» поднято в топ на "
        f"{services.BUMP_HOURS} часа.",
    )


@router.callback_query(F.data.startswith("bumpno:"))
async def bump_no(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    await callback.answer("Отказал")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
    if listing is not None:
        await notify_user(bot, listing["author_tg_id"], "🚫 Топ пока не выдаём: сначала наберём оборот.")


@router.message(Command("ban"))
async def ban_user(message: Message, db: Database) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /ban @username или /ban 123456789")
        return
    target = await db.find_user(parts[1])
    if target is None:
        await message.answer("Не нашёл такого пользователя в базе.")
        return
    await db.set_banned(target["tg_id"], True)
    await message.answer(
        f"🚫 Забанен: {texts.author_handle(target['username'], target['first_name'])}"
    )


@router.message(Command("unban"))
async def unban_user(message: Message, db: Database) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /unban @username или /unban 123456789")
        return
    target = await db.find_user(parts[1])
    if target is None:
        await message.answer("Не нашёл такого пользователя в базе.")
        return
    await db.set_banned(target["tg_id"], False)
    await message.answer(
        f"✅ Разбанен: {texts.author_handle(target['username'], target['first_name'])}"
    )


@router.message(Command("stats"))
async def stats_command(message: Message, db: Database) -> None:
    data = await db.stats(7)
    await message.answer(
        "📊 <b>Статистика за 7 дней</b>\n\n"
        f"👥 Активных: {data['users_active']}\n"
        f"🆕 Объявлений: {data['listings_created']}\n"
        f"🛒 Активных сейчас: {data['listings_active']}\n"
        f"🤝 Сделок закрыто: {data['deals_done']}\n"
        f"👀 Контактов показано: {data['contacts_shown']}"
    )
