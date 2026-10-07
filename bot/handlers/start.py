"""/start, правила, помощь, меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.db import Database

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user, db: Database) -> None:
    await state.clear()
    if user["agreed_at"]:
        await message.answer(texts.WELCOME_AGREED, reply_markup=keyboards.main_menu())
        return
    await message.answer(texts.RULES, reply_markup=keyboards.rules_kb(), disable_web_page_preview=True)


@router.callback_query(F.data == "rules:accept")
async def rules_accept(callback: CallbackQuery, user, db: Database) -> None:
    await db.set_agreed(user["tg_id"])
    if callback.message is not None:
        await callback.message.edit_text("✅ Правила приняты.")
        await callback.message.answer(texts.WELCOME_AGREED, reply_markup=keyboards.main_menu())
    await callback.answer()


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    await message.answer(texts.RULES, reply_markup=keyboards.rules_kb(), disable_web_page_preview=True)


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("menu"))
async def cmd_menu(message: Message, user) -> None:
    if not user["agreed_at"]:
        await message.answer("Сначала прими правила: /start")
        return
    await message.answer("Меню 👇", reply_markup=keyboards.main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил. Меню ниже 👇", reply_markup=keyboards.main_menu())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
