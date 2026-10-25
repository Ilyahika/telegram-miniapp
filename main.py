import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()  # Токен хранится в Render -> Environment!
WEBAPP_URL = os.getenv('WEBAPP_URL', '').strip().rstrip('/') + '/'
DB_PATH = Path(os.getenv('DB_PATH', str(ROOT / 'database.db')))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('miniapp')
dp = Dispatcher()


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    return db


def init_db():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS players (
            telegram_id INTEGER PRIMARY KEY,
            telegram_name TEXT NOT NULL,
            nickname TEXT,
            coins INTEGER NOT NULL DEFAULT 0,
            games_played INTEGER NOT NULL DEFAULT 0,
            games_won INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS mines_games (
            telegram_id INTEGER PRIMARY KEY,
            mines_json TEXT NOT NULL,
            opened_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )''')


def authenticate(init_data: str):
    """Telegram WebApp initData verified using the bot token and HMAC."""
    if not BOT_TOKEN:
        raise HTTPException(503, 'BOT_TOKEN не настроен на сервере')
    if not init_data:
        raise HTTPException(401, 'Открой Mini App кнопкой «Открыть» внутри Telegram')
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received_hash = params.pop('hash')
        params.pop('signature', None)
        auth_date = int(params['auth_date'])
        now = int(time.time())
        if auth_date > now + 60 or now - auth_date > 86400:
            raise ValueError('expired')
        data_check = '\n'.join(f'{k}={v}' for k, v in sorted(params.items()))
        data_check = "\n".join(
            f"{key}={value}"
            for key, value in sorted(params.items())
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        expected = hmac.new(
            secret,
            data_check.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected):
            raise ValueError("invalid signature")
        if not hmac.compare_digest(received_hash, expected):
            raise ValueError('invalid signature')
        user = json.loads(params['user'])
        user_id = int(user['id'])
        if user_id <= 0:
            raise ValueError('invalid id')
        return {'id': user_id, 'first_name': str(user.get('first_name') or 'Игрок')[:100],
                'username': str(user.get('username') or '')[:100]}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logging.warning(
            "Telegram authorization failed: %s",
            str(exc)
        )
        raise HTTPException(
            status_code=401,
            detail="Не удалось подтвердить профиль Telegram"
    ) from exc


def get_player(db, user):
    name = user['first_name']
    db.execute('''INSERT OR IGNORE INTO players (telegram_id, telegram_name, created_at)
                  VALUES (?, ?, ?)''', (user['id'], name, int(time.time())))
    db.execute('UPDATE players SET telegram_name=? WHERE telegram_id=?', (name, user['id']))
    return db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()


def player_json(row):
    return {'telegram_id': row['telegram_id'], 'telegram_name': row['telegram_name'],
            'nickname': row['nickname'] or row['telegram_name'], 'custom_nickname': row['nickname'],
            'coins': row['coins'], 'games_played': row['games_played'], 'games_won': row['games_won']}


def game_json(row):
    if row is None:
        return None
    mines = set(json.loads(row['mines_json']))
    opened = json.loads(row['opened_json'])
    status = row['status']
    cells = []
    for index in range(25):
        if index not in opened:
            cells.append({'state': 'closed'})
        elif index in mines:
            cells.append({'state': 'mine'})
        else:
            x, y = index % 5, index // 5
            around = sum(((ny * 5 + nx) in mines)
                         for ny in range(max(0, y - 1), min(5, y + 2))
                         for nx in range(max(0, x - 1), min(5, x + 2)) if (nx, ny) != (x, y))
            cells.append({'state': 'safe', 'around': around})
    return {'status': status, 'opened': len(opened), 'total_safe': 20, 'cells': cells}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not BOT_TOKEN:
        raise RuntimeError('Добавь BOT_TOKEN в Render -> Environment')
    if not WEBAPP_URL.startswith('https://'):
        raise RuntimeError('Добавь ссылку GitHub Pages (https://...) в WEBAPP_URL')
    init_db()
    bot = Bot(token=BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    polling = asyncio.create_task(dp.start_polling(bot))
    app.state.bot = bot
    try:
        yield
    finally:
        polling.cancel()
        try:
            await polling
        except asyncio.CancelledError:
            pass
        await bot.session.close()


app = FastAPI(lifespan=lifespan)
parsed_webapp = urlsplit(WEBAPP_URL)
origin = f'{parsed_webapp.scheme}://{parsed_webapp.netloc}'
app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=['GET', 'POST'],
                   allow_headers=['Content-Type', 'X-Telegram-Init-Data'])


@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text='🚀 Открыть', web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer('🎮 Профиль и игра «Мины» доступны в Mini App!', reply_markup=kb)


@app.get('/health')
def health():
    return {'status': 'ok', 'api': 'reachable'}


@app.get('/health/db')
def database_health():
    """Public read-only check; no credentials or player data exposed."""
    try:
        with connection() as db:
            db.execute('SELECT 1').fetchone()
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        return {'database': 'connected', 'tables_ready':
                'players' in tables and 'mines_games' in tables}
    except sqlite3.Error:
        log.exception('Database health check failed')
        raise HTTPException(503, 'SQLite3 недоступна; смотри Logs в Render')


@app.get('/api/diagnostics')
def diagnostics(request: Request):
    """Authenticated SQLite write/read/update/delete probe, with real commits."""
    user = auth_request(request)
    try:
        with connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS db_probe (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('INSERT INTO db_probe (id,value) VALUES (lower(hex(randomblob(16))),?)', ('created',))
            key = db.execute('SELECT id FROM db_probe WHERE value=? ORDER BY rowid DESC LIMIT 1', ('created',)).fetchone()[0]
            db.commit()
            read_ok = db.execute('SELECT value FROM db_probe WHERE id=?', (key,)).fetchone()[0] == 'created'
            db.execute('UPDATE db_probe SET value=? WHERE id=?', ('updated', key))
            db.commit()
            update_ok = db.execute('SELECT value FROM db_probe WHERE id=?', (key,)).fetchone()[0] == 'updated'
            db.execute('DELETE FROM db_probe WHERE id=?', (key,))
            db.commit()
            delete_ok = db.execute('SELECT 1 FROM db_probe WHERE id=?', (key,)).fetchone() is None
            row = get_player(db, user)
            db.commit()
            profile_read_ok = row is not None and int(row['telegram_id']) == user['id']
        return {'telegram_auth': 'ok', 'sqlite_write': True,
                'sqlite_read': read_ok, 'sqlite_update': update_ok,
                'sqlite_delete': delete_ok, 'profile_read': profile_read_ok}
    except sqlite3.Error:
        log.exception('Database diagnostic failed')
        raise HTTPException(503, 'Ошибка записи/чтения SQLite3. Открой Logs в Render')



@app.get('/')
def index():
    return FileResponse(ROOT / 'index.html')


@app.get('/app.js')
def javascript():
    return FileResponse(ROOT / 'app.js', media_type='application/javascript')


def auth_request(request: Request):
    return authenticate(request.headers.get('X-Telegram-Init-Data', ''))


@app.get('/api/profile')
def profile(request: Request):
    user = auth_request(request)
    with connection() as db:
        row = get_player(db, user)
        return {'player': player_json(row)}


class Nickname(BaseModel):
    nickname: str


@app.post('/api/nickname')
def nickname(data: Nickname, request: Request):
    user = auth_request(request)
    new_name = data.nickname.strip()
    if len(new_name) > 24 or (new_name and (len(new_name) < 2 or not re.fullmatch(r'[\w -]+', new_name, re.UNICODE))):
        raise HTTPException(400, 'Ник: 2–24 символа, буквы, цифры, пробел, _ или -. Пустое поле — сброс.')
    with connection() as db:
        get_player(db, user)
        db.execute('UPDATE players SET nickname=? WHERE telegram_id=?', (new_name or None, user['id']))
        row = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
        return {'player': player_json(row)}


@app.get('/api/mines')
def mines_status(request: Request):
    user = auth_request(request)
    with connection() as db:
        get_player(db, user)
        game = db.execute('SELECT * FROM mines_games WHERE telegram_id=?', (user['id'],)).fetchone()
        return {'game': game_json(game)}


@app.post('/api/mines/new')
def new_game(request: Request):
    user = auth_request(request)
    with connection() as db:
        get_player(db, user)
        old = db.execute('SELECT status FROM mines_games WHERE telegram_id=?', (user['id'],)).fetchone()
        if old and old['status'] == 'playing':
            raise HTTPException(409, 'Сначала закончи текущую игру')
        chosen = sorted(random.SystemRandom().sample(range(25), 5))
        db.execute('''INSERT OR REPLACE INTO mines_games
            (telegram_id, mines_json, opened_json, status, created_at) VALUES (?, ?, ?, ?, ?)''',
                   (user['id'], json.dumps(chosen), '[]', 'playing', int(time.time())))
        db.execute('UPDATE players SET games_played=games_played+1 WHERE telegram_id=?', (user['id'],))
        row = db.execute('SELECT * FROM mines_games WHERE telegram_id=?', (user['id'],)).fetchone()
        player = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
        return {'game': game_json(row), 'player': player_json(player)}


class Pick(BaseModel):
    cell: int


@app.post('/api/mines/open')
def open_cell(data: Pick, request: Request):
    user = auth_request(request)
    if not 0 <= data.cell < 25:
        raise HTTPException(400, 'Неверная клетка')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        get_player(db, user)
        row = db.execute('SELECT * FROM mines_games WHERE telegram_id=?', (user['id'],)).fetchone()
        if not row or row['status'] != 'playing':
            raise HTTPException(409, 'Начни новую игру')
        opened = json.loads(row['opened_json'])
        if data.cell in opened:
            raise HTTPException(409, 'Эта клетка уже открыта')
        mines = set(json.loads(row['mines_json']))
        opened.append(data.cell)
        if data.cell in mines:
            status = 'lost'
        elif len(opened) == 20:
            status = 'won'
            db.execute('UPDATE players SET coins=coins+50, games_won=games_won+1 WHERE telegram_id=?', (user['id'],))
        else:
            status = 'playing'
        db.execute('UPDATE mines_games SET opened_json=?, status=? WHERE telegram_id=?',
                   (json.dumps(opened), status, user['id']))
        updated = db.execute('SELECT * FROM mines_games WHERE telegram_id=?', (user['id'],)).fetchone()
        player = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
        return {'game': game_json(updated), 'player': player_json(player),
                'message': ('Победа! +50 игровых монет' if status == 'won' else
                            'Попалась мина! Начни новую игру.' if status == 'lost' else 'Клетка открыта')}
