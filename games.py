"""
games.py — игры и магазин: «Мины» со ставками, кейсы с машинами, гараж, магазин за звёзды, рейтинг.
"""
import json
import random
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from buildhouse import MAX_LEVEL, claim_pending, star_price, view
from catalog import CARS, CASES, CASES_PUBLIC, car_info
from config import ADMIN_ID
from db import session

router = APIRouter()
rng = random.SystemRandom()                      # криптостойкий генератор — результат нельзя предсказать
BETS = [200, 500, 1000, 3000, 5000, 10000, 50000]
FIELD = 25                                       # поле 5×5


# =============================================================================== МИНЫ
@lru_cache(maxsize=None)
def mult(opened: int, mines: int) -> float:
    """Коэффициент выплаты после `opened` открытых клеток при `mines` минах (возврат игроку 97%)."""
    p = 0.97
    for i in range(opened):
        p *= (FIELD - i) / (FIELD - mines - i)   # вероятность, что очередная клетка безопасна
    return round(p, 2)


def game_view(row):
    """Игра в виде словаря для клиента. Позиции мин скрыты, пока игра не закончена."""
    if not row:
        return None
    mines = set(json.loads(row['mines_json']))
    opened = json.loads(row['opened_json'])
    finished = row['status'] != 'playing'
    k, m = len(opened), row['mines']
    cells = ['mine' if i in mines and (finished or i in opened) else 'safe' if i in opened else 'closed'
             for i in range(FIELD)]
    return {'status': row['status'], 'bet': row['bet'], 'mines': m, 'opened': k, 'mult': mult(k, m),
            'next': mult(k + 1, m) if k < FIELD - m else None, 'payout': int(row['bet'] * mult(k, m)),
            'cells': cells, 'order': opened}


def current_game(db, uid: int):
    return db.execute('SELECT * FROM mines2 WHERE telegram_id=?', (uid,)).fetchone()


def pay(db, uid: int, amount: int, win: bool = False) -> None:
    """Начисляет деньги игроку; win=True увеличивает счётчик побед."""
    db.execute('UPDATE players SET coins=coins+?, games_won=games_won+? WHERE telegram_id=?', (amount, int(win), uid))


@router.get('/api/bh/mines')
def mines_get(user: dict = Depends(current_user)):
    """Текущая (или последняя) игра в мины."""
    with session() as db:
        return {'game': game_view(current_game(db, user['id']))}


class Start(BaseModel):
    bet: int
    mines: int


@router.post('/api/bh/mines/start')
def mines_start(data: Start, user: dict = Depends(current_user)):
    """Начать игру: списывает ставку и случайно расставляет мины."""
    if data.bet not in BETS or not 1 <= data.mines <= 20:
        raise HTTPException(400, 'Неверная ставка или число мин')
    uid = user['id']
    with session(write=True) as db:
        v = view(db, user)
        row = current_game(db, uid)
        if row and row['status'] == 'playing':
            raise HTTPException(409, 'Сначала закончи текущую игру')
        if v['player']['coins'] < data.bet:
            raise HTTPException(402, 'Не хватает долларов для ставки')
        db.execute('UPDATE players SET coins=coins-?, games_played=games_played+1 WHERE telegram_id=?', (data.bet, uid))
        db.execute('''INSERT OR REPLACE INTO mines2 (telegram_id, bet, mines, mines_json, opened_json, status, created_at)
                      VALUES (?,?,?,?,?,?,?)''',
                   (uid, data.bet, data.mines, json.dumps(sorted(rng.sample(range(FIELD), data.mines))),
                    '[]', 'playing', int(time.time())))
        return {**view(db, user), 'game': game_view(current_game(db, uid))}


class Pick(BaseModel):
    cell: int


@router.post('/api/bh/mines/open')
def mines_open(data: Pick, user: dict = Depends(current_user)):
    """Открыть клетку: мина — проигрыш; все безопасные открыты — автоматическая выплата."""
    uid = user['id']
    with session(write=True) as db:
        row = current_game(db, uid)
        if not row or row['status'] != 'playing':
            raise HTTPException(409, 'Начни новую игру')
        opened = json.loads(row['opened_json'])
        if not 0 <= data.cell < FIELD or data.cell in opened:
            raise HTTPException(400, 'Нельзя открыть эту клетку')
        opened.append(data.cell)
        status = 'playing'
        if data.cell in json.loads(row['mines_json']):
            status = 'lost'                                    # ставка сгорает
        elif len(opened) == FIELD - row['mines']:              # открыты все безопасные клетки
            status = 'cashed'
            pay(db, uid, int(row['bet'] * mult(len(opened), row['mines'])), win=True)
        db.execute('UPDATE mines2 SET opened_json=?, status=? WHERE telegram_id=?', (json.dumps(opened), status, uid))
        return {**view(db, user), 'game': game_view(current_game(db, uid))}


@router.post('/api/bh/mines/cash')
def mines_cash(user: dict = Depends(current_user)):
    """Забрать выигрыш. Без открытых клеток — просто возврат ставки."""
    uid = user['id']
    with session(write=True) as db:
        row = current_game(db, uid)
        if not row or row['status'] != 'playing':
            raise HTTPException(409, 'Нет активной игры')
        k = len(json.loads(row['opened_json']))
        amount = row['bet'] if k == 0 else int(row['bet'] * mult(k, row['mines']))
        pay(db, uid, amount, win=amount > row['bet'])
        db.execute("UPDATE mines2 SET status='cashed' WHERE telegram_id=?", (uid,))
        return {**view(db, user), 'game': game_view(current_game(db, uid))}


# =============================================================================== КЕЙСЫ И ГАРАЖ
def car_row(row) -> dict:
    """Машина из гаража (строка таблицы cars) в виде словаря."""
    info = car_info(int(row['car'])) or {'idx': -1, 'name': '???', 'value': 0, 'bonus': 0}
    return {'id': row['id'], **info, 'parked': bool(row['parked'])}


@router.get('/api/bh/garage')
def garage(user: dict = Depends(current_user)):
    """Гараж игрока и описание всех кейсов."""
    with session() as db:
        rows = db.execute('SELECT id, car, parked FROM cars WHERE telegram_id=? LIMIT 300', (user['id'],)).fetchall()
    cars = sorted((car_row(r) for r in rows), key=lambda c: (not c['parked'], -c['value']))  # сначала припаркованная, потом дорогие
    return {'cars': cars, 'cases': CASES_PUBLIC}


class Case(BaseModel):
    case: str


@router.post('/api/bh/case')
def open_case(data: Case, user: dict = Depends(current_user)):
    """Открыть кейс: списывает цену и выдаёт случайную машину по весам."""
    case = CASES.get(data.case)
    if not case:
        raise HTTPException(400, 'Нет такого кейса')
    with session(write=True) as db:
        if view(db, user)['player']['coins'] < case['price']:
            raise HTTPException(402, 'Не хватает долларов')
        idx = rng.choices(list(case['drops']), weights=list(case['drops'].values()))[0]
        db.execute('UPDATE players SET coins=coins-? WHERE telegram_id=?', (case['price'], user['id']))
        cur = db.execute('INSERT INTO cars (telegram_id, car, ts) VALUES (?,?,?)', (user['id'], str(idx), int(time.time())))
        return {**view(db, user), 'car': {'id': cur.lastrowid, **car_info(idx)}}


class CarId(BaseModel):
    id: int


@router.post('/api/bh/sell')
def sell(data: CarId, user: dict = Depends(current_user)):
    """Продать машину по её рыночной цене."""
    with session(write=True) as db:
        row = db.execute('SELECT car, parked FROM cars WHERE id=? AND telegram_id=?', (data.id, user['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Машина не найдена')
        if row['parked']:
            claim_pending(db, user)    # доход до продажи считаем по старой ставке (с бонусом машины)
        db.execute('DELETE FROM cars WHERE id=?', (data.id,))
        value = (car_info(int(row['car'])) or {'value': 0})['value']
        pay(db, user['id'], value)
        return {**view(db, user), 'got': value}


@router.post('/api/bh/park')
def park(data: CarId, user: dict = Depends(current_user)):
    """Припарковать машину (даёт бонус к доходу). id=0 — освободить парковку."""
    with session(write=True) as db:
        if data.id and not db.execute('SELECT 1 FROM cars WHERE id=? AND telegram_id=?', (data.id, user['id'])).fetchone():
            raise HTTPException(404, 'Машина не найдена')
        claim_pending(db, user)        # меняется доход -> сначала забираем накопленное
        db.execute('UPDATE cars SET parked=0 WHERE telegram_id=?', (user['id'],))
        if data.id:
            db.execute('UPDATE cars SET parked=1 WHERE id=? AND telegram_id=?', (data.id, user['id']))
        return view(db, user)


# =============================================================================== МАГАЗИН
@router.post('/api/bh/buylevel')
def buy_level(user: dict = Depends(current_user)):
    """Повысить уровень дома за звёзды."""
    with session(write=True) as db:
        v = view(db, user)
        level = v['house']['level']
        if level >= MAX_LEVEL:
            raise HTTPException(409, 'Максимальный уровень')
        price = star_price(level)
        if v['gems'] < price:
            raise HTTPException(402, f'Не хватает звёзд: нужно {price}')
        claim_pending(db, user)
        db.execute('UPDATE bh SET gems=gems-?, house=house+1 WHERE telegram_id=?', (price, user['id']))
        return view(db, user)


class Convert(BaseModel):
    stars: int


@router.post('/api/bh/convert')
def convert(data: Convert, user: dict = Depends(current_user)):
    """Обмен звёзд на доллары: курс 1⭐ = 500$ × уровень дома."""
    if not 1 <= data.stars <= 100000:
        raise HTTPException(400, 'Неверное количество')
    with session(write=True) as db:
        v = view(db, user)
        if v['gems'] < data.stars:
            raise HTTPException(402, 'Не хватает звёзд')
        got = data.stars * 500 * v['house']['level']
        db.execute('UPDATE bh SET gems=gems-? WHERE telegram_id=?', (data.stars, user['id']))
        pay(db, user['id'], got)
        return {**view(db, user), 'got': got}


# =============================================================================== РЕЙТИНГ
ORDERS = {'house': 'b.house DESC, p.coins DESC, p.telegram_id', 'coins': 'p.coins DESC, p.telegram_id'}


def _ranking_sql(order: str) -> str:
    """Подзапрос: все не заблокированные игроки (кроме админа) с позицией в рейтинге."""
    return f'''SELECT p.telegram_id AS id, COALESCE(p.nickname, p.telegram_name) AS name, p.coins, b.house, b.avatar,
                      ROW_NUMBER() OVER (ORDER BY {order}) AS rank
               FROM players p JOIN bh b ON b.telegram_id = p.telegram_id
               WHERE b.blocked=0 AND p.telegram_id != ?'''


@router.get('/api/bh/top')
def top(by: str = 'house', q: str = '', user: dict = Depends(current_user)):
    """Топ-30 игроков. by=house|coins, q — поиск по нику (место остаётся «настоящим», из общего рейтинга)."""
    sql = _ranking_sql(ORDERS.get(by, ORDERS['house']))
    like = '%' + q.strip().lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    with session() as db:
        rows = db.execute(f"SELECT * FROM ({sql}) WHERE ?='' OR PYLOWER(name) LIKE ? ESCAPE '\\' ORDER BY rank LIMIT 30",
                          (ADMIN_ID, q.strip(), like)).fetchall()
        me = db.execute(f'SELECT rank FROM ({sql}) WHERE id=?', (ADMIN_ID, user['id'])).fetchone()
        total = db.execute(f'SELECT COUNT(*) FROM ({sql})', (ADMIN_ID,)).fetchone()[0]
    return {'top': [dict(r) for r in rows], 'me': me['rank'] if me else None, 'total': total}
