#!/usr/bin/env bash
# Установка бота «Биржа колледжа» на чистый VPS (Ubuntu 22.04/24.04).
# Запускать от root:  bash deploy/setup-vps.sh
# Скрипт можно запускать повторно — он же служит обновлением.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/jumuslim10-lab/college-bourse.git}"
APP_DIR="${APP_DIR:-/opt/college-bourse}"
SERVICE_USER="${SERVICE_USER:-college}"

echo "== 1/7 системные пакеты =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates

echo "== 2/7 пользователь сервиса =="
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
fi

echo "== 3/7 код проекта =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --all --quiet
  git -C "$APP_DIR" reset --hard origin/master --quiet
else
  git clone --quiet "$REPO_URL" "$APP_DIR"
fi

echo "== 4/7 виртуальное окружение и зависимости =="
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "== 5/7 конфиг =="
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  cat <<'TEXT'

Нужен файл /opt/college-bourse/.env — заполни его и запусти скрипт снова:
  BOT_TOKEN=<токен от @BotFather>
  ADMIN_IDS=<твой tg_id>
  DB_BACKEND=postgres
  DATABASE_URL=<строка подключения Supabase>
TEXT
  exit 1
fi
chmod 600 "$APP_DIR/.env"

echo "== 6/7 тесты перед запуском =="
"$APP_DIR/.venv/bin/pip" install --quiet pytest ruff
if (cd "$APP_DIR" && "$APP_DIR/.venv/bin/python" -m pytest -q); then
  echo "тесты прошли"
else
  echo "ВНИМАНИЕ: тесты не прошли — но запускаю сервис, чтобы увидеть ошибку в логах"
fi

echo "== 7/7 systemd =="
install -m 644 "$APP_DIR/deploy/college-bourse.service" /etc/systemd/system/college-bourse.service
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
systemctl daemon-reload
systemctl enable --now college-bourse
sleep 4
systemctl --no-pager --full status college-bourse | head -15 || true

cat <<'TEXT'

Готово. Полезные команды:
  systemctl status college-bourse      — состояние
  journalctl -u college-bourse -f      — живой лог
  systemctl restart college-bourse     — перезапуск
  bash /opt/college-bourse/deploy/update.sh — обновление из GitHub
TEXT
