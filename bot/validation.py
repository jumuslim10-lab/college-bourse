"""Проверка пользовательского ввода и автофильтр запрещённых объявлений."""

from __future__ import annotations

import re

TITLE_MIN, TITLE_MAX = 5, 80
DESCRIPTION_MIN, DESCRIPTION_MAX = 10, 600
PRICE_MAX = 100_000

NEGOTIABLE_WORDS = {"договорная", "договор", "дог", "торг", "по договору"}

# Регулярки, а не подстроки: нужно ловить «гарант», но не «гарантия».
BAD_WORD_PATTERNS: tuple[str, ...] = (
    r"\bскам",
    r"\bобнал",
    r"\bзакладк",
    r"\bнарко",
    r"\bпорно",
    r"\bинтим",
    r"\bказино",
    r"\bставки на спорт",
    r"\bдиплом на заказ",
    r"\bкурсовую на заказ",
    r"\bконтрольную на заказ",
    r"\b18\+",
    r"\bгарант(?!и)",
)

_BAD_WORD_REGEXES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pattern, re.compile(pattern, re.IGNORECASE)) for pattern in BAD_WORD_PATTERNS
)


def normalize(text: str) -> str:
    return " ".join((text or "").split())


def find_bad_word(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        for pattern, regex in _BAD_WORD_REGEXES:
            if regex.search(text):
                return pattern
    return None


def validate_title(text: str) -> str | None:
    """Только структура: длину и пустоту. Запрещённые слова ловит submit_listing."""
    value = normalize(text)
    if len(value) < TITLE_MIN:
        return f"Название слишком короткое — минимум {TITLE_MIN} символов."
    if len(value) > TITLE_MAX:
        return f"Название слишком длинное — максимум {TITLE_MAX} символов."
    return None


def validate_description(text: str) -> str | None:
    """Только структура: длину и пустоту. Запрещённые слова ловит submit_listing."""
    value = normalize(text)
    if len(value) < DESCRIPTION_MIN:
        return f"Описание слишком короткое — минимум {DESCRIPTION_MIN} символов."
    if len(value) > DESCRIPTION_MAX:
        return f"Описание слишком длинное — максимум {DESCRIPTION_MAX} символов."
    return None


def bad_word_error(*texts: str) -> str | None:
    """Текст ошибки для быстрой подсказки на шаге ввода."""
    bad_word = find_bad_word(*texts)
    if bad_word:
        return "Такую формулировку размещать нельзя (запрещено правилами). Переформулируй."
    return None


def parse_price(raw: str) -> tuple[int | None, bool, str | None]:
    """Возвращает (цена, договорная, ошибка)."""
    value = normalize(raw).lower()
    if not value:
        return None, False, "Пришли цену числом (например 200) или напиши «договорная»."
    if value in NEGOTIABLE_WORDS or "договор" in value:
        return None, True, None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None, False, "Не понял цену. Пришли число (например 200) или «договорная»."
    price = int(digits)
    if price <= 0:
        return None, False, "Цена должна быть больше нуля, либо напиши «договорная»."
    if price > PRICE_MAX:
        return None, False, f"Слишком большая цена. Максимум {PRICE_MAX} ₽."
    return price, False, None
