"""Все тексты бота в одном месте."""

from __future__ import annotations

import html
from typing import Any

BTN_CATALOG = "🛒 Каталог"
BTN_NEW = "➕ Разместить"
BTN_MY = "📁 Мои объявления"
BTN_SEARCH = "🔍 Поиск"
BTN_HELP = "❓ Помощь"
BTN_COMMUNITIES = "🏢 Площадки"

# Валюта проекта: меняется тут одной строкой при выходе в другую страну.
CURRENCY = "сом"

KIND_LABELS = {"sell": "Продаю", "buy": "Куплю"}

RULES = (
    "📋 <b>Правила биржи колледжа</b>\n\n"
    "1. Бот — только витрина объявлений. <b>Деньги бот не держит и не переводит.</b> "
    "Никаких «гарантов» и посредников: договаривайтесь и рассчитывайтесь лично "
    "(наличные или перевод на номер телефона: MBank, O!Деньги, Balance).\n"
    "2. Максимум 3 активных объявления на человека. Новое объявление — не чаще 1 раза в 30 секунд.\n"
    "3. Еда — только фабричная упаковка или доставка от партнёра. Домашняя еда запрещена.\n"
    "4. Запрещено: скам, обман, 18+, продажа алкоголя и сигарет, «сделаю курсовую/диплом на заказ», "
    "любые услуги «гаранта» и переводы через третьих лиц.\n"
    "5. Отвечаешь за свой товар и свои слова сам. Администрация колледжа и бот ответственности не несут.\n"
    "6. Объявления сами уходят в архив: еда — через 1 день, услуги — через 7, вещи — через 14.\n\n"
    "Нажимая «Принимаю», ты соглашаешься с правилами."
)

HELP = (
    "❓ <b>Как пользоваться</b>\n\n"
    f"{BTN_NEW} — выложить объявление. После отправки его смотрит админ.\n"
    f"{BTN_CATALOG} — смотреть, что продают и покупают сейчас.\n"
    f"{BTN_MY} — свои объявления: закрыть или попросить топ.\n"
    f"{BTN_SEARCH} — поиск по словам.\n\n"
    "🤝 Когда договорился с человеком, нажми «Сделка состоялась» в карточке — так появится история и отзыв.\n"
    "🚩 Если кто-то обманывает или спамит — жми «Жалоба», разберёмся.\n\n"
    "Команды: /start, /rules, /help, /cancel"
)

WELCOME_AGREED = (
    "Ты в бирже колледжа. Смотри каталог или выкладывай своё.\n\n"
    "Выбери действие на клавиатуре ниже 👇"
)


def format_price(price: Any, is_negotiable: Any) -> str:
    if is_negotiable:
        return "договорная"
    if price is None:
        return "цена не указана"
    return f"{int(price)} {CURRENCY}"


def escape(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def author_handle(username: Any, first_name: Any) -> str:
    if username:
        return f"@{username}"
    return f"{escape(first_name or 'участник')} (без @username)"


def format_listing_card(listing: Any, *, include_author: bool = True) -> str:
    kind = KIND_LABELS.get(listing["kind"], listing["kind"])
    price = format_price(listing["price"], listing["is_negotiable"])
    lines = [
        f"<b>{kind}: {escape(listing['title'])}</b>",
        f"💰 {price}",
        "",
        escape(listing["description"]),
    ]
    if include_author:
        lines += ["", f"👤 {author_handle(listing['username'], listing['first_name'])}"]
        rating, count = rating_of(listing)
        if count:
            lines.append(f"⭐ {rating:.1f} ({count} отзыв(ов))")
    return "\n".join(lines)


def rating_of(row: Any) -> tuple[float, int]:
    try:
        rating_sum = int(row["rating_sum"] or 0)
        rating_count = int(row["rating_count"] or 0)
    except (KeyError, IndexError):
        return 0.0, 0
    if not rating_count:
        return 0.0, 0
    return rating_sum / rating_count, rating_count


def short_listing_line(row: Any) -> str:
    kind = KIND_LABELS.get(row["kind"], row["kind"])
    return f"• <b>{escape(row['title'])}</b> — {format_price(row['price'], row['is_negotiable'])} ({kind})"


def moderation_card(listing: Any) -> str:
    kind = KIND_LABELS.get(listing["kind"], listing["kind"])
    return (
        "🆕 <b>На модерации</b>\n\n"
        f"#{listing['id']} • {kind} • {escape(listing['title'])}\n"
        f"💰 {format_price(listing['price'], listing['is_negotiable'])}\n"
        f"📂 {escape(listing['category_code'])}\n\n"
        f"{escape(listing['description'])}\n\n"
        f"👤 {author_handle(listing['username'], listing['first_name'])}"
    )


# --- площадки ---------------------------------------------------------------
COMMUNITY_ALL_BUTTON = "🌍 Все площадки"
COMMUNITIES_EMPTY = (
    "🏢 Площадок пока нет — бот работает как одна площадка (твой колледж).\n"
    "Когда появится вторая, здесь можно будет переключаться."
)
COMMUNITIES_HEADER = "🏢 <b>Площадки</b>\n\nСейчас ты видишь: <b>{current}</b>\n\nВыбери площадку:"
COMMUNITY_SWITCHED = (
    "✅ Переключено на «<b>{title}</b>».\n\n"
    "Теперь в каталоге только объявления этой площадки."
)
COMMUNITY_SWITCHED_ALL = "🌍 Включён общий вид: показываю объявления всех площадок."
COMMUNITY_JOINED = (
    "✅ Ты на площадке «<b>{title}</b>». Каталог теперь показывает объявления только этой площадки."
)
COMMUNITY_NOT_FOUND = "Не нашёл площадку по этой ссылке. Возможно, код устарел — уточни у админа."
COMMUNITY_INACTIVE = "Эта площадка сейчас отключена."
COMMUNITY_OTHER = "Это объявление с другой площадки — открой каталог своей."
COMMUNITY_ON = "включена"
COMMUNITY_OFF = "выключена"

ADMIN_COMMUNITIES_EMPTY = (
    "🏫 <b>Площадки</b>\n\nПока ни одной: всё работает как одна площадка.\n"
    "Создай вторую кнопкой ниже — тогда появятся инвайт-ссылки."
)
ADMIN_COMMUNITIES_HEADER = (
    "🏫 <b>Площадки</b>\n\n{body}\n\nНажми на площадку, чтобы включить или выключить её."
)
ADMIN_COMMUNITY_ASK_CODE = (
    "Код новой площадки: латиница, цифры и дефис, 3–32 символа. "
    "Например: college-01 или obshaga-12. Пришли одним сообщением."
)
ADMIN_COMMUNITY_ASK_TITLE = "Название площадки, как её увидят студенты:"
ADMIN_COMMUNITY_ASK_CITY = "Город площадки:"
ADMIN_COMMUNITY_CREATED = (
    "✅ Площадка «<b>{title}</b>» создана.\n\n"
    "Инвайт-ссылка для студентов:\n{link}\n\n"
    "Отправь её в чат площадки — кто по ней зайдёт, сразу попадёт на неё."
)
ADMIN_COMMUNITY_TOGGLED = "Площадка «{title}»: {state}."


def community_label(row: Any) -> str:
    """«Колледж №12 (Бишкек)» — или только название, если город пуст."""
    title = escape(row["title"])
    city = (row["city"] or "").strip()
    return f"{title} ({escape(city)})" if city else title


def community_state(row: Any) -> str:
    return COMMUNITY_ON if row["is_active"] else COMMUNITY_OFF
