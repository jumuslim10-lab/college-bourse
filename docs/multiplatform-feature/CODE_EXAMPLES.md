# Примеры кода для копирования

Готовые фрагменты кода для быстрой реализации мультиплощадочности.

---

## 1. Клавиатура выбора площадок

**Файл:** `bot/keyboards.py`

Добавить в конец файла:

```python
def communities_kb(communities: list[tuple[Any, int]]) -> InlineKeyboardMarkup:
    """Клавиатура выбора площадки с количеством объявлений."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{c['title']} ({c['city']}) — {count} объявлений",
                callback_data=f"switch_community:{c['id']}",
            )
        ]
        for c, count in communities
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Площадок пока нет", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

---

## 2. Тексты

**Файл:** `bot/texts.py`

Найти строку с `BTN_HELP` и добавить после неё:

```python
BTN_COMMUNITIES = "🏢 Площадки"
```

---

## 3. Кнопка в главном меню

**Файл:** `bot/keyboards.py`, функция `main_menu()`

Заменить:

```python
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CATALOG), KeyboardButton(text=texts.BTN_NEW)],
            [KeyboardButton(text=texts.BTN_MY), KeyboardButton(text=texts.BTN_SEARCH)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
```

На:

```python
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CATALOG), KeyboardButton(text=texts.BTN_NEW)],
            [KeyboardButton(text=texts.BTN_MY), KeyboardButton(text=texts.BTN_SEARCH)],
            [KeyboardButton(text=texts.BTN_COMMUNITIES), KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
```

---

## 4. Хендлер переключения площадок

**Новый файл:** `bot/handlers/communities.py`

Создать файл со следующим содержимым:

```python
"""Хендлеры переключения площадок."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiosqlite import Row

from bot import keyboards, texts
from bot.db import Database

router = Router(name="communities")


@router.message(F.text == texts.BTN_COMMUNITIES)
async def show_communities(message: Message, user: Row, db: Database) -> None:
    """Показать список доступных площадок."""
    communities = await db.list_active_communities()
    
    if not communities:
        await message.answer("🏢 Площадок пока нет. Скоро появятся новые!")
        return
    
    # Подсчитать объявления для каждой площадки
    comm_with_counts = []
    for c in communities:
        count = await db.count_community_listings(c["id"], status="active")
        comm_with_counts.append((c, count))
    
    current_community = user["community_id"]
    current_name = "не выбрана"
    
    if current_community:
        community = await db.get_community(current_community)
        if community:
            current_name = community["title"]
    
    await message.answer(
        f"🏢 Текущая площадка: {current_name}\n\nВыбери площадку:",
        reply_markup=keyboards.communities_kb(comm_with_counts),
    )


@router.callback_query(F.data.startswith("switch_community:"))
async def switch_community(callback: CallbackQuery, user: Row, db: Database) -> None:
    """Переключить пользователя на другую площадку."""
    if callback.data is None:
        await callback.answer("Ошибка данных")
        return
    
    community_id = int(callback.data.split(":")[1])
    await db.set_user_community(user["id"], community_id)
    
    community = await db.get_community(community_id)
    if community:
        await callback.message.answer(
            f"✅ Переключено на площадку: {community['title']} ({community['city']})\n\n"
            "Теперь ты видишь только объявления этой площадки."
        )
    
    await callback.answer()
```

---

## 5. Регистрация роутера

**Файл:** `bot/handlers/__init__.py`

Найти строку:

```python
from bot.handlers import admin, catalog, deals, listing, report, start
```

Заменить на:

```python
from bot.handlers import admin, catalog, communities, deals, listing, report, start
```

Найти:

```python
ALL_ROUTERS = [
    start.router,
    listing.router,
    catalog.router,
    deals.router,
    report.router,
    admin.router,
]
```

Заменить на:

```python
ALL_ROUTERS = [
    start.router,
    listing.router,
    catalog.router,
    deals.router,
    report.router,
    communities.router,
    admin.router,
]
```

---

## 6. Обновление create_listing

**Файл:** `bot/db.py`, метод `create_listing()`

Найти:

```python
async def create_listing(
    self,
    *,
    author_id: int,
    kind: str,
    category_code: str,
    title: str,
    description: str,
    price: int | None,
    is_negotiable: bool,
    photo_file_id: str | None,
    status: str,
    reject_reason: str | None = None,
) -> int:
```

Заменить на:

```python
async def create_listing(
    self,
    *,
    author_id: int,
    community_id: int | None = None,
    kind: str,
    category_code: str,
    title: str,
    description: str,
    price: int | None,
    is_negotiable: bool,
    photo_file_id: str | None,
    status: str,
    reject_reason: str | None = None,
) -> int:
```

Найти строку:

```python
INSERT INTO listings(
    author_id, kind, category_code, title, description, search_text, price,
    is_negotiable, photo_file_id, status, created_at, reject_reason
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

Заменить на:

```python
INSERT INTO listings(
    author_id, community_id, kind, category_code, title, description, search_text, price,
    is_negotiable, photo_file_id, status, created_at, reject_reason
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

Найти:

```python
(
    author_id,
    kind,
    category_code,
    title,
    description,
    search_key(title, description),
    price,
    int(is_negotiable),
    photo_file_id,
    status,
    now_iso(),
    reject_reason,
),
```

Заменить на:

```python
(
    author_id,
    community_id,
    kind,
    category_code,
    title,
    description,
    search_key(title, description),
    price,
    int(is_negotiable),
    photo_file_id,
    status,
    now_iso(),
    reject_reason,
),
```

---

## 7. Обновление submit_listing

**Файл:** `bot/services.py`, функция `submit_listing()`

Найти вызов `db.create_listing`:

```python
listing_id = await db.create_listing(
    author_id=user["id"],
    kind=kind,
    category_code=category_code,
    title=title,
    description=description,
    price=price,
    is_negotiable=is_negotiable,
    photo_file_id=photo_file_id,
    status=status,
    reject_reason=reject_reason,
)
```

Заменить на:

```python
listing_id = await db.create_listing(
    author_id=user["id"],
    community_id=user["community_id"],
    kind=kind,
    category_code=category_code,
    title=title,
    description=description,
    price=price,
    is_negotiable=is_negotiable,
    photo_file_id=photo_file_id,
    status=status,
    reject_reason=reject_reason,
)
```

---

## 8. Фильтрация list_active по площадке

**Файл:** `bot/db.py`, метод `list_active()`

Найти:

```python
async def list_active(
    self, category_code: str, page: int = 0
) -> tuple[list[aiosqlite.Row], int]:
```

Заменить на:

```python
async def list_active(
    self, category_code: str, page: int = 0, community_id: int | None = None
) -> tuple[list[aiosqlite.Row], int]:
```

Найти:

```python
WHERE l.status = 'active' AND l.category_code = ?
```

Заменить на:

```python
WHERE l.status = 'active' AND l.category_code = ?
    AND (? IS NULL OR l.community_id = ?)
```

Найти все вызовы с параметрами, например:

```python
(category_code,)
```

Заменить на:

```python
(category_code, community_id, community_id)
```

И для запроса COUNT тоже:

```python
(category_code, community_id, community_id)
```

---

## 9. Обновление category_counts

**Файл:** `bot/db.py`, метод `category_counts()`

Найти:

```python
async def category_counts(self) -> dict[str, int]:
```

Заменить на:

```python
async def category_counts(self, community_id: int | None = None) -> dict[str, int]:
```

Найти:

```python
WHERE status = 'active'
```

Заменить на:

```python
WHERE status = 'active' AND (? IS NULL OR community_id = ?)
```

Найти параметры запроса (пустой кортеж `()`):

```python
async with self.conn.execute(
    """
    SELECT category_code, COUNT(*) AS amount
    FROM listings
    WHERE status = 'active' AND (? IS NULL OR community_id = ?)
    GROUP BY category_code
    """,
    (),  # <-- найти это
) as cursor:
```

Заменить на:

```python
(community_id, community_id),
```

---

## 10. Обновление search_listings

**Файл:** `bot/db.py`, метод `search_listings()`

Найти:

```python
async def search_listings(self, query: str, limit: int = 10) -> list[aiosqlite.Row]:
```

Заменить на:

```python
async def search_listings(
    self, query: str, limit: int = 10, community_id: int | None = None
) -> list[aiosqlite.Row]:
```

Найти:

```python
WHERE l.status = 'active' AND l.search_text LIKE ?
```

Заменить на:

```python
WHERE l.status = 'active' AND l.search_text LIKE ?
    AND (? IS NULL OR l.community_id = ?)
```

Найти:

```python
(f"%{normalize(query).lower()}%",),
```

Заменить на:

```python
(f"%{normalize(query).lower()}%", community_id, community_id),
```

---

## 11. Обновление хендлеров каталога

**Файл:** `bot/handlers/catalog.py`

Найти все вызовы:
- `db.list_active(code, page)` → `db.list_active(code, page, user["community_id"])`
- `db.category_counts()` → `db.category_counts(user["community_id"])`
- `db.search_listings(query)` → `db.search_listings(query, community_id=user["community_id"])`

---

## 12. Тесты

**Файл:** `tests/test_db.py`

Добавить в конец файла:

```python
async def test_community_creation(db: Database) -> None:
    """Создание площадки."""
    cid = await db.create_community("college-01", "Колледж №1", "Бишкек")
    community = await db.get_community(cid)
    assert community is not None
    assert community["code"] == "college-01"
    assert community["title"] == "Колледж №1"
    assert community["city"] == "Бишкек"
    assert community["is_active"] == 1


async def test_community_by_code(db: Database) -> None:
    """Получение площадки по коду."""
    await db.create_community("college-02", "Колледж №2", "Ош")
    community = await db.get_community_by_code("college-02")
    assert community is not None
    assert community["title"] == "Колледж №2"


async def test_user_community_binding(db: Database) -> None:
    """Привязка пользователя к площадке."""
    cid = await db.create_community("college-03", "Колледж №3", "Ош")
    user = await db.upsert_user(12345, "testuser", "Test")
    
    await db.set_user_community(user["id"], cid)
    updated = await db.get_user(user["id"])
    assert updated["community_id"] == cid


async def test_listing_community_filter(db: Database) -> None:
    """Фильтрация объявлений по площадке."""
    # Создать две площадки
    c1 = await db.create_community("college-04", "Колледж №4", "Бишкек")
    c2 = await db.create_community("college-05", "Колледж №5", "Ош")
    
    # Создать пользователей
    u1 = await db.upsert_user(11111, "user1", "User1")
    u2 = await db.upsert_user(22222, "user2", "User2")
    await db.set_user_community(u1["id"], c1)
    await db.set_user_community(u2["id"], c2)
    
    # Создать объявления
    l1 = await db.create_listing(
        author_id=u1["id"],
        community_id=c1,
        kind="sell",
        category_code="goods",
        title="Книга из площадки 1",
        description="Описание",
        price=100,
        is_negotiable=False,
        photo_file_id=None,
        status="active",
    )
    
    l2 = await db.create_listing(
        author_id=u2["id"],
        community_id=c2,
        kind="sell",
        category_code="goods",
        title="Книга из площадки 2",
        description="Описание",
        price=200,
        is_negotiable=False,
        photo_file_id=None,
        status="active",
    )
    
    # Проверить фильтрацию
    listings_c1, _ = await db.list_active("goods", 0, community_id=c1)
    listings_c2, _ = await db.list_active("goods", 0, community_id=c2)
    
    assert len(listings_c1) == 1
    assert len(listings_c2) == 1
    assert listings_c1[0]["id"] == l1
    assert listings_c2[0]["id"] == l2
```

---

## Проверка после применения всех изменений

```powershell
# Перейти в проект
cd C:\Users\User\Documents\deepseek-harness\default-workspace\college-bourse

# Запустить тесты
.venv\Scripts\python.exe -m pytest -q

# Проверить линтер
.venv\Scripts\python.exe -m ruff check .

# Запустить бота
.venv\Scripts\python.exe run.py
```

Все тесты должны быть зелёными ✅
