"""Выбор и переключение площадок (колледжей)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.db import Database

router = Router(name="communities")


@router.message(StateFilter(None), F.text == texts.BTN_COMMUNITIES)
async def show_communities(message: Message, user, db: Database) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return

    communities = await db.list_communities_with_counts(active_only=True)
    if not communities:
        await message.answer(texts.COMMUNITIES_EMPTY)
        return

    current = "все площадки"
    if user["community_id"] is not None:
        row = await db.get_community(user["community_id"])
        if row is not None:
            current = texts.community_label(row)
    await message.answer(
        texts.COMMUNITIES_HEADER.format(current=current),
        reply_markup=keyboards.communities_kb(communities, user["community_id"]),
    )


@router.callback_query(F.data.startswith("switch_community:"))
async def switch_community(callback: CallbackQuery, user, db: Database) -> None:
    parts = (callback.data or "").split(":")
    try:
        community_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Не понял, какая площадка", show_alert=True)
        return

    # 0 — общий вид: снова видно объявления всех площадок.
    if community_id == 0:
        await db.set_user_community(user["id"], None)
        await db.log_event("community_switched", user_id=user["id"], meta="all")
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(texts.COMMUNITY_SWITCHED_ALL)
        return

    community = await db.get_community(community_id)
    if community is None or not community["is_active"]:
        await callback.answer(texts.COMMUNITY_INACTIVE, show_alert=True)
        return

    await db.set_user_community(user["id"], community_id)
    await db.log_event("community_switched", user_id=user["id"], meta=community["code"])
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            texts.COMMUNITY_SWITCHED.format(title=texts.escape(community["title"]))
        )
