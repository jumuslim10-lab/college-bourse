"""Тесты конфигурации: разбор переменных окружения."""

from __future__ import annotations

import pytest

from bot.config import load_config, parse_admin_ids


def test_parse_admin_ids():
    assert parse_admin_ids("5819052050") == (5819052050,)
    assert parse_admin_ids("1, 2;3") == (1, 2, 3)
    assert parse_admin_ids("мусор, 42") == (42,)
    assert parse_admin_ids("") == ()


def test_health_port_from_env(monkeypatch):
    monkeypatch.setenv("HEALTH_PORT", "8080")
    assert load_config().health_port == 8080

    monkeypatch.delenv("HEALTH_PORT")
    monkeypatch.setenv("PORT", "9090")  # так делает Railway
    assert load_config().health_port == 9090

    monkeypatch.delenv("PORT")
    assert load_config().health_port == 0


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "mysql")
    with pytest.raises(SystemExit):
        load_config()


def test_postgres_backend_is_accepted(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/postgres")
    config = load_config()
    assert config.db_backend == "postgres"
    assert config.database_url.startswith("postgresql://")
