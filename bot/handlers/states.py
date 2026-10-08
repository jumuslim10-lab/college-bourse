"""Состояния FSM."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class NewListing(StatesGroup):
    kind = State()
    category = State()
    photo = State()
    title = State()
    description = State()
    price = State()
    confirm = State()


class Search(StatesGroup):
    query = State()


class Review(StatesGroup):
    rating = State()
    text = State()


class Report(StatesGroup):
    reason = State()


class ModerateReason(StatesGroup):
    reason = State()


class AdForm(StatesGroup):
    partner = State()
    text = State()
    days = State()


class Broadcast(StatesGroup):
    text = State()


class CommunityForm(StatesGroup):
    code = State()
    title = State()
    city = State()
