#!/usr/bin/env bash
# Обновление бота из GitHub и перезапуск сервиса.
# Запускать от root:  bash /opt/college-bourse/deploy/update.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/college-bourse}"

echo "== забираю свежий код =="
git -C "$APP_DIR" fetch --all --quiet
git -C "$APP_DIR" reset --hard origin/master --quiet

echo "== зависимости =="
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "== тесты =="
(cd "$APP_DIR" && "$APP_DIR/.venv/bin/python" -m pytest -q) || echo "тесты не прошли"

echo "== перезапуск =="
systemctl restart college-bourse
sleep 4
systemctl --no-pager --full status college-bourse | head -12 || true
echo
echo "Логи: journalctl -u college-bourse -f"
