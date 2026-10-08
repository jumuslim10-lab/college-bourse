# Quick Start для следующего ИИ-агента

## Контекст
Проект: Telegram-бот «Биржа колледжа» (Кыргызстан)  
Задача: Добавление мультиплощадочности (возможность работы на нескольких колледжах)

## Что уже сделано
✅ Таблица `communities` в БД  
✅ Поля `community_id` в `users` и `listings`  
✅ Миграции для существующих баз  
✅ Методы работы с площадками в `bot/db.py`  
✅ GitHub репозиторий создан  

## Что нужно сделать (по порядку)

### Шаг 1: Добавить UI переключения площадок

**Файл:** `bot/keyboards.py`

Добавить функцию:
```python
def communities_kb(communities: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{c['title']} ({c['city']}) — {count} объявлений",
            callback_data=f"switch_community:{c['id']}"
        )]
        for c, count in communities
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

**Файл:** `bot/texts.py`

Добавить:
```python
BTN_COMMUNITIES = "🏢 Площадки"
```

**Файл:** `bot/keyboards.py`, функция `main_menu()`

Добавить кнопку:
```python
[KeyboardButton(text=texts.BTN_COMMUNITIES)]
```

### Шаг 2: Создать хендлер переключения

**Новый файл:** `bot/handlers/communities.py`

```python
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiosqlite import Row

from bot import keyboards, texts
from bot.db import Database

router = Router(name="communities")

@router.message(lambda m: m.text == texts.BTN_COMMUNITIES)
async def show_communities(message: Message, user: Row, db: Database):
    communities = await db.list_active_communities()
    if not communities:
        await message.answer("Площадок пока нет")
        return
    
    # Подсчитать объявления для каждой
    comm_with_counts = []
    for c in communities:
        count = await db.count_community_listings(c["id"])
        comm_with_counts.append((c, count))
    
    await message.answer(
        "Выбери площадку:",
        reply_markup=keyboards.communities_kb(comm_with_counts)
    )

@router.callback_query(lambda c: c.data.startswith("switch_community:"))
async def switch_community(callback: CallbackQuery, user: Row, db: Database):
    community_id = int(callback.data.split(":")[1])
    await db.set_user_community(user["id"], community_id)
    
    community = await db.get_community(community_id)
    await callback.message.answer(f"✅ Переключено на: {community['title']}")
    await callback.answer()
```

**Файл:** `bot/handlers/__init__.py`

Добавить:
```python
from bot.handlers import communities

ALL_ROUTERS = [
    start.router,
    listing.router,
    catalog.router,
    deals.router,
    report.router,
    communities.router,  # НОВОЕ
    admin.router,
]
```

### Шаг 3: Фильтрация каталога по площадкам

**Файл:** `bot/db.py`

Обновить методы:
- `list_active()` — добавить `WHERE community_id = ?`
- `category_counts()` — добавить фильтр по площадке
- `search_listings()` — добавить фильтр

Пример для `list_active`:
```python
async def list_active(
    self,
    category_code: str,
    page: int = 0,
    community_id: int | None = None,
) -> tuple[list[aiosqlite.Row], int]:
    where = "l.status = 'active' AND l.category_code = ?"
    params: list[Any] = [category_code]
    
    if community_id is not None:
        where += " AND l.community_id = ?"
        params.append(community_id)
    
    # ... остальной запрос без изменений
```

**Файл:** `bot/handlers/catalog.py`

Передавать `user["community_id"]` во все вызовы:
```python
listings, total = await db.list_active(code, page, community_id=user["community_id"])
```

### Шаг 4: Привязка объявлений к площадке

**Файл:** `bot/db.py`, метод `create_listing()`

Добавить параметр:
```python
async def create_listing(
    self,
    *,
    author_id: int,
    community_id: int | None = None,  # НОВОЕ
    kind: str,
    category_code: str,
    # ... остальные параметры
) -> int:
    cursor = await self._execute(
        """
        INSERT INTO listings(
            author_id, community_id, kind, category_code, title, description,
            search_text, price, is_negotiable, photo_file_id, status,
            created_at, reject_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            author_id,
            community_id,  # НОВОЕ
            kind,
            category_code,
            # ... остальные значения
        ),
    )
```

**Файл:** `bot/services.py`, функция `submit_listing()`

Передавать `community_id`:
```python
listing_id = await db.create_listing(
    author_id=user["id"],
    community_id=user["community_id"],  # НОВОЕ
    kind=kind,
    # ... остальное
)
```

### Шаг 5: Тесты

**Файл:** `tests/test_db.py`

Добавить:
```python
async def test_community_creation(db: Database):
    cid = await db.create_community("college-01", "Колледж №1", "Бишкек")
    community = await db.get_community(cid)
    assert community["code"] == "college-01"
    assert community["title"] == "Колледж №1"

async def test_user_community_binding(db: Database):
    cid = await db.create_community("college-02", "Колледж №2", "Ош")
    user = await db.upsert_user(12345, "testuser", "Test")
    await db.set_user_community(user["id"], cid)
    updated = await db.get_user(user["id"])
    assert updated["community_id"] == cid
```

## Проверка после каждого шага

```powershell
# Тесты
.venv\Scripts\python.exe -m pytest -q

# Линтер
.venv\Scripts\python.exe -m ruff check .

# Запуск бота
.venv\Scripts\python.exe run.py
```

## Важно помнить

1. **Все тексты** — только в `bot/texts.py`
2. **Все SQL** — только в `bot/db.py`
3. **Бизнес-логика** — в `bot/services.py`, не в хендлерах
4. **Callback формат** — см. PROMPT.md раздел 8
5. **Тесты обязательны** для новой логики

## Если что-то сломалось

1. Откатить изменения: `git reset --hard HEAD`
2. Проверить тесты: `pytest -q`
3. Прочитать ошибку полностью
4. Проверить PROMPT.md на запреты

## Коммит после завершения

```bash
git add .
git commit -m "feat: добавлена мультиплощадочность (communities)

- UI переключения площадок
- Фильтрация каталога по community_id
- Привязка объявлений к площадке автора
- Тесты для новых методов"

git push origin master
```

## Следующие задачи (после этого)

1. Инвайт-ссылки (`/start <code>`)
2. Админка создания площадок
3. Статистика по площадкам
4. Амбассадоры и доля выручки

---

**Полная документация:** `docs/multiplatform-feature/CHANGES.md`
