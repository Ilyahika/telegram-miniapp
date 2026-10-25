"""
main.py — точка входа. Запуск:  uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1

Что здесь происходит:
  1. при старте создаётся БД (мгновенно) и в ФОНЕ запускается Telegram-бот;
  2. подключаются маршруты: игра (buildhouse, games) и админ-панель (admin);
  3. отдаются файлы интерфейса: index.html, style.css, app.js, admin.js.
Важно: --workers 1, иначе несколько копий бота будут конфликтовать при polling.
"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

import admin
import botapp
import buildhouse
import games
from config import BOT_TOKEN, CORS_ORIGINS, ROOT, WEBAPP_URL
from db import init_db, session

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('miniapp')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Старт: готовим БД и запускаем бота в фоне. Остановка: аккуратно гасим бота."""
    if not BOT_TOKEN:
        log.error('BOT_TOKEN не задан (Render -> Environment): API работать не будет')
    if not WEBAPP_URL.startswith('https://'):
        log.error('WEBAPP_URL не задан или не https: кнопка «Открыть» в боте не заработает')
    init_db()                                        # создаёт таблицы за миллисекунды
    bot = botapp.create_bot()
    botapp.state.bot = bot
    task = asyncio.create_task(botapp.run_bot(bot)) if bot else None   # бот стартует параллельно, сайт уже отвечает
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if bot:
            await bot.session.close()


# docs/openapi отключены: схема API не должна быть публичной
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)                      # сжимает ответы -> быстрее на мобильном интернете
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=['GET', 'POST'],
                   allow_headers=['Content-Type', 'X-Telegram-Init-Data'],
                   max_age=86400)                                          # браузер запоминает preflight на сутки

# --------------------------------------------------------------------- служебные маршруты
@app.get('/health')
def health():
    """Проверка «сервер жив». Не требует авторизации и не трогает БД — именно им клиент «будит» Render."""
    return {'status': 'ok', 'api': 'reachable', 'bot': botapp.state.username or None, 'polling': botapp.state.polling}


@app.get('/health/db')
def health_db():
    """Проверка доступности БД."""
    try:
        with session() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {'database': 'connected', 'tables_ready': {'players', 'bh', 'cars', 'mines2'} <= tables}
    except Exception:
        log.exception('Проверка БД не прошла')
        raise HTTPException(503, 'SQLite недоступна; смотри Logs в Render')


# --------------------------------------------------------------------- API
app.include_router(buildhouse.router)   # дом, доход, тапы, бонус, ник, аватар
app.include_router(games.router)        # мины, кейсы, гараж, магазин, рейтинг
app.include_router(admin.router)        # админ-панель

# --------------------------------------------------------------------- интерфейс
# Отдаём только перечисленные файлы — исходники сервера (main.py и т.д.) не выставляются наружу
STATIC = {'style.css': 'text/css', 'app.js': 'application/javascript', 'admin.js': 'application/javascript'}
# no-cache = «всегда сверяйся с сервером»; благодаря ETag неизменный файл отдаётся как 304 без тела
NO_CACHE = {'Cache-Control': 'no-cache'}


@app.get('/')
def index():
    """Главная страница Mini App."""
    return FileResponse(ROOT / 'index.html', media_type='text/html', headers=NO_CACHE)


@app.get('/{name}')
def static_file(name: str):
    """Статические файлы интерфейса (этот маршрут объявлен последним, чтобы не перекрывать остальные)."""
    if name not in STATIC:
        raise HTTPException(404, 'Not found')
    return FileResponse(ROOT / name, media_type=STATIC[name], headers=NO_CACHE)
