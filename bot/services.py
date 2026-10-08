"""Бизнес-логика биржи: публикация объявлений, модерация, топ, дайджест."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bot import texts
from bot.categories import CATEGORIES, Category, get_category, is_visible, ttl_days
from bot.db import Database, iso_in_days, iso_in_hours
from bot.validation import find_bad_word, validate_description, validate_title

MAX_ACTIVE_PER_USER = 3
RATE_LIMIT_SECONDS = 30
BUMP_HOURS = 24

# Код площадки: латиница/цифры/дефис, 3–32 символа, без дефиса на концах.
COMMUNITY_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
COMMUNITY_CODE_MIN, COMMUNITY_CODE_MAX = 3, 32


def normalize_community_code(raw: str) -> str:
    return "-".join((raw or "").strip().lower().split())


def is_valid_community_code(code: str) -> bool:
    return (
        COMMUNITY_CODE_MIN <= len(code) <= COMMUNITY_CODE_MAX
        and COMMUNITY_CODE_RE.match(code) is not None
    )


def parse_start_payload(raw: str | None) -> str | None:
    """Код площадки из deep-link «/start college-01» (или /start@bot college-01)."""
    if not raw:
        return None
    parts = raw.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip().lower()
    return payload or None


def can_view_community(user_community: int | None, listing_community: int | None) -> bool:
    """Правило видимости: «общий вид» (площадка не выбрана) видит всё; площадка — только своё.

    Объявления без площадки (созданные до мультиплощадочности) остаются в общем пуле.
    Первая созданная площадка забирает этот пул себе — см. create_community.
    """
    if user_community is None:
        return True
    return user_community == listing_community


@dataclass
class SubmitOutcome:
    status: str  # 'pending' | 'rejected' | 'invalid'
    listing_id: int | None = None
    reason: str | None = None


def visible_categories(counts: dict[str, int], bootstrap: bool) -> list[tuple[Category, int]]:
    result = []
    for category in CATEGORIES:
        count = counts.get(category.code, 0)
        if is_visible(count, bootstrap):
            result.append((category, count))
    return result


async def category_menu(
    db: Database, bootstrap: bool, community_id: int | None = None
) -> list[tuple[Category, int]]:
    return visible_categories(await db.category_counts(community_id), bootstrap)


async def submit_listing(
    db: Database,
    *,
    user: Any,
    kind: str,
    category_code: str,
    title: str,
    description: str,
    price: int | None,
    is_negotiable: bool,
    photo_file_id: str | None,
) -> SubmitOutcome:
    """Проверяет объявление и создаёт его в статусе pending либо rejected."""
    if kind not in {"sell", "buy"}:
        return SubmitOutcome("invalid", reason="Не понял тип объявления. Начни заново.")
    if get_category(category_code) is None:
        return SubmitOutcome("invalid", reason="Не понял категорию. Начни заново.")

    for error in (validate_title(title), validate_description(description)):
        if error:
            return SubmitOutcome("invalid", reason=error)

    if await db.count_active_by_user(user["id"]) >= MAX_ACTIVE_PER_USER:
        return SubmitOutcome(
            "invalid",
            reason=(
                f"У тебя уже {MAX_ACTIVE_PER_USER} активных объявления — это лимит. "
                "Закрой что-нибудь в «Мои объявления» и попробуй снова."
            ),
        )

    if await db.count_listings_since(user["id"], RATE_LIMIT_SECONDS):
        return SubmitOutcome(
            "invalid", reason=f"Слишком часто: следующее объявление можно через {RATE_LIMIT_SECONDS} секунд."
        )

    normalized_title = " ".join(title.split())
    normalized_description = " ".join(description.split())

    bad_word = find_bad_word(normalized_title, normalized_description)
    if bad_word:
        listing_id = await db.create_listing(
            author_id=user["id"],
            community_id=user["community_id"],
            kind=kind,
            category_code=category_code,
            title=normalized_title,
            description=normalized_description,
            price=price,
            is_negotiable=is_negotiable,
            photo_file_id=photo_file_id,
            status="rejected",
            reject_reason=f"автофильтр: {bad_word}",
        )
        return SubmitOutcome(
            "rejected",
            listing_id=listing_id,
            reason="Объявление отклонено автофильтром: такие формулировки запрещены правилами.",
        )

    listing_id = await db.create_listing(
        author_id=user["id"],
        community_id=user["community_id"],
        kind=kind,
        category_code=category_code,
        title=normalized_title,
        description=normalized_description,
        price=price,
        is_negotiable=is_negotiable,
        photo_file_id=photo_file_id,
        status="pending",
    )
    await db.log_event("listing_submitted", user_id=user["id"], listing_id=listing_id)
    return SubmitOutcome("pending", listing_id=listing_id)


async def activate_listing(db: Database, listing_id: int, admin_tg_id: int) -> Any:
    listing = await db.get_listing(listing_id)
    if listing is None:
        return None
    await db.set_listing_status(
        listing_id,
        "active",
        expires_at=iso_in_days(ttl_days(listing["category_code"])),
        moderated_by=admin_tg_id,
    )
    await db.log_event("listing_activated", listing_id=listing_id, user_id=admin_tg_id)
    return await db.get_listing(listing_id)


async def reject_listing(db: Database, listing_id: int, admin_tg_id: int, reason: str) -> Any:
    listing = await db.get_listing(listing_id)
    if listing is None:
        return None
    await db.set_listing_status(
        listing_id, "rejected", reject_reason=reason, moderated_by=admin_tg_id
    )
    await db.log_event("listing_rejected", listing_id=listing_id, user_id=admin_tg_id, meta=reason)
    return await db.get_listing(listing_id)


async def grant_bump(
    db: Database, listing_id: int, admin_tg_id: int, hours: int = BUMP_HOURS, amount: int = 0
) -> None:
    paid_until = iso_in_hours(hours)
    await db.bump_listing(listing_id, paid_until)
    await db.add_promotion(listing_id, paid_until, amount, admin_tg_id)
    await db.log_event("bump_granted", listing_id=listing_id, user_id=admin_tg_id)


async def build_digest(db: Database, limit: int = 5, community_id: int | None = None) -> str | None:
    counts = await db.category_counts(community_id)
    lines: list[str] = []
    for category, count in visible_categories(counts, bootstrap=True):
        if not count:
            continue
        listings = await db.list_active(category.code, limit=limit, community_id=community_id)
        if not listings:
            continue
        lines.append(f"{category.emoji} <b>{category.title}</b>")
        lines.extend(texts.short_listing_line(row) for row in listings)
        lines.append("")
    if not lines:
        return None
    return "☀️ <b>Сегодня на бирже</b>\n\n" + "\n".join(lines).strip()


# --- площадки ---------------------------------------------------------------
async def create_community(
    db: Database, *, code: str, title: str, city: str
) -> tuple[int | None, str | None]:
    """Создаёт площадку. Возвращает (id, текст ошибки)."""
    normalized = normalize_community_code(code)
    if not is_valid_community_code(normalized):
        return None, (
            "Код не подошёл: латиница, цифры и дефис, 3–32 символа, "
            "без дефиса на концах. Например: college-01."
        )
    clean_title = " ".join((title or "").split())[:80]
    clean_city = " ".join((city or "").split())[:60]
    if len(clean_title) < 3:
        return None, "Название слишком короткое — напиши, как площадку увидят студенты."
    if not clean_city:
        return None, "Укажи город — он виден студентам в списке площадок."
    if await db.get_community_by_code(normalized) is not None:
        return None, "Площадка с таким кодом уже есть — придумай другой."
    is_first = not await db.list_communities_with_counts()
    community_id = await db.create_community(normalized, clean_title, clean_city)
    if is_first:
        # Первая площадка забирает общий пул: иначе после её появления у студентов
        # «пропали» бы все старые объявления и они бы не нашли свою витрину.
        await db.adopt_unassigned(community_id)
    return community_id, None


async def join_community(db: Database, user: Any, code: str) -> tuple[Any | None, str | None]:
    """Привязывает пользователя к площадке по коду из инвайт-ссылки."""
    normalized = normalize_community_code(code)
    if not normalized:
        return None, texts.COMMUNITY_NOT_FOUND
    community = await db.get_community_by_code(normalized)
    if community is None:
        return None, texts.COMMUNITY_NOT_FOUND
    if not community["is_active"]:
        return None, texts.COMMUNITY_INACTIVE
    await db.set_user_community(user["id"], community["id"])
    await db.log_event("community_joined", user_id=user["id"], meta=normalized)
    return community, None


async def needs_community_switch(db: Database) -> bool:
    """Кнопка «Площадки» нужна только когда площадок реально больше одной."""
    return len(await db.list_active_communities()) > 1
