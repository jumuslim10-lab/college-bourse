# Отчёт о добавлении мультиплощадочности (Communities)

**Дата:** 2026-10-08  
**Статус:** Инфраструктура готова, UI не реализован  
**GitHub репозиторий:** https://github.com/jumuslim10-lab/college-bourse

---

## Что было сделано

### 1. Создан GitHub репозиторий
Проект запушен в новый публичный репозиторий для совместной работы.

### 2. Добавлена таблица `communities` в БД

**Файл:** `schema.sql`

Новая таблица для хранения площадок (колледжей/школ):

```sql
CREATE TABLE IF NOT EXISTS communities (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT    NOT NULL UNIQUE,
    title             TEXT    NOT NULL,
    city              TEXT    NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1,
    ambassador_user_id INTEGER REFERENCES users(id),
    created_at        TEXT    NOT NULL
);
```

**Поля:**
- `id` — внутренний ID площадки
- `code` — уникальный код для инвайт-ссылок (например: `college-01`, `school-bishkek-12`)
- `title` — название площадки (например: "Колледж №12")
- `city` — город площадки
- `is_active` — активна ли площадка (для отключения без удаления)
- `ambassador_user_id` — ID амбассадора (студент, ведущий площадку за долю выручки)
- `created_at` — дата создания

### 3. Добавлено поле `community_id` в таблицы

**Таблица `users`:**
```sql
community_id INTEGER REFERENCES communities(id)
```
Связывает пользователя с его площадкой.

**Таблица `listings`:**
```sql
community_id INTEGER REFERENCES communities(id)
```
Связывает объявление с площадкой, где оно размещено.

### 4. Обновлены индексы

**Файл:** `schema.sql`

Добавлены индексы для быстрой фильтрации по площадкам:

```sql
CREATE INDEX IF NOT EXISTS idx_listings_cat ON listings(status, category_code, community_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_community ON listings(community_id, status);
```

### 5. Добавлены миграции для существующих БД

**Файл:** `bot/db.py`, метод `Database.migrate()`

Автоматическое добавление новых колонок при запуске бота:

```python
# Миграция 2: community_id в users
async with self.conn.execute("PRAGMA table_info(users)") as cursor:
    user_columns = {row["name"] for row in await cursor.fetchall()}
if "community_id" not in user_columns:
    await self.conn.execute(
        "ALTER TABLE users ADD COLUMN community_id INTEGER REFERENCES communities(id)"
    )
    await self.conn.commit()

# Миграция 3: community_id в listings
async with self.conn.execute("PRAGMA table_info(listings)") as cursor:
    listing_columns = {row["name"] for row in await cursor.fetchall()}
if "community_id" not in listing_columns:
    await self.conn.execute(
        "ALTER TABLE listings ADD COLUMN community_id INTEGER REFERENCES communities(id)"
    )
    await self.conn.commit()
```

**Важно:** Миграции идемпотентны — можно запускать много раз безопасно.

### 6. Добавлены методы работы с площадками

**Файл:** `bot/db.py`

Новые методы класса `Database`:

```python
async def create_community(code: str, title: str, city: str, ambassador_user_id: int | None = None) -> int
    # Создать новую площадку

async def get_community(community_id: int) -> aiosqlite.Row | None
    # Получить площадку по ID

async def get_community_by_code(code: str) -> aiosqlite.Row | None
    # Получить площадку по коду (для инвайт-ссылок)

async def list_active_communities() -> list[aiosqlite.Row]
    # Список всех активных площадок

async def set_user_community(user_id: int, community_id: int | None) -> None
    # Привязать пользователя к площадке

async def count_community_users(community_id: int) -> int
    # Количество пользователей на площадке

async def count_community_listings(community_id: int, status: str = "active") -> int
    # Количество объявлений на площадке
```

---

## Что НЕ сделано (нужно продолжить)

### 1. UI для переключения площадок

**Задача:** Добавить кнопку "🏢 Площадки" в главное меню и хендлер для выбора.

**Файлы для изменения:**
- `bot/keyboards.py` — добавить `communities_kb()`
- `bot/handlers/start.py` или новый файл `bot/handlers/communities.py` — хендлеры

**Логика:**
1. Пользователь жмёт "🏢 Площадки"
2. Видит список активных площадок с количеством объявлений
3. Выбирает площадку → `db.set_user_community(user.id, community_id)`
4. Каталог теперь показывает только объявления выбранной площадки

### 2. Фильтрация каталога по площадкам

**Задача:** Все запросы к `listings` должны фильтроваться по `community_id` текущего пользователя.

**Файлы для изменения:**
- `bot/db.py` — методы `list_active`, `search_listings`, `category_counts` и др.
- Добавить параметр `community_id` в SQL-запросы

**Пример:**
```python
async def list_active(self, category_code: str, page: int, community_id: int | None = None):
    where = "status = 'active' AND category_code = ?"
    params = [category_code]
    
    if community_id is not None:
        where += " AND community_id = ?"
        params.append(community_id)
    
    # ... остальной запрос
```

### 3. Привязка новых объявлений к площадке

**Задача:** При создании объявления автоматически ставить `community_id` автора.

**Файлы для изменения:**
- `bot/db.py`, метод `create_listing()` — добавить параметр `community_id`
- `bot/services.py`, метод `submit_listing()` — передавать `user["community_id"]`

### 4. Инвайт-ссылки для площадок

**Задача:** Поддержка входа через `t.me/<bot>?start=<code>` для автоматической привязки к площадке.

**Файлы для изменения:**
- `bot/handlers/start.py`, хендлер `/start`
- Парсить `start` параметр, искать площадку по коду, привязывать пользователя

**Пример:**
```python
@router.message(Command("start"))
async def start_handler(message: Message, user: Row, db: Database):
    # Проверить deep link
    args = message.text.split()[1:] if message.text else []
    if args:
        code = args[0]
        community = await db.get_community_by_code(code)
        if community:
            await db.set_user_community(user["id"], community["id"])
            await message.answer(f"✅ Ты присоединился к площадке: {community['title']}")
    
    # ... обычная логика /start
```

### 5. Админка для управления площадками

**Задача:** Админ должен уметь создавать новые площадки, видеть статистику по каждой.

**Файлы для изменения:**
- `bot/handlers/admin.py` — новые команды `/create_community`, `/list_communities`
- `bot/keyboards.py` — клавиатура для админки площадок

### 6. Тесты

**Задача:** Добавить тесты для новых методов.

**Файл:** `tests/test_db.py`

**Что протестировать:**
- Создание площадки
- Привязка пользователя к площадке
- Фильтрация объявлений по площадке
- Инвайт-ссылки

### 7. Обновление статистики

**Задача:** Статистика должна показываться раздельно по площадкам.

**Файл:** `bot/db.py`, метод `stats()`

---

## Как проверить текущие изменения

```powershell
cd C:\Users\User\Documents\deepseek-harness\default-workspace\college-bourse

# Запустить тесты (должны остаться зелёными)
.venv\Scripts\python.exe -m pytest -q

# Проверить линтер (должен быть чист)
.venv\Scripts\python.exe -m ruff check .

# Запустить бота (миграции применятся автоматически)
.venv\Scripts\python.exe run.py
```

**Ожидаемый результат:**
- Все тесты зелёные ✅
- Линтер без ошибок ✅
- Бот запускается и добавляет новые колонки в БД ✅
- Функциональность бота не сломана (пока площадки не используются) ✅

---

## Архитектурные решения

### Почему `community_id` nullable?

На этапе миграции у старых пользователей и объявлений `community_id = NULL`. Это позволяет:
1. Безопасно обновить существующую БД
2. Работать в "моноплощадочном" режиме до запуска Фазы 3
3. Избежать массовой переприсвоения данных

**В будущем:** при регистрации нового пользователя `community_id` обязателен.

### Почему площадки не удаляются?

Поле `is_active` позволяет "отключить" площадку без потери данных:
- История сделок сохраняется
- Рейтинги пользователей не ломаются
- Статистика доступна для анализа

### Почему инвайт по коду, а не по ID?

Код (`college-01`) более читаем в ссылках, чем ID (`42`):
- `t.me/college_bourse_bot?start=college-01` ✅
- `t.me/college_bourse_bot?start=42` ❌

---

## Следующие шаги (приоритет)

1. **Добавить UI переключения площадок** (кнопка в главном меню)
2. **Фильтрация каталога по площадкам** (обязательное условие)
3. **Привязка новых объявлений к площадке автора**
4. **Инвайт-ссылки** (`t.me/bot?start=code`)
5. **Админка для создания площадок**
6. **Тесты** для новых методов
7. **Статистика по площадкам**

---

## Важные ограничения (из PROMPT.md)

⚠️ **Мультиплощадочность — это Фаза 3**, которая включается только после гейта:

**Гейт:** метрики текущей площадки держатся 2 недели подряд:
- ≥10 объявлений/день
- ≥5 сделок/неделю

**Почему это важно:**
- Сначала нужно доказать, что биржа работает на одной площадке
- Масштабирование без ликвидности убьёт проект
- Амбассадоры имеют смысл только при работающей модели

**Порядок открытия площадок:**
1. Свой колледж (уже есть)
2. Соседний колледж/техникум (та же аудитория)
3. Общаги/кампусы (плотнее спрос на еду)
4. Школы — **только в родительском формате** после 2-3 работающих колледжей

---

## Контакты и ссылки

- **GitHub:** https://github.com/jumuslim10-lab/college-bourse
- **Полное ТЗ:** `PROMPT.md` в корне проекта
- **Правила для ИИ:** `CLAUDE.md` в корне проекта
- **Текущая ветка:** `master`

---

## Для следующего ИИ-агента

### Быстрый старт

1. Прочитать `PROMPT.md` (полное ТЗ)
2. Прочитать `CLAUDE.md` (правила работы)
3. Прочитать этот файл (`docs/multiplatform-feature/CHANGES.md`)
4. Запустить тесты: `.venv\Scripts\python.exe -m pytest -q`
5. Продолжить с пункта "Что НЕ сделано" выше

### Что можно менять

✅ Технические детали (имена, структура, рефакторинг)  
✅ UI и UX (в рамках инвариантов)  
✅ Добавление тестов  

### Что НЕЛЬЗЯ менять

❌ Бизнес-модель (деньги через бота)  
❌ Монетизацию (комиссия с оборота)  
❌ Бесплатный тариф (3 объявления)  
❌ Порядок фаз (без гейтов)  

### Проверки перед коммитом

```powershell
.venv\Scripts\python.exe -m pytest -q      # Тесты зелёные
.venv\Scripts\python.exe -m ruff check .   # Линтер чист
```

---

**Статус задачи #2:** Добавить UI для переключения между площадками — **НЕ НАЧАТА**  
**Готово к передаче:** ✅
