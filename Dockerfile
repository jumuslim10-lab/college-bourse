# Образ для Railway и любого другого Docker-хостинга.
# Бот работает на long polling: публичный порт ему не нужен, но платформы вроде Railway
# ждут слушающий порт — поэтому run.py поднимает крошечный health-ответ на $PORT.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY run.py schema.sql schema_postgres.sql ./

# работаем не от root
RUN useradd --create-home bot && chown -R bot:bot /app
USER bot

CMD ["python", "run.py"]
