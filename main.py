"""Telegram Mini App: aiogram 3.31 + FastAPI + SQLite.

Run on Render as a Web Service with:
    uvicorn main:app --host 0.0.0.0 --port $PORT

Required environment variable:
    BOT_TOKEN = your BotFather bot token
Optional:
    WEBAPP_URL = GitHub Pages Mini App URL (otherwise use Render URL)
    DB_PATH = location for SQLite file (on a paid persistent disk)
"""
import hashlib
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, WebAppInfo
from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
BOT_TOKEN = os.environ.get("7143276893:AAEBgt6e-8-KZ4pi5P2rybeJruWw64KYWbs", "").strip()
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBAPP_URL = os.environ.get("WEBAPP_URL", RENDER_URL).strip()
DB_PATH = Path(os.environ.get("DB_PATH", str(ROOT / "database.db")))

# A per-bot webhook secret. Telegram sends it in a protected request header.
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest() if BOT_TOKEN else ""

dp = Dispatcher()


def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def create_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                username TEXT,
                clicks INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0
            )
        """)


def get_or_create_user(user):
    with open_db() as db:
        db.execute("""
            INSERT INTO users(telegram_id, first_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username
        """, (user.id, user.first_name, user.username))
        return dict(db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (user.id,)
        ).fetchone())


def authorized_user(header: str | None):
    if not header or not header.startswith("tma "):
        raise HTTPException(401, "Открой Mini App кнопкой внутри Telegram")
    try:
        parsed = safe_parse_webapp_init_data(
            token=BOT_TOKEN, init_data=header[4:]
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(401, "Ошибка проверки подписи Telegram") from exc
    if not parsed.user:
        raise HTTPException(401, "Telegram не передал данные пользователя")
    now = datetime.now(timezone.utc)
    if not (now - timedelta(minutes=5) <= parsed.auth_date <= now + timedelta(minutes=5)):
        # Allow an initData token to be used for up to 24 hours.
        if parsed.auth_date < now - timedelta(hours=24) or parsed.auth_date > now + timedelta(minutes=5):
            raise HTTPException(401, "Сессия устарела. Закрой и открой Mini App заново")
    return parsed.user


@dp.message(CommandStart())
async def on_start(message: Message):
    if not WEBAPP_URL.startswith("https://"):
        await message.answer("Администратор ещё не настроил ссылку WEBAPP_URL")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚀 Открыть",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]])
    await message.answer("Привет! Твой профиль и монеты уже ждут тебя 👇", reply_markup=keyboard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not BOT_TOKEN:
        raise RuntimeError("Добавь BOT_TOKEN в Environment на Render")
    create_db()
    bot = Bot(token=BOT_TOKEN)
    app.state.bot = bot
    try:
        if RENDER_URL:
            await bot.set_webhook(
                url=f"{RENDER_URL}/telegram/webhook",
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=False,
            )
            logger.info("Webhook registered at %s", RENDER_URL)
        else:
            logger.warning("No RENDER_EXTERNAL_URL; webhook is not registered locally")
        yield
    finally:
        # Do not remove the webhook here: a Render redeploy or sleep is normal.
        await bot.session.close()


app = FastAPI(lifespan=lifespan)

# Needed when WEBAPP_URL points to GitHub Pages instead of the Render frontend.
allowed_origins = []
for url in (RENDER_URL, WEBAPP_URL):
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in allowed_origins:
            allowed_origins.append(origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/")
async def index():
    return FileResponse(ROOT / "index.html")


@app.get("/app.js")
async def javascript():
    return FileResponse(ROOT / "app.js", media_type="application/javascript")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "Invalid Telegram webhook secret")
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": request.app.state.bot})
    await dp.feed_update(request.app.state.bot, update)
    return {"ok": True}


@app.get("/api/me")
async def profile(authorization: str | None = Header(default=None)):
    user = authorized_user(authorization)
    return get_or_create_user(user)


@app.post("/api/click")
async def click(authorization: str | None = Header(default=None)):
    user = authorized_user(authorization)
    get_or_create_user(user)
    with open_db() as db:
        db.execute("""
            UPDATE users SET clicks = clicks + 1, coins = coins + 5
            WHERE telegram_id = ?
        """, (user.id,))
        result = db.execute("SELECT clicks, coins FROM users WHERE telegram_id = ?", (user.id,)).fetchone()
        return dict(result)


@app.post("/api/reset")
async def reset(authorization: str | None = Header(default=None)):
    user = authorized_user(authorization)
    get_or_create_user(user)
    with open_db() as db:
        db.execute("UPDATE users SET clicks = 0 WHERE telegram_id = ?", (user.id,))
        result = db.execute("SELECT clicks, coins FROM users WHERE telegram_id = ?", (user.id,)).fetchone()
        return dict(result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
