-- Схема БД биржи колледжа. Применяется при каждом старте (idempotent).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS communities (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT    NOT NULL UNIQUE,
    title             TEXT    NOT NULL,
    city              TEXT    NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1,
    ambassador_user_id INTEGER REFERENCES users(id),
    created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL UNIQUE,
    username     TEXT,
    first_name   TEXT,
    community_id INTEGER REFERENCES communities(id),
    role         TEXT    NOT NULL DEFAULT 'student',
    is_banned    INTEGER NOT NULL DEFAULT 0,
    warn_count   INTEGER NOT NULL DEFAULT 0,
    rating_sum   INTEGER NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    agreed_at    TEXT,
    created_at   TEXT    NOT NULL,
    last_seen_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    code     TEXT PRIMARY KEY,
    title    TEXT    NOT NULL,
    emoji    TEXT    NOT NULL,
    ttl_days INTEGER NOT NULL,
    sort     INTEGER NOT NULL,
    is_food  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS listings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id      INTEGER NOT NULL REFERENCES users(id),
    community_id   INTEGER REFERENCES communities(id),
    kind           TEXT    NOT NULL CHECK (kind IN ('sell', 'buy')),
    category_code  TEXT    NOT NULL REFERENCES categories(code),
    title          TEXT    NOT NULL,
    description    TEXT    NOT NULL,
    search_text    TEXT    NOT NULL DEFAULT '',
    price          INTEGER,
    is_negotiable  INTEGER NOT NULL DEFAULT 0,
    photo_file_id  TEXT,
    status         TEXT    NOT NULL CHECK (status IN ('draft', 'pending', 'active', 'archived', 'sold', 'rejected', 'removed')),
    created_at     TEXT    NOT NULL,
    expires_at     TEXT,
    bumped_until   TEXT,
    moderated_by   INTEGER,
    reject_reason  TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_cat  ON listings(status, category_code, community_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(author_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_community ON listings(community_id, status);

CREATE TABLE IF NOT EXISTS deals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    buyer_id   INTEGER NOT NULL REFERENCES users(id),
    seller_id  INTEGER NOT NULL REFERENCES users(id),
    status     TEXT    NOT NULL CHECK (status IN ('agreed', 'done', 'cancelled', 'disputed')),
    created_at TEXT    NOT NULL,
    closed_at  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_deals_unique ON deals(listing_id, buyer_id);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id    INTEGER NOT NULL REFERENCES deals(id),
    rater_id   INTEGER NOT NULL REFERENCES users(id),
    target_id  INTEGER NOT NULL REFERENCES users(id),
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text       TEXT,
    created_at TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reviews_unique ON reviews(deal_id, rater_id);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER REFERENCES listings(id),
    reporter_id INTEGER NOT NULL REFERENCES users(id),
    reason      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at  TEXT    NOT NULL,
    resolved_by INTEGER
);

CREATE TABLE IF NOT EXISTS promotions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    kind       TEXT    NOT NULL DEFAULT 'bump',
    paid_until TEXT    NOT NULL,
    amount     INTEGER NOT NULL DEFAULT 0,
    method     TEXT    NOT NULL DEFAULT 'manual',
    granted_by INTEGER,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_name TEXT    NOT NULL,
    text         TEXT    NOT NULL,
    photo_file_id TEXT,
    starts_at    TEXT,
    ends_at      TEXT,
    price        INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'expired', 'disabled')),
    created_by   INTEGER,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,
    user_id    INTEGER,
    listing_id INTEGER,
    meta       TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, created_at DESC);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
