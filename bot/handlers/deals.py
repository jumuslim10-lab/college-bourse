"""Сделки и отзывы."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, services, texts
from bot.db import Database
from bot.handlers.states import Review

router = Router(name="deals")


async def _notify(bot: Bot, tg_id: int, text: str, markup=None) -> None:
    try:
        await bot.send_message(tg_id, text, reply_markup=markup)
    except TelegramAPIError:
        pass


@router.callback_query(F.data.startswith("deal:"))
async def start_deal(callback: CallbackQuery, db: Database, user, bot: Bot) -> None:
    listing_id = int(callback.data.split(":")[1])
    listing = await db.get_listing(listing_id)
    if listing is None or listing["status"] != "active":
        await callback.answer("Объявление уже неактуально", show_alert=True)
        return
    if not services.can_view_community(user["community_id"], listing["community_id"]):
        await callback.answer(texts.COMMUNITY_OTHER, show_alert=True)
        return
    if listing["author_id"] == user["id"]:
        await callback.answer("Это твоё объявление 🙂", show_alert=True)
        return

    deal_id = await db.create_deal(listing_id, user["id"], listing["author_id"])
    await db.log_event("deal_created", user_id=user["id"], listing_id=listing_id)
    await callback.answer("Отметил 🤝")

    await _notify(
        bot,
        listing["author_tg_id"],
        f"🤝 <b>{texts.escape(user['first_name'] or 'Кто-то')}</b> отмечает сделку по "
        f"«{texts.escape(listing['title'])}».\n\nПодтверди, когда всё сделано — тогда откроются отзывы.",
        keyboards.deal_seller_kb(deal_id),
    )
    if callback.message is not None:
        await callback.message.answer(
            "Передал автору 👍 Как только он подтвердит выполнение, вы оба сможете оставить отзыв."
        )


@router.callback_query(F.data.startswith("done:"))
async def confirm_done(callback: CallbackQuery, db: Database, user, bot: Bot) -> None:
    deal_id = int(callback.data.split(":")[1])
    deal = await db.get_deal(deal_id)
    if deal is None:
        await callback.answer("Сделка не найдена", show_alert=True)
        return
    if user["id"] != deal["seller_id"]:
        await callback.answer("Подтвердить может только автор объявления", show_alert=True)
        return
    if deal["status"] == "done":
        await callback.answer("Уже подтверждено", show_alert=True)
        return

    await db.set_deal_status(deal_id, "done")
    await db.log_event("deal_done", user_id=user["id"], listing_id=deal["listing_id"])
    await callback.answer("Сделка закрыта ✅")

    buyer = await db.get_user(deal["buyer_id"])
    if buyer is not None:
        await _notify(
            bot,
            buyer["tg_id"],
            "✅ Сделка закрыта. Поставь отзыв — это главная защита от обмана в бирже.",
            keyboards.review_start_kb(deal_id),
        )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "✅ Записал. Ты тоже можешь оставить отзыв.",
            reply_markup=keyboards.review_start_kb(deal_id),
        )


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_deal(callback: CallbackQuery, db: Database, user, bot: Bot) -> None:
    deal_id = int(callback.data.split(":")[1])
    deal = await db.get_deal(deal_id)
    if deal is None or user["id"] != deal["seller_id"]:
        await callback.answer("Не получится", show_alert=True)
        return
    await db.set_deal_status(deal_id, "cancelled")
    await callback.answer("Отменил")
    buyer = await db.get_user(deal["buyer_id"])
    if buyer is not None:
        await _notify(bot, buyer["tg_id"], "🚫 Автор отметил, что сделка не состоялась.")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("review:"))
async def start_review(callback: CallbackQuery, state: FSMContext, db: Database, user) -> None:
    deal_id = int(callback.data.split(":")[1])
    deal = await db.get_deal(deal_id)
    if deal is None or deal["status"] != "done":
        await callback.answer("Отзыв можно оставить только по закрытой сделке", show_alert=True)
        return
    if user["id"] not in (deal["buyer_id"], deal["seller_id"]):
        await callback.answer("Это не твоя сделка", show_alert=True)
        return
    if await db.has_review(deal_id, user["id"]):
        await callback.answer("Ты уже оставил отзыв по этой сделке", show_alert=True)
        return

    await state.set_state(Review.rating)
    await state.update_data(deal_id=deal_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Оцени от 1 до 5:", reply_markup=keyboards.review_stars_kb(deal_id))


@router.callback_query(Review.rating, F.data.startswith("rate:"))
async def review_rating(callback: CallbackQuery, state: FSMContext) -> None:
    _, deal_id, rating = callback.data.split(":")
    await state.update_data(deal_id=int(deal_id), rating=int(rating))
    await state.set_state(Review.text)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Оценка: {rating}⭐\nТеперь напиши пару слов (или «-», чтобы без текста)."
        )


@router.message(Review.text, F.text)
async def review_text(message: Message, state: FSMContext, db: Database, user, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    deal = await db.get_deal(int(data.get("deal_id", 0)))
    if deal is None:
        await message.answer("Сделка не найдена, начни отзыв заново.")
        return
    if await db.has_review(deal["id"], user["id"]):
        await message.answer("Ты уже оставил отзыв по этой сделке.")
        return

    target_id = deal["seller_id"] if user["id"] == deal["buyer_id"] else deal["buyer_id"]
    raw = message.text.strip()
    review_body = None if raw in {"-", "нет", "пропустить"} else raw[:300]
    created = await db.create_review(deal["id"], user["id"], target_id, int(data.get("rating", 5)), review_body)
    if not created:
        await message.answer("Отзыв уже был сохранён.")
        return

    await message.answer("Спасибо! Отзыв сохранён ⭐")
    target = await db.get_user(target_id)
    if target is not None:
        await _notify(
            bot,
            target["tg_id"],
            f"⭐ Тебе поставили оценку {data.get('rating')}/5 по сделке.\n"
            + (f"«{texts.escape(review_body)}»" if review_body else ""),
        )
