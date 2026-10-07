"""Роутеры бота."""

from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, catalog, deals, listing, report, start

ALL_ROUTERS: tuple[Router, ...] = (
    start.router,
    listing.router,
    catalog.router,
    deals.router,
    report.router,
    admin.router,
)
