"""Роутеры бота."""

from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, catalog, communities, deals, listing, report, start

ALL_ROUTERS: tuple[Router, ...] = (
    start.router,
    listing.router,
    catalog.router,
    deals.router,
    report.router,
    communities.router,
    admin.router,
)
