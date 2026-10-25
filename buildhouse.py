import os, sys, time, platform
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import main as M

ADMIN_ID = int(os.getenv('ADMIN_ID', '1181838335'))
STARTED = time.time()
router = APIRouter()
NAMES = ['Палатка', 'Хижина', 'Домик', 'Коттедж', 'Таунхаус', 'Вилла', 'Особняк', 'Поместье', 'Замок', 'Небоскрёб']
COST = [500, 1500, 4000, 9000, 20000, 45000, 100000, 220000, 500000]  # цена перехода на уровень 2..10
INCOME = [20, 50, 110, 220, 420, 800, 1500, 2800, 5000, 9000]       # монет в час
CAP_H, MAX_E = 8, 50
AVATARS = ['🏠', '🔨', '👷', '🏗️', '🦾', '👑', '🐱', '🚀']


@contextmanager
def S():
    with M.db_session() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS bh (telegram_id INTEGER PRIMARY KEY,
            gems INTEGER NOT NULL DEFAULT 0, house INTEGER NOT NULL DEFAULT 1,
            last_claim INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0, reason TEXT,
            last_seen INTEGER NOT NULL DEFAULT 0, energy REAL NOT NULL DEFAULT 50,
            energy_ts INTEGER NOT NULL DEFAULT 0, last_daily INTEGER NOT NULL DEFAULT 0,
            taps INTEGER NOT NULL DEFAULT 0, earned INTEGER NOT NULL DEFAULT 0,
            avatar TEXT NOT NULL DEFAULT '🏠')''')
        yield db


def touch(u):
    """Вызывается при каждой авторизации: создаёт запись, проверяет блокировку."""
    now = int(time.time())
    with S() as db:
        db.execute('INSERT OR IGNORE INTO bh (telegram_id,last_claim,energy_ts) VALUES (?,?,?)', (u['id'], now, now))
        r = db.execute('SELECT blocked,reason FROM bh WHERE telegram_id=?', (u['id'],)).fetchone()
        if r['blocked'] and u['id'] != ADMIN_ID:
            raise HTTPException(403, 'Аккаунт заблокирован' + (f": {r['reason']}" if r['reason'] else ''))
        db.execute('UPDATE bh SET last_seen=? WHERE telegram_id=?', (now, u['id']))


def view(db, u):
    p = M.get_player(db, u)
    b = db.execute('SELECT * FROM bh WHERE telegram_id=?', (u['id'],)).fetchone()
    now, lv = int(time.time()), b['house']
    en = min(MAX_E, b['energy'] + (now - b['energy_ts']) / 2)
    return {'player': M.player_json(p), 'gems': b['gems'], 'avatar': b['avatar'], 'energy': int(en), 'max_energy': MAX_E,
            'daily_ready': now - b['last_daily'] >= 86400, 'is_admin': u['id'] == ADMIN_ID,
            'house': {'level': lv, 'name': NAMES[lv - 1], 'income': INCOME[lv - 1], 'cap_hours': CAP_H,
                      'pending': int(min(now - b['last_claim'], CAP_H * 3600) * INCOME[lv - 1] / 3600),
                      'next_cost': COST[lv - 1] if lv < 10 else None, 'next_income': INCOME[lv] if lv < 10 else None}}


def _claim(db, u):
    v = view(db, u)
    amt = v['house']['pending']
    db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (amt, u['id']))
    db.execute('UPDATE bh SET last_claim=?, earned=earned+? WHERE telegram_id=?', (int(time.time()), amt, u['id']))
    return amt


@router.get('/api/bh/state')
def state(request: Request):
    u = M.auth_request(request)
    with S() as db:
        return view(db, u)


@router.post('/api/bh/claim')
def claim(request: Request):
    u = M.auth_request(request)
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        got = _claim(db, u)
        return {**view(db, u), 'got': got}


@router.post('/api/bh/upgrade')
def upgrade(request: Request):
    u = M.auth_request(request)
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        lv = v['house']['level']
        if lv >= 10:
            raise HTTPException(409, 'Максимальный уровень дома')
        if v['player']['coins'] < COST[lv - 1]:
            raise HTTPException(402, f'Не хватает монет: нужно {COST[lv - 1]}')
        _claim(db, u)  # забираем накопленный доход по старой ставке
        db.execute('UPDATE players SET coins=coins-? WHERE telegram_id=?', (COST[lv - 1], u['id']))
        db.execute('UPDATE bh SET house=house+1 WHERE telegram_id=?', (u['id'],))
        return view(db, u)


class Tap(BaseModel):
    n: int = 1


@router.post('/api/bh/tap')
def tap(d: Tap, request: Request):
    u = M.auth_request(request)
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        n = min(max(d.n, 1), 10, v['energy'])
        if n < 1:
            raise HTTPException(429, 'Нет энергии — подожди, она восстанавливается')
        gain = n * (1 + v['house']['level'])
        now = int(time.time())
        db.execute('UPDATE bh SET energy=?, energy_ts=?, taps=taps+?, earned=earned+? WHERE telegram_id=?',
                   (v['energy'] - n, now, n, gain, u['id']))
        db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (gain, u['id']))
        return {**view(db, u), 'got': gain}


@router.post('/api/bh/daily')
def daily(request: Request):
    u = M.auth_request(request)
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        if not v['daily_ready']:
            raise HTTPException(409, 'Бонус уже получен, приходи завтра')
        c = 100 * v['house']['level']
        db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (c, u['id']))
        db.execute('UPDATE bh SET gems=gems+1, last_daily=?, earned=earned+? WHERE telegram_id=?', (int(time.time()), c, u['id']))
        return {**view(db, u), 'got': c}


class Avatar(BaseModel):
    avatar: str


@router.post('/api/bh/avatar')
def avatar(d: Avatar, request: Request):
    u = M.auth_request(request)
    if d.avatar not in AVATARS:
        raise HTTPException(400, 'Неверный аватар')
    with S() as db:
        M.get_player(db, u)
        db.execute('UPDATE bh SET avatar=? WHERE telegram_id=?', (d.avatar, u['id']))
        return view(db, u)


# ------------------------------------------------------------------ админ-панель
def A(request):
    u = M.auth_request(request)
    if u['id'] != ADMIN_ID:
        raise HTTPException(403, 'Нет доступа')
    return u


@router.get('/api/admin/stats')
def stats(request: Request):
    A(request)
    now = int(time.time())
    with S() as db:
        one = lambda q, a=(): db.execute(q, a).fetchone()[0] or 0
        t0 = time.time()
        db.execute('CREATE TABLE IF NOT EXISTS db_probe (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute("INSERT OR REPLACE INTO db_probe VALUES ('p','ok')")
        ok = db.execute("SELECT value FROM db_probe WHERE id='p'").fetchone()[0] == 'ok'
        db.execute("DELETE FROM db_probe WHERE id='p'")
        ms = round((time.time() - t0) * 1000, 1)
        st = {'players': one('SELECT COUNT(*) FROM players'), 'blocked': one('SELECT COUNT(*) FROM bh WHERE blocked=1'),
              'active_24h': one('SELECT COUNT(*) FROM bh WHERE last_seen>?', (now - 86400,)),
              'coins_total': one('SELECT SUM(coins) FROM players'), 'gems_total': one('SELECT SUM(gems) FROM bh'),
              'games_played': one('SELECT SUM(games_played) FROM players'), 'games_won': one('SELECT SUM(games_won) FROM players'),
              'taps': one('SELECT SUM(taps) FROM bh'),
              'levels': {str(r[0]): r[1] for r in db.execute('SELECT house,COUNT(*) FROM bh GROUP BY house')}}
        rows = {t: one(f'SELECT COUNT(*) FROM {t}') for t in ('players', 'bh', 'mines_games')}
    size = os.path.getsize(M.DB_PATH) if M.DB_PATH.exists() else 0
    diag = {'Авторизация Telegram (initData)': True, 'BOT_TOKEN задан': bool(M.BOT_TOKEN),
            'Бот (getMe)': M.BOT_USERNAME not in ('?', ''), 'WEBAPP_URL https': M.WEBAPP_URL.startswith('https://'),
            'SQLite запись/чтение': ok, 'Файл БД существует': M.DB_PATH.exists()}
    info = {'Бот': '@' + M.BOT_USERNAME, 'WEBAPP_URL': M.WEBAPP_URL, 'Путь БД': str(M.DB_PATH),
            'Размер БД, КБ': round(size / 1024, 1), 'Запись в БД, мс': ms, 'Python': platform.python_version(),
            'Аптайм, мин': int((time.time() - STARTED) / 60), 'Время сервера': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC',
            'Строк в таблицах': rows, 'ADMIN_ID': ADMIN_ID}
    return {'stats': st, 'diag': diag, 'info': info}


@router.get('/api/admin/players')
def players(request: Request, q: str = ''):
    A(request)
    like = f'%{q.strip()}%'
    with S() as db:
        rows = db.execute('''SELECT p.telegram_id, p.telegram_name, p.nickname, p.coins, p.games_played, p.games_won,
            p.created_at, b.gems, b.house, b.blocked, b.reason, b.last_seen, b.taps, b.earned
            FROM players p LEFT JOIN bh b USING(telegram_id)
            WHERE ?='' OR CAST(p.telegram_id AS TEXT) LIKE ? OR p.telegram_name LIKE ? OR IFNULL(p.nickname,'') LIKE ?
            ORDER BY b.last_seen DESC LIMIT 50''', (q.strip(), like, like, like)).fetchall()
        return {'players': [dict(r) for r in rows]}


class Grant(BaseModel):
    telegram_id: int
    coins: int = 0
    gems: int = 0


@router.post('/api/admin/grant')
def grant(d: Grant, request: Request):
    A(request)
    if abs(d.coins) > 10**9 or abs(d.gems) > 10**6:
        raise HTTPException(400, 'Слишком большое значение')
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM players WHERE telegram_id=?', (d.telegram_id,)).fetchone():
            raise HTTPException(404, 'Игрок не найден (он должен хотя бы раз открыть приложение)')
        now = int(time.time())
        db.execute('INSERT OR IGNORE INTO bh (telegram_id,last_claim,energy_ts) VALUES (?,?,?)', (d.telegram_id, now, now))
        db.execute('UPDATE players SET coins=MAX(0,coins+?) WHERE telegram_id=?', (d.coins, d.telegram_id))
        db.execute('UPDATE bh SET gems=MAX(0,gems+?) WHERE telegram_id=?', (d.gems, d.telegram_id))
        M.log.info('ADMIN grant %s coins=%s gems=%s', d.telegram_id, d.coins, d.gems)
        return {'ok': True}


class Block(BaseModel):
    telegram_id: int
    blocked: bool
    reason: str = ''


@router.post('/api/admin/block')
def block(d: Block, request: Request):
    A(request)
    if d.telegram_id == ADMIN_ID:
        raise HTTPException(400, 'Нельзя заблокировать администратора')
    with S() as db:
        now = int(time.time())
        db.execute('INSERT OR IGNORE INTO bh (telegram_id,last_claim,energy_ts) VALUES (?,?,?)', (d.telegram_id, now, now))
        db.execute('UPDATE bh SET blocked=?, reason=? WHERE telegram_id=?', (int(d.blocked), d.reason[:100], d.telegram_id))
        M.log.info('ADMIN block %s=%s', d.telegram_id, d.blocked)
        return {'ok': True}