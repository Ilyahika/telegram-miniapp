import os, sys, time, platform, shutil, random, sqlite3
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import main as M
from catalog import CARS, bonus

ADMIN_ID = int(os.getenv('ADMIN_ID', '1181838335'))
STARTED = time.time()
router = APIRouter()
NAMES = ['Палатка', 'Хижина', 'Домик', 'Коттедж', 'Таунхаус', 'Вилла', 'Особняк', 'Поместье', 'Замок', 'Небоскрёб',
         'Резиденция', 'Дворец', 'Крепость', 'Башня', 'Комплекс', 'Отель', 'Курорт', 'Остров', 'Квартал', 'Город-сад',
         'Мегаполис', 'Технопарк', 'Космопорт', 'Орбитальная станция', 'Лунная база', 'Марс-колония', 'Звёздный город',
         'Галактический хаб', 'Вселенский дворец', 'Обитель богов']
MAXLV = len(NAMES)
INF = 10**15


def cost(lv):    # цена перехода с уровня lv на lv+1, $
    return int(500 * 1.55 ** (lv - 1) // 10 * 10)


def income(lv):  # доход, $ в час
    return int(20 * 1.42 ** (lv - 1))


def topup(db, u):  # у админа бесконечные ресурсы
    db.execute('UPDATE players SET coins=MAX(coins,?) WHERE telegram_id=?', (INF, u['id']))
    db.execute('UPDATE bh SET gems=MAX(gems,?) WHERE telegram_id=?', (INF, u['id']))
    return db.execute('SELECT * FROM players WHERE telegram_id=?', (u['id'],)).fetchone()


CAP_H, MAX_E = 8, 50
_mig = False
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
        db.execute('CREATE TABLE IF NOT EXISTS cars (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, car TEXT NOT NULL, ts INTEGER NOT NULL, parked INTEGER NOT NULL DEFAULT 0)')
        global _mig
        if not _mig:
            try:
                db.execute('ALTER TABLE cars ADD COLUMN parked INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError:
                pass
            db.execute("DELETE FROM cars WHERE car NOT GLOB '[0-9]*'")  # старые машины прошлой версии
            _mig = True
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
    now = int(time.time())
    db.execute('INSERT OR IGNORE INTO bh (telegram_id,last_claim,energy_ts) VALUES (?,?,?)', (u['id'], now, now))
    if u['id'] == ADMIN_ID:
        p = topup(db, u)
    b = db.execute('SELECT * FROM bh WHERE telegram_id=?', (u['id'],)).fetchone()
    cr = db.execute('SELECT car FROM cars WHERE telegram_id=? AND parked=1', (u['id'],)).fetchone()
    car = None
    if cr:
        n, v = CARS[int(cr['car'])]
        car = {'name': n, 'value': v, 'bonus': bonus(v)}
    lv = b['house']
    cb = car['bonus'] if car else 0
    inc = income(lv) + cb
    en = min(MAX_E, b['energy'] + (now - b['energy_ts']) / 2)
    return {'player': M.player_json(p), 'gems': b['gems'], 'avatar': b['avatar'], 'energy': int(en), 'max_energy': MAX_E,
            'daily_ready': now - b['last_daily'] >= 86400, 'is_admin': u['id'] == ADMIN_ID, 'car': car,
            'house': {'level': lv, 'name': NAMES[lv - 1], 'income': inc, 'base_income': income(lv), 'cap_hours': CAP_H,
                      'pending': int(min(now - b['last_claim'], CAP_H * 3600) * inc / 3600),
                      'next_cost': cost(lv) if lv < MAXLV else None, 'next_income': income(lv + 1) + cb if lv < MAXLV else None,
                      'next_stars': 10 + 5 * lv if lv < MAXLV else None, 'max': MAXLV}}


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
        if lv >= MAXLV:
            raise HTTPException(409, 'Максимальный уровень дома')
        if v['player']['coins'] < cost(lv):
            raise HTTPException(402, f'Не хватает монет: нужно {cost(lv)}')
        _claim(db, u)  # забираем накопленный доход по старой ставке
        db.execute('UPDATE players SET coins=coins-? WHERE telegram_id=?', (cost(lv), u['id']))
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
    nA = f'telegram_id!={ADMIN_ID}'  # админ с бесконечным балансом в суммы не входит
    with S() as db:
        one = lambda q, a=(): db.execute(q, a).fetchone()[0] or 0
        t0 = time.perf_counter()
        db.execute('CREATE TABLE IF NOT EXISTS db_probe (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute("INSERT OR REPLACE INTO db_probe VALUES ('p','ok')")
        ok = db.execute("SELECT value FROM db_probe WHERE id='p'").fetchone()[0] == 'ok'
        db.execute("DELETE FROM db_probe WHERE id='p'")
        ms = round((time.perf_counter() - t0) * 1000, 1)
        integ = db.execute('PRAGMA quick_check').fetchone()[0]
        st = {'players': one('SELECT COUNT(*) FROM players'), 'blocked': one('SELECT COUNT(*) FROM bh WHERE blocked=1'),
              'online_15m': one('SELECT COUNT(*) FROM bh WHERE last_seen>?', (now - 900,)),
              'active_24h': one('SELECT COUNT(*) FROM bh WHERE last_seen>?', (now - 86400,)),
              'new_24h': one('SELECT COUNT(*) FROM players WHERE created_at>?', (now - 86400,)),
              'coins_total': one(f'SELECT SUM(coins) FROM players WHERE {nA}'), 'gems_total': one(f'SELECT SUM(gems) FROM bh WHERE {nA}'),
              'games_played': one('SELECT SUM(games_played) FROM players'), 'games_won': one('SELECT SUM(games_won) FROM players'),
              'taps': one('SELECT SUM(taps) FROM bh'), 'cars': one('SELECT COUNT(*) FROM cars'),
              'levels': {str(r[0]): r[1] for r in db.execute('SELECT house,COUNT(*) FROM bh GROUP BY house ORDER BY house')}}
        rows = {}
        for t in ('players', 'bh', 'cars', 'mines2'):
            try:
                rows[t] = one(f'SELECT COUNT(*) FROM {t}')
            except sqlite3.OperationalError:
                rows[t] = 0
    size = os.path.getsize(M.DB_PATH) if M.DB_PATH.exists() else 0
    free = shutil.disk_usage(str(M.DB_PATH.parent)).free // 2**20
    up = int(time.time() - STARTED)
    chk = lambda n, s_, d: {'n': n, 's': s_, 'd': d}
    checks = [chk('Авторизация Telegram', 'ok', 'initData подтверждена, ты — админ'),
              chk('BOT_TOKEN', 'ok' if M.BOT_TOKEN else 'fail', ('id бота ' + M.BOT_TOKEN.split(':')[0]) if M.BOT_TOKEN else 'не задан'),
              chk('Бот (getMe)', 'ok' if M.BOT_USERNAME not in ('?', '') else 'fail', '@' + M.BOT_USERNAME),
              chk('WEBAPP_URL', 'ok' if M.WEBAPP_URL.startswith('https://') else 'fail', M.WEBAPP_URL),
              chk('SQLite запись/чтение', 'ok' if ok else 'fail', f'{ms} мс'),
              chk('Целостность БД', 'ok' if integ == 'ok' else 'fail', integ),
              chk('Файл БД', 'ok' if M.DB_PATH.exists() else 'fail', f'{round(size / 1024, 1)} КБ'),
              chk('Свободно на диске', 'ok' if free > 200 else 'warn', f'{free} МБ'),
              chk('Время работы', 'ok' if up > 120 else 'warn', f'{up // 3600} ч {up // 60 % 60} мин' + (' (недавний рестарт: прогресс на Render мог сброситься)' if up < 120 else ''))]
    info = {'Python': platform.python_version(), 'Сервер (UTC)': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()), 'Путь БД': str(M.DB_PATH),
            'ADMIN_ID': ADMIN_ID, 'Версия': 'BuildHouse 3.0'}
    return {'stats': st, 'checks': checks, 'info': info, 'rows': rows, 'db_ms': ms}


SORTS = {'last_seen': 'b.last_seen', 'coins': 'p.coins', 'gems': 'b.gems', 'house': 'b.house', 'created_at': 'p.created_at', 'earned': 'b.earned'}


@router.get('/api/admin/players')
def players(request: Request, q: str = '', flt: str = 'all', sort: str = 'last_seen'):
    A(request)
    q, now = q.strip(), int(time.time())
    where = {'online': f'b.last_seen>{now - 900}', 'blocked': 'b.blocked=1', 'new': f'p.created_at>{now - 86400}'}.get(flt, '1=1')
    like = f'%{q}%'
    with S() as db:
        rows = db.execute(f'''SELECT p.telegram_id, p.telegram_name, p.nickname, p.coins, p.games_played, p.games_won, p.created_at,
            b.gems, b.house, b.blocked, b.reason, b.last_seen, b.taps, b.earned FROM players p LEFT JOIN bh b USING(telegram_id)
            WHERE ({where}) AND (?='' OR CAST(p.telegram_id AS TEXT) LIKE ? OR p.telegram_name LIKE ? OR IFNULL(p.nickname,'') LIKE ?)
            ORDER BY {SORTS.get(sort, 'b.last_seen')} DESC LIMIT 100''', (q, like, like, like)).fetchall()
        return {'players': [dict(r) for r in rows], 'admin_id': ADMIN_ID}


@router.get('/api/admin/player')
def player_card(request: Request, id: int):
    A(request)
    with S() as db:
        r = db.execute('''SELECT p.*, b.gems, b.house, b.blocked, b.reason, b.last_seen, b.taps, b.earned FROM players p
            LEFT JOIN bh b USING(telegram_id) WHERE p.telegram_id=?''', (id,)).fetchone()
        if not r:
            raise HTTPException(404, 'Игрок не найден')
        cars = [{'name': CARS[int(c['car'])][0], 'value': CARS[int(c['car'])][1], 'parked': bool(c['parked'])}
                for c in db.execute('SELECT car, parked FROM cars WHERE telegram_id=? ORDER BY parked DESC, id DESC LIMIT 30', (id,))]
        try:
            g = db.execute('SELECT bet, mines, status FROM mines2 WHERE telegram_id=?', (id,)).fetchone()
        except sqlite3.OperationalError:
            g = None
        d = dict(r)
        d.update(cars=cars, game=dict(g) if g else None, is_admin=id == ADMIN_ID)
        return d


class Act(BaseModel):
    telegram_id: int
    act: str
    value: str = ''


@router.post('/api/admin/act')
def act(d: Act, request: Request):
    A(request)
    t, a, now = d.telegram_id, d.act, int(time.time())
    try:
        n = int(float(d.value or 0))
    except ValueError:
        raise HTTPException(400, 'Число введено неверно')
    if abs(n) > 10**12:
        raise HTTPException(400, 'Слишком большое число')
    if t == ADMIN_ID and a in ('block', 'reset', 'clear_garage'):
        raise HTTPException(400, 'Это действие нельзя применить к админу')
    with S() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM players WHERE telegram_id=?', (t,)).fetchone():
            raise HTTPException(404, 'Игрок не найден')
        db.execute('INSERT OR IGNORE INTO bh (telegram_id,last_claim,energy_ts) VALUES (?,?,?)', (t, now, now))
        Q = lambda sql, *args: db.execute(sql, args)
        if a == 'coins_add': Q('UPDATE players SET coins=MAX(0,coins+?) WHERE telegram_id=?', n, t)
        elif a == 'coins_set': Q('UPDATE players SET coins=MAX(0,?) WHERE telegram_id=?', n, t)
        elif a == 'gems_add': Q('UPDATE bh SET gems=MAX(0,gems+?) WHERE telegram_id=?', n, t)
        elif a == 'gems_set': Q('UPDATE bh SET gems=MAX(0,?) WHERE telegram_id=?', n, t)
        elif a == 'house_add': Q('UPDATE bh SET house=MIN(?,MAX(1,house+?)), last_claim=? WHERE telegram_id=?', MAXLV, n, now, t)
        elif a == 'house_set': Q('UPDATE bh SET house=MIN(?,MAX(1,?)), last_claim=? WHERE telegram_id=?', MAXLV, n, now, t)
        elif a == 'give_car':
            i = n if 0 <= n < len(CARS) and d.value != '' else random.randrange(len(CARS))
            Q('INSERT INTO cars (telegram_id,car,ts) VALUES (?,?,?)', t, str(i), now)
        elif a == 'clear_garage': Q('DELETE FROM cars WHERE telegram_id=?', t)
        elif a == 'block': Q('UPDATE bh SET blocked=1, reason=? WHERE telegram_id=?', d.value[:100], t)
        elif a == 'unblock': Q('UPDATE bh SET blocked=0, reason=NULL WHERE telegram_id=?', t)
        elif a == 'refill_energy': Q('UPDATE bh SET energy=?, energy_ts=? WHERE telegram_id=?', MAX_E, now, t)
        elif a == 'daily_reset': Q('UPDATE bh SET last_daily=0 WHERE telegram_id=?', t)
        elif a == 'reset':
            Q('DELETE FROM cars WHERE telegram_id=?', t)
            try: Q('DELETE FROM mines2 WHERE telegram_id=?', t)
            except sqlite3.OperationalError: pass
            Q('UPDATE players SET coins=0, games_played=0, games_won=0, nickname=NULL WHERE telegram_id=?', t)
            Q("UPDATE bh SET gems=0, house=1, earned=0, taps=0, last_claim=?, avatar='🏠', last_daily=0 WHERE telegram_id=?", now, t)
        else:
            raise HTTPException(400, 'Неизвестное действие')
        M.log.info('ADMIN act %s %s %s', t, a, d.value)
        return {'ok': True}


class Msg(BaseModel):
    telegram_id: int
    text: str


@router.post('/api/admin/message')
async def message(d: Msg, request: Request):
    A(request)
    try:
        await M.app.state.bot.send_message(d.telegram_id, d.text[:1000])
    except Exception as e:
        raise HTTPException(400, f'Не удалось отправить: {type(e).__name__}')
    return {'ok': True}


class Grant(BaseModel):
    telegram_id: int
    coins: int = 0
    gems: int = 0
    house: int = 0


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
        if 1 <= d.house <= MAXLV:
            db.execute('UPDATE bh SET house=?, last_claim=? WHERE telegram_id=?', (d.house, now, d.telegram_id))
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