import json, random, time
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import main as M
from buildhouse import S, view, _claim, MAXLV, ADMIN_ID

router = APIRouter()
BETS = [200, 500, 1000, 3000, 5000, 10000, 50000]
CARS = {'lada': ('Lada Granta', 600), 'kia': ('Kia Rio', 900), 'toyota': ('Toyota Camry', 1500), 'mazda': ('Mazda 6', 2500),
        'bmw': ('BMW M5', 6000), 'audi': ('Audi RS7', 9000), 'merc': ('Mercedes AMG GT', 15000), 'porsche': ('Porsche 911', 40000),
        'ferrari': ('Ferrari F8', 120000), 'lambo': ('Lamborghini Aventador', 220000), 'rolls': ('Rolls-Royce Phantom', 400000),
        'bugatti': ('Bugatti Chiron', 900000)}
CASES = {'start': {'name': 'Стартовый', 'price': 1000, 'drops': {'lada': 50, 'kia': 30, 'toyota': 14, 'mazda': 5, 'bmw': 1}},
         'prem': {'name': 'Премиум', 'price': 10000, 'drops': {'mazda': 25, 'bmw': 34, 'audi': 20, 'merc': 14, 'porsche': 6, 'ferrari': 1}},
         'lux': {'name': 'Люкс', 'price': 100000, 'drops': {'merc': 45, 'porsche': 35, 'ferrari': 14, 'lambo': 4, 'rolls': 1.5, 'bugatti': 0.5}}}


@contextmanager
def T():
    with S() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS mines2 (telegram_id INTEGER PRIMARY KEY, bet INTEGER, mines INTEGER,
            mines_json TEXT, opened_json TEXT, status TEXT, created_at INTEGER)''')
        db.execute('CREATE TABLE IF NOT EXISTS cars (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, car TEXT NOT NULL, ts INTEGER NOT NULL)')
        yield db


def mult(k, m):  # коэффициент после k открытых клеток при m минах (RTP 97%)
    p = 0.97
    for i in range(k):
        p *= (25 - i) / (25 - m - i)
    return round(p, 2)


def gview(r):
    if not r:
        return None
    mines, op = set(json.loads(r['mines_json'])), json.loads(r['opened_json'])
    fin, m, k = r['status'] != 'playing', r['mines'], len(json.loads(r['opened_json']))
    cells = ['mine' if i in mines and (fin or i in op) else 'safe' if i in op else 'closed' for i in range(25)]
    return {'status': r['status'], 'bet': r['bet'], 'mines': m, 'opened': k, 'mult': mult(k, m),
            'next': mult(k + 1, m) if k < 25 - m else None, 'payout': int(r['bet'] * mult(k, m)), 'cells': cells}


def pay(db, u, amount, win=False):
    db.execute('UPDATE players SET coins=coins+?, games_won=games_won+? WHERE telegram_id=?', (amount, int(win), u['id']))


def cur(db, u):
    return db.execute('SELECT * FROM mines2 WHERE telegram_id=?', (u['id'],)).fetchone()


@router.get('/api/bh/mines')
def mines_get(request: Request):
    u = M.auth_request(request)
    with T() as db:
        return {'game': gview(cur(db, u))}


class Start(BaseModel):
    bet: int
    mines: int


@router.post('/api/bh/mines/start')
def mines_start(d: Start, request: Request):
    u = M.auth_request(request)
    if d.bet not in BETS or not 1 <= d.mines <= 20:
        raise HTTPException(400, 'Неверная ставка или число мин')
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        r = cur(db, u)
        if r and r['status'] == 'playing':
            raise HTTPException(409, 'Сначала закончи текущую игру')
        if v['player']['coins'] < d.bet:
            raise HTTPException(402, 'Не хватает долларов для ставки')
        db.execute('UPDATE players SET coins=coins-?, games_played=games_played+1 WHERE telegram_id=?', (d.bet, u['id']))
        db.execute('INSERT OR REPLACE INTO mines2 VALUES (?,?,?,?,?,?,?)', (u['id'], d.bet, d.mines,
                   json.dumps(sorted(random.SystemRandom().sample(range(25), d.mines))), '[]', 'playing', int(time.time())))
        return {**view(db, u), 'game': gview(cur(db, u))}


class Pick(BaseModel):
    cell: int


@router.post('/api/bh/mines/open')
def mines_open(d: Pick, request: Request):
    u = M.auth_request(request)
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        r = cur(db, u)
        if not r or r['status'] != 'playing':
            raise HTTPException(409, 'Начни новую игру')
        op = json.loads(r['opened_json'])
        if not 0 <= d.cell < 25 or d.cell in op:
            raise HTTPException(400, 'Нельзя открыть эту клетку')
        op.append(d.cell)
        st = 'playing'
        if d.cell in json.loads(r['mines_json']):
            st = 'lost'  # ставка сгорает
        elif len(op) == 25 - r['mines']:
            st = 'cashed'
            pay(db, u, int(r['bet'] * mult(len(op), r['mines'])), True)
        db.execute('UPDATE mines2 SET opened_json=?, status=? WHERE telegram_id=?', (json.dumps(op), st, u['id']))
        return {**view(db, u), 'game': gview(cur(db, u))}


@router.post('/api/bh/mines/cash')
def mines_cash(request: Request):
    u = M.auth_request(request)
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        r = cur(db, u)
        if not r or r['status'] != 'playing':
            raise HTTPException(409, 'Нет активной игры')
        k = len(json.loads(r['opened_json']))
        amount = r['bet'] if k == 0 else int(r['bet'] * mult(k, r['mines']))  # без ходов — возврат ставки
        pay(db, u, amount, amount > r['bet'])
        db.execute("UPDATE mines2 SET status='cashed' WHERE telegram_id=?", (u['id'],))
        return {**view(db, u), 'game': gview(cur(db, u))}


# ---------------------------------------------------------------- кейсы с машинами
@router.get('/api/bh/garage')
def garage(request: Request):
    u = M.auth_request(request)
    with T() as db:
        rows = db.execute('SELECT id, car FROM cars WHERE telegram_id=? ORDER BY id DESC LIMIT 60', (u['id'],)).fetchall()
        return {'cars': [{'id': r['id'], 'key': r['car'], 'name': CARS[r['car']][0], 'value': CARS[r['car']][1]} for r in rows],
                'cases': {k: {'name': c['name'], 'price': c['price'], 'drops': [{'name': CARS[x][0], 'value': CARS[x][1], 'w': w} for x, w in c['drops'].items()]} for k, c in CASES.items()}}


class Case(BaseModel):
    case: str


@router.post('/api/bh/case')
def open_case(d: Case, request: Request):
    u = M.auth_request(request)
    c = CASES.get(d.case)
    if not c:
        raise HTTPException(400, 'Нет такого кейса')
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        if view(db, u)['player']['coins'] < c['price']:
            raise HTTPException(402, 'Не хватает долларов')
        key = random.SystemRandom().choices(list(c['drops']), weights=list(c['drops'].values()))[0]
        db.execute('UPDATE players SET coins=coins-? WHERE telegram_id=?', (c['price'], u['id']))
        db.execute('INSERT INTO cars (telegram_id, car, ts) VALUES (?,?,?)', (u['id'], key, int(time.time())))
        return {**view(db, u), 'car': {'key': key, 'name': CARS[key][0], 'value': CARS[key][1]}}


class Sell(BaseModel):
    id: int


@router.post('/api/bh/sell')
def sell(d: Sell, request: Request):
    u = M.auth_request(request)
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        r = db.execute('SELECT car FROM cars WHERE id=? AND telegram_id=?', (d.id, u['id'])).fetchone()
        if not r:
            raise HTTPException(404, 'Машина не найдена')
        db.execute('DELETE FROM cars WHERE id=?', (d.id,))
        pay(db, u, CARS[r['car']][1])
        return {**view(db, u), 'got': CARS[r['car']][1]}


# ------------------------------------------------------------ магазин за звёзды
@router.post('/api/bh/buylevel')
def buylevel(request: Request):
    u = M.auth_request(request)
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        lv = v['house']['level']
        if lv >= MAXLV:
            raise HTTPException(409, 'Максимальный уровень')
        price = 10 + 5 * lv
        if v['gems'] < price:
            raise HTTPException(402, f'Не хватает звёзд: нужно {price}')
        _claim(db, u)
        db.execute('UPDATE bh SET gems=gems-?, house=house+1 WHERE telegram_id=?', (price, u['id']))
        return view(db, u)


class Conv(BaseModel):
    stars: int


@router.post('/api/bh/convert')
def convert(d: Conv, request: Request):
    u = M.auth_request(request)
    if not 1 <= d.stars <= 100000:
        raise HTTPException(400, 'Неверное количество')
    with T() as db:
        db.execute('BEGIN IMMEDIATE')
        v = view(db, u)
        if v['gems'] < d.stars:
            raise HTTPException(402, 'Не хватает звёзд')
        got = d.stars * 500 * v['house']['level']  # курс растёт с уровнем дома
        db.execute('UPDATE bh SET gems=gems-? WHERE telegram_id=?', (d.stars, u['id']))
        pay(db, u, got)
        return {**view(db, u), 'got': got}


# ------------------------------------------------------------------- рейтинг
@router.get('/api/bh/top')
def top(request: Request, by: str = 'house'):
    u = M.auth_request(request)
    order = 'b.house DESC, p.coins DESC' if by == 'house' else 'p.coins DESC'
    with T() as db:
        rows = db.execute(f'''SELECT p.telegram_id id, COALESCE(p.nickname,p.telegram_name) name, p.coins, b.house, b.avatar
            FROM players p JOIN bh b USING(telegram_id) WHERE b.blocked=0 AND p.telegram_id!=? ORDER BY {order} LIMIT 1000''',
                          (ADMIN_ID,)).fetchall()
    ids = [r['id'] for r in rows]
    return {'top': [dict(r) for r in rows[:20]], 'me': ids.index(u['id']) + 1 if u['id'] in ids else None}