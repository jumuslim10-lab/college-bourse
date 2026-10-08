# Развёртывание на VPS (Сингапур, рядом с базой)

Зачем: база у нас в Supabase (регион Singapore). Если бот работает на домашнем ПК, каждый запрос
идёт через полмира и занимает ~540 мс. Если бот живёт **на сервере в том же регионе**, что база,
запросы становятся 1–5 мс — и всё работает быстро, круглосуточно, без твоего компьютера.

## Какой сервер брать

| Параметр | Значение |
|---|---|
| Регион | **Singapore** (обязательно — рядом с базой) |
| ОС | Ubuntu 24.04 LTS (или 22.04) |
| Мощность | 1 vCPU, **1 ГБ RAM**, 25 ГБ SSD — с запасом |
| Цена | ~$3.5–6 в месяц (300–500 сом) |
| Провайдеры | Vultr, DigitalOcean, Linode, AWS Lightsail — у всех есть Сингапур |

При создании сервера добавь **SSH-ключ** (публичную часть), тогда доступ будет без пароля.
Если карта не проходит у провайдера — скажи, подберём другой вариант оплаты.

## Установка

1. Создать сервер с SSH-ключом, получить **IP-адрес**.
2. Залить проект и поставить сервис — одной командой на сервере:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/jumuslim10-lab/college-bourse/master/deploy/setup-vps.sh | bash
   ```

   Или вручную:

   ```bash
   git clone https://github.com/jumuslim10-lab/college-bourse.git /opt/college-bourse
   bash /opt/college-bourse/deploy/setup-vps.sh
   ```

3. При первом запуске скрипт остановится и попросит заполнить `/opt/college-bourse/.env`:

   ```
   BOT_TOKEN=<токен от @BotFather>
   ADMIN_IDS=<твой tg_id>
   DB_BACKEND=postgres
   DATABASE_URL=postgresql://postgres.<ref>:<пароль>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   ```

   Пароль с символами кодируется: `$` → `%24`, `%` → `%25`, `?` → `%3F`.
   Файл `.env` не попадает в git — это единственное место, где живут секреты.

4. Запустить скрипт ещё раз — он поднимет сервис и включит автозапуск при перезагрузке.

> **Важно: один токен — один бот.** После запуска на сервере обязательно останови локальный бот
> (закрой окно `start-bot.cmd` или нажми `Ctrl+C`), иначе Telegram будет отдавать
> `409 Conflict` обоим экземплярам.

## Управление

```bash
systemctl status college-bourse        # состояние
journalctl -u college-bourse -f        # живой лог
systemctl restart college-bourse       # перезапуск
systemctl stop college-bourse          # остановить
bash /opt/college-bourse/deploy/update.sh   # обновить код из GitHub и перезапустить
```

## Если что-то сломалось

Быстрый откат на локальную базу (данные в `/opt/college-bourse/data/bot.db`):

```bash
sed -i 's/^DB_BACKEND=.*/DB_BACKEND=sqlite/' /opt/college-bourse/.env
systemctl restart college-bourse
journalctl -u college-bourse -n 30 --no-pager
```

## Мини-пожарная безопасность

```bash
ufw allow OpenSSH      # оставить только SSH
ufw --force enable
chmod 600 /opt/college-bourse/.env
```

Дополнительно: отозвать ключи Supabase (`sb_secret_*`, JWT) и сменить пароль базы, если они
где-то публиковались; токен бота перевыпустить у @BotFather, если он попадал в переписку.

## Что уже подготовлено в репозитории

- `deploy/college-bourse.service` — systemd-юнит (автозапуск, перезапуск при падении);
- `deploy/setup-vps.sh` — установка/обновление с нуля, включая прогон тестов перед запуском;
- `deploy/update.sh` — обновление кода и перезапуск.
