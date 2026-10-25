# Telegram Mini App на aiogram + FastAPI + SQLite3

## Файлы
- main.py — Telegram webhook + API + SQLite3
- index.html — интерфейс
- app.js — запросы к API
- requirements.txt — зависимости
- .gitignore — не публикуем токены и базу

## Быстрый вариант: весь Mini App через Render
1. Положить файлы в корень своего репозитория GitHub (вместо старых).
2. Render -> New -> Web Service -> выбрать этот репозиторий.
3. Runtime: Python; Build Command: `pip install -r requirements.txt`.
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`.
5. Environment -> добавить `BOT_TOKEN` = токен бота от BotFather.
6. Выбрать Free, создать сервис. Render автоматически задаёт RENDER_EXTERNAL_URL.
7. Открыть https://<имя>.onrender.com/health и проверить ответ `{"status":"ok"}`.
8. Отправить боту /start и нажать «🚀 Открыть».

## Если надо сохранить GitHub Pages ссылку
1. Получить ссылку Render `https://<имя>.onrender.com`.
2. В app.js прописать `const API_BASE = "https://<имя>.onrender.com";`.
3. В Render -> Environment добавить WEBAPP_URL = https://USERNAME.github.io/REPO/.
4. Сохранить / дождаться deploy. GitHub Pages обновится после коммита.
5. /start у бота откроет GitHub Pages, кнопки будут обращаться к API Render.

## Важно: хранение SQLite
На Render Free база SQLite исчезает при перезапуске/сне сервера и при deploy.
Для постоянного хранения SQLite нужен план Render с persistent disk,
смонтированный по пути /var/data, и Environment DB_PATH=/var/data/database.db.
Бесплатная альтернатива для долговременных данных — внешняя PostgreSQL БД
(но код потребуется адаптировать под PostgreSQL).

## Проверка
- /health доступен без Telegram
- /api/me требует действительные Telegram WebApp initData
- /telegram/webhook принимает только запросы с secret-token
- не размещайте токен в main.py и GitHub
- не запускайте тот же токен через polling на ПК одновременно с Render webhook
