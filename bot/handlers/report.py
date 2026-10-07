"""Жалобы на объявления."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.handlers.states import Report
from bot.notify import send_to_admins

router = Router(name="report")


@router.callback_query(F.data.startswith("report:"))
async def start_report(callback: CallbackQuery, state: FSMContext, db: Database, user) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None:
        await callback.answer("Объявление не найдено", show_alert=True)
        return
    await state.set_state(Report.reason)
    await state.update_data(listing_id=listing_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"🚩 Жалоба на «{texts.escape(listing['title'])}».\n\n"
            "Опиши одним сообщением, что не так (обман, спам, запрещённый товар)."
        )


@router.message(Report.reason, F.text)
async def submit_report(
    message: Message, state: FSMContext, db: Database, user, bot: Bot, config: Config
) -> None:
    data = await state.get_data()
    await state.clear()
    listing_id = data.get("listing_id")
    reason = " ".join(message.text.split())[:500]
    if len(reason) < 5:
        await message.answer("Слишком коротко: опиши проблему хотя бы в 5 символах.")
        return

    report_id = await db.create_report(listing_id, user["id"], reason)
    await db.log_event("report_created", user_id=user["id"], listing_id=listing_id)
    await message.answer("🚩 Жалобу отправил админу. Спасибо!")

    listing = await db.get_listing(int(listing_id)) if listing_id else None
    title = texts.escape(listing["title"]) if listing else "—"
    await send_to_admins(
        bot,
        config,
        f"🚩 <b>Жалоба #{report_id}</b>\n\n"
        f"Объявление: #{listing_id} «{title}»\n"
        f"От: {texts.author_handle(user['username'], user['first_name'])}\n\n"
        f"{texts.escape(reason)}",
        reply_markup=_close_report_kb(report_id),
    )


def _close_report_kb(report_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Обработано", callback_data=f"closereport:{report_id}")]
        ]
    )
