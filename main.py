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
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
# Токен берём из Render -> Environment. Убираем пробелы, переносы строк и случайные кавычки.
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip().strip('"').strip("'").strip()
WEBAPP_URL = os.getenv('WEBAPP_URL', '').strip().rstrip('/') + '/'
DB_PATH = Path(os.getenv('DB_PATH', str(ROOT / 'database.db')))
INIT_DATA_MAX_AGE = 24 * 3600
BOT_USERNAME = '?'  # заполняется при старте через getMe

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('miniapp')
dp = Dispatcher()
NO_CACHE = {'Cache-Control': 'no-store'}


# ----------------------------------------------------------------- база данных
@contextmanager
def db_session():
    """Открывает соединение, коммитит при успехе, откатывает при ошибке и ВСЕГДА закрывает."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with db_session() as db:
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


# ----------------------------------------------------------- проверка initData
class AuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _calc_hash(params: dict, secret: bytes) -> str:
    data_check = '\n'.join(f'{k}={v}' for k, v in sorted(params.items()))
    return hmac.new(secret, data_check.encode('utf-8'), hashlib.sha256).hexdigest()


def verify_init_data(init_data: str, token: str, max_age: int = INIT_DATA_MAX_AGE) -> dict:
    """Проверка подписи Telegram Mini App (HMAC-SHA256 по токену бота).

    По документации Telegram из строки проверки исключается ТОЛЬКО поле hash,
    поле signature остаётся. Для надёжности пробуем и вариант без signature —
    подделать оба без токена бота невозможно, так что безопасность не страдает.
    """
    if not init_data:
        raise AuthError('no_init_data')
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        raise AuthError('malformed')
    received_hash = params.pop('hash', None)
    if not received_hash:
        raise AuthError('no_hash')

    secret = hmac.new(b'WebAppData', token.encode('utf-8'), hashlib.sha256).digest()
    variants = [params]
    if 'signature' in params:
        variants.append({k: v for k, v in params.items() if k != 'signature'})
    received = received_hash.strip().lower().encode('utf-8')
    if not any(hmac.compare_digest(_calc_hash(v, secret).encode('utf-8'), received) for v in variants):
        raise AuthError('bad_hash')

    try:
        auth_date = int(params['auth_date'])
    except (KeyError, ValueError):
        raise AuthError('bad_auth_date')
    now = int(time.time())
    if auth_date > now + 300 or now - auth_date > max_age:
        raise AuthError('expired')

    try:
        user = json.loads(params['user'])
        user_id = int(user['id'])
    except (KeyError, ValueError, TypeError):
        raise AuthError('no_user')
    if user_id <= 0:
        raise AuthError('no_user')
    return {'id': user_id,
            'first_name': str(user.get('first_name') or 'Игрок')[:100],
            'username': str(user.get('username') or '')[:100]}


def authenticate(init_data: str) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(503, 'BOT_TOKEN не настроен на сервере')
    try:
        user = verify_init_data(init_data, BOT_TOKEN)
    except AuthError as exc:
        log.warning('Telegram authorization failed: %s (init_data length=%d)', exc.code, len(init_data or ''))
        messages = {
            'no_init_data': 'Открой Mini App кнопкой «Открыть» внутри Telegram, а не в браузере.',
            'expired': 'Данные Telegram устарели (expired). Закрой Mini App и открой заново.',
            'bad_hash': (f'Не удалось подтвердить профиль Telegram (bad_hash). Сервер проверяет бота '
                         f'@{BOT_USERNAME}: открой Mini App из чата именно с ним и убедись, что BOT_TOKEN '
                         f'на Render принадлежит этому боту.'),
        }
        detail = messages.get(exc.code, f'Не удалось подтвердить профиль Telegram ({exc.code}).')
        raise HTTPException(401, detail)
    import buildhouse
    buildhouse.touch(user)  # блокировка + last_seen
    return user


def auth_request(request: Request) -> dict:
    return authenticate(request.headers.get('X-Telegram-Init-Data', ''))


# ------------------------------------------------------------------ игровая логика
def get_player(db, user):
    name = user['first_name']
    row = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
    if row is None:
        db.execute('INSERT OR IGNORE INTO players (telegram_id, telegram_name, created_at) VALUES (?, ?, ?)',
                   (user['id'], name, int(time.time())))
        row = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
    if row['telegram_name'] != name:
        db.execute('UPDATE players SET telegram_name=? WHERE telegram_id=?', (name, user['id']))
        row = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
    return row


def player_json(row):
    return {'telegram_id': row['telegram_id'], 'telegram_name': row['telegram_name'],
            'nickname': row['nickname'] or row['telegram_name'], 'custom_nickname': row['nickname'],
            'coins': row['coins'], 'games_played': row['games_played'], 'games_won': row['games_won']}


def game_json(row):
    if row is None:
        return None
    mines = set(json.loads(row['mines_json']))
    opened = set(json.loads(row['opened_json']))
    status = row['status']
    finished = status != 'playing'
    cells = []
    for index in range(25):
        if index in mines and (index in opened or finished):
            cells.append({'state': 'mine'})  # после конца игры показываем все мины
        elif index not in opened:
            cells.append({'state': 'closed'})
        else:
            x, y = index % 5, index // 5
            around = sum(((ny * 5 + nx) in mines)
                         for ny in range(max(0, y - 1), min(5, y + 2))
                         for nx in range(max(0, x - 1), min(5, x + 2)) if (nx, ny) != (x, y))
            cells.append({'state': 'safe', 'around': around})
    return {'status': status, 'opened': len(opened - mines), 'total_safe': 20, 'cells': cells}


# -------------------------------------------------------------------- запуск
@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_USERNAME
    if not BOT_TOKEN:
        raise RuntimeError('Добавь BOT_TOKEN в Render -> Environment')
    if not WEBAPP_URL.startswith('https://'):
        raise RuntimeError('Добавь ссылку на Mini App (https://...) в WEBAPP_URL')
    init_db()
    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username or str(me.id)
        log.info('Бот авторизован: @%s (id=%s)', BOT_USERNAME, me.id)
    except TelegramUnauthorizedError:
        await bot.session.close()
        raise RuntimeError('BOT_TOKEN неверный или отозван. Возьми актуальный токен в @BotFather.')
    except Exception:
        log.exception('Не удалось вызвать getMe (временная ошибка сети?)')
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        log.exception('delete_webhook не удался')

    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    polling.add_done_callback(
        lambda t: (not t.cancelled()) and t.exception() and log.error('Polling упал: %r', t.exception()))
    app.state.bot = bot
    try:
        yield
    finally:
        polling.cancel()
        try:
            await polling
        except BaseException:
            pass
        await bot.session.close()


app = FastAPI(lifespan=lifespan)
_parsed = urlsplit(WEBAPP_URL)
ORIGIN = f'{_parsed.scheme}://{_parsed.netloc}'
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_methods=['GET', 'POST'],
                   allow_headers=['Content-Type', 'X-Telegram-Init-Data'])


@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text='🚀 Открыть', web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer('🎮 Профиль и игра «Мины» доступны в Mini App!', reply_markup=kb)


# ----------------------------------------------------------------- служебные
@app.get('/health')
def health():
    return {'status': 'ok', 'api': 'reachable', 'bot': BOT_USERNAME}


@app.get('/health/db')
def database_health():
    try:
        with db_session() as db:
            db.execute('SELECT 1').fetchone()
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        return {'database': 'connected', 'tables_ready': 'players' in tables and 'mines_games' in tables}
    except sqlite3.Error:
        log.exception('Database health check failed')
        raise HTTPException(503, 'SQLite3 недоступна; смотри Logs в Render')


@app.get('/api/diagnostics')
def diagnostics(request: Request):
    user = auth_request(request)
    try:
        with db_session() as db:
            db.execute('CREATE TABLE IF NOT EXISTS db_probe (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
            key = os.urandom(8).hex()
            db.execute('INSERT INTO db_probe (id, value) VALUES (?, ?)', (key, 'created'))
            db.commit()
            read_ok = db.execute('SELECT value FROM db_probe WHERE id=?', (key,)).fetchone()[0] == 'created'
            db.execute('UPDATE db_probe SET value=? WHERE id=?', ('updated', key))
            db.commit()
            update_ok = db.execute('SELECT value FROM db_probe WHERE id=?', (key,)).fetchone()[0] == 'updated'
            db.execute('DELETE FROM db_probe WHERE id=?', (key,))
            db.commit()
            delete_ok = db.execute('SELECT 1 FROM db_probe WHERE id=?', (key,)).fetchone() is None
            row = get_player(db, user)
            profile_ok = row is not None and int(row['telegram_id']) == user['id']
        return {'telegram_auth': 'ok', 'sqlite_write': True, 'sqlite_read': read_ok,
                'sqlite_update': update_ok, 'sqlite_delete': delete_ok, 'profile_read': profile_ok}
    except sqlite3.Error:
        log.exception('Database diagnostic failed')
        raise HTTPException(503, 'Ошибка записи/чтения SQLite3. Открой Logs в Render')


@app.get('/')
def index():
    return FileResponse(ROOT / 'index.html', headers=NO_CACHE)


@app.get('/app.js')
def javascript():
    return FileResponse(ROOT / 'app.js', media_type='application/javascript', headers=NO_CACHE)


# ---------------------------------------------------------------------- API
@app.get('/api/profile')
def profile(request: Request):
    user = auth_request(request)
    with db_session() as db:
        return {'player': player_json(get_player(db, user))}


class Nickname(BaseModel):
    nickname: str


@app.post('/api/nickname')
def nickname(data: Nickname, request: Request):
    user = auth_request(request)
    new_name = data.nickname.strip()
    if len(new_name) > 24 or (new_name and (len(new_name) < 2 or not re.fullmatch(r'[\w -]+', new_name, re.UNICODE))):
        raise HTTPException(400, 'Ник: 2–24 символа, буквы, цифры, пробел, _ или -. Пустое поле — сброс.')
    with db_session() as db:
        get_player(db, user)
        db.execute('UPDATE players SET nickname=? WHERE telegram_id=?', (new_name or None, user['id']))
        row = db.execute('SELECT * FROM players WHERE telegram_id=?', (user['id'],)).fetchone()
        return {'player': player_json(row)}


import buildhouse  # noqa: E402  (BuildHouse: дом, валюты, админ-панель)
app.include_router(buildhouse.router)
import bh2  # noqa: E402  (мины со ставками, кейсы, магазин, рейтинг)
app.include_router(bh2.router)