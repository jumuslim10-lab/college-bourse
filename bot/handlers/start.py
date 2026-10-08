"""/start, правила, помощь, меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, services, texts
from bot.db import Database

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user, db: Database) -> None:
    await state.clear()

    # Deep-link вида t.me/<bot>?start=college-01 привязывает студента к площадке.
    code = services.parse_start_payload(message.text)
    if code:
        community, error = await services.join_community(db, user, code)
        if error:
            await message.answer(error)
        elif community is not None:
            await message.answer(
                texts.COMMUNITY_JOINED.format(title=texts.escape(community["title"]))
            )
            refreshed = await db.get_user_by_tg(user["tg_id"])
            if refreshed is not None:
                user = refreshed

    show_communities = await services.needs_community_switch(db)
    if user["agreed_at"]:
        await message.answer(
            texts.WELCOME_AGREED, reply_markup=keyboards.main_menu(show_communities)
        )
        return
    await message.answer(texts.RULES, reply_markup=keyboards.rules_kb(), disable_web_page_preview=True)


@router.callback_query(F.data == "rules:accept")
async def rules_accept(callback: CallbackQuery, user, db: Database) -> None:
    await db.set_agreed(user["tg_id"])
    if callback.message is not None:
        show_communities = await services.needs_community_switch(db)
        await callback.message.edit_text("✅ Правила приняты.")
        await callback.message.answer(
            texts.WELCOME_AGREED, reply_markup=keyboards.main_menu(show_communities)
        )
    await callback.answer()


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    await message.answer(texts.RULES, reply_markup=keyboards.rules_kb(), disable_web_page_preview=True)


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("menu"))
async def cmd_menu(message: Message, user, db: Database) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    show_communities = await services.needs_community_switch(db)
    await message.answer("Меню 👇", reply_markup=keyboards.main_menu(show_communities))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    show_communities = await services.needs_community_switch(db)
    await message.answer("Отменил. Меню ниже 👇", reply_markup=keyboards.main_menu(show_communities))


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
