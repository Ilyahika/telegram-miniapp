"""
buildhouse.py — экономика «дома»: доход, прокачка, тапы, ежедневный бонус, аватар, ник.

Здесь же общая функция view(): единый «снимок» состояния игрока, который получает клиент.
"""
import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from catalog import car_info
from config import ADMIN_ID
from auth import current_user
from db import session

router = APIRouter()

# ----------------------------------------------------------------------- константы баланса
HOUSE_NAMES = ['Палатка', 'Хижина', 'Домик', 'Коттедж', 'Таунхаус', 'Вилла', 'Особняк', 'Поместье', 'Замок', 'Небоскрёб',
               'Резиденция', 'Дворец', 'Крепость', 'Башня', 'Комплекс', 'Отель', 'Курорт', 'Остров', 'Квартал', 'Город-сад',
               'Мегаполис', 'Технопарк', 'Космопорт', 'Орбитальная станция', 'Лунная база', 'Марс-колония', 'Звёздный город',
               'Галактический хаб', 'Вселенский дворец', 'Обитель богов']
MAX_LEVEL = len(HOUSE_NAMES)
CAP_HOURS = 8              # доход копится максимум 8 часов, потом нужно забрать
MAX_ENERGY = 50            # максимум энергии для кликера «Стройка»
ENERGY_REGEN_SEC = 2       # 1 единица энергии восстанавливается за 2 секунды
DAILY_COOLDOWN = 86400     # ежедневный бонус раз в сутки
AVATARS = ['🏠', '🔨', '👷', '🏗️', '🦾', '👑', '🐱', '🚀']
INF = 10 ** 15             # «бесконечный» баланс администратора


def upgrade_cost(level: int) -> int:
    """Цена перехода с уровня level на level+1 в долларах."""
    return int(500 * 1.55 ** (level - 1) // 10 * 10)


def house_income(level: int) -> int:
    """Базовый доход дома, $ в час."""
    return int(20 * 1.42 ** (level - 1))


def star_price(level: int) -> int:
    """Цена повышения уровня за звёзды."""
    return 10 + 5 * level


def player_json(row, coins=None) -> dict:
    """Профиль игрока в виде словаря для клиента."""
    return {'telegram_id': row['telegram_id'], 'telegram_name': row['telegram_name'],
            'nickname': row['nickname'] or row['telegram_name'], 'custom_nickname': row['nickname'],
            'coins': row['coins'] if coins is None else coins,
            'games_played': row['games_played'], 'games_won': row['games_won']}


# ----------------------------------------------------------------------- снимок состояния
def view(db, user: dict) -> dict:
    """Полное состояние игрока: баланс, дом, энергия, машина, доступность бонуса."""
    uid, now = user['id'], int(time.time())
    p = db.execute('SELECT * FROM players WHERE telegram_id=?', (uid,)).fetchone()
    b = db.execute('SELECT * FROM bh WHERE telegram_id=?', (uid,)).fetchone()
    if p is None or b is None:
        raise HTTPException(404, 'Профиль не найден — перезапусти приложение')

    coins, gems = p['coins'], b['gems']
    if uid == ADMIN_ID and (coins < INF // 2 or gems < INF // 2):
        # у администратора бесконечные ресурсы: пополняем, только когда запас упал вдвое
        db.execute('UPDATE players SET coins=MAX(coins,?) WHERE telegram_id=?', (INF, uid))
        db.execute('UPDATE bh SET gems=MAX(gems,?) WHERE telegram_id=?', (INF, uid))
        coins, gems = max(coins, INF), max(gems, INF)

    parked = db.execute('SELECT car FROM cars WHERE telegram_id=? AND parked=1 LIMIT 1', (uid,)).fetchone()
    car = car_info(int(parked['car'])) if parked else None
    car_bonus = car['bonus'] if car else 0

    level = min(max(b['house'], 1), MAX_LEVEL)
    income = house_income(level) + car_bonus                       # доход с учётом машины
    energy = min(MAX_ENERGY, b['energy'] + (now - b['energy_ts']) / ENERGY_REGEN_SEC)
    pending = int(min(now - b['last_claim'], CAP_HOURS * 3600) * income / 3600)  # накопленный, но не забранный доход
    can_up = level < MAX_LEVEL
    return {
        'player': player_json(p, coins), 'gems': gems, 'avatar': b['avatar'],
        'energy': int(energy), 'max_energy': MAX_ENERGY,
        'daily_ready': now - b['last_daily'] >= DAILY_COOLDOWN,
        'is_admin': uid == ADMIN_ID, 'car': car,
        'house': {'level': level, 'name': HOUSE_NAMES[level - 1], 'income': income, 'base_income': house_income(level),
                  'cap_hours': CAP_HOURS, 'pending': pending, 'max': MAX_LEVEL,
                  'next_cost': upgrade_cost(level) if can_up else None,
                  'next_income': house_income(level + 1) + car_bonus if can_up else None,
                  'next_stars': star_price(level) if can_up else None}}


def claim_pending(db, user: dict) -> int:
    """Переводит накопленный доход на баланс. Возвращает сумму. Вызывать внутри write-сессии."""
    amount = view(db, user)['house']['pending']
    if amount < 1:
        return 0
    db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (amount, user['id']))
    db.execute('UPDATE bh SET last_claim=?, earned=earned+? WHERE telegram_id=?', (int(time.time()), amount, user['id']))
    return amount


# ----------------------------------------------------------------------- маршруты
@router.get('/api/bh/state')
def state(user: dict = Depends(current_user)):
    """Текущее состояние игрока (первый запрос при открытии приложения)."""
    with session() as db:
        return view(db, user)


@router.post('/api/bh/claim')
def claim(user: dict = Depends(current_user)):
    """Забрать накопленный доход дома."""
    with session(write=True) as db:
        got = claim_pending(db, user)
        return {**view(db, user), 'got': got}


@router.post('/api/bh/upgrade')
def upgrade(user: dict = Depends(current_user)):
    """Улучшить дом за доллары."""
    with session(write=True) as db:
        v = view(db, user)
        level = v['house']['level']
        if level >= MAX_LEVEL:
            raise HTTPException(409, 'Максимальный уровень дома')
        price = upgrade_cost(level)
        if v['player']['coins'] < price:
            raise HTTPException(402, f'Не хватает монет: нужно {price}')
        claim_pending(db, user)   # сначала забираем доход по СТАРОЙ ставке, потом повышаем уровень
        db.execute('UPDATE players SET coins=coins-? WHERE telegram_id=?', (price, user['id']))
        db.execute('UPDATE bh SET house=house+1 WHERE telegram_id=?', (user['id'],))
        return view(db, user)


class Tap(BaseModel):
    n: int = 1   # сколько тапов накопил клиент (отправляются пачкой)


@router.post('/api/bh/tap')
def tap(data: Tap, user: dict = Depends(current_user)):
    """Кликер «Стройка»: каждый тап тратит 1 энергию и даёт (1 + уровень дома) долларов."""
    with session(write=True) as db:
        v = view(db, user)
        n = min(max(data.n, 1), 10, v['energy'])      # не больше 10 тапов за раз и не больше энергии
        if n < 1:
            raise HTTPException(429, 'Нет энергии — подожди, она восстанавливается')
        gain = n * (1 + v['house']['level'])
        db.execute('UPDATE bh SET energy=?, energy_ts=?, taps=taps+?, earned=earned+? WHERE telegram_id=?',
                   (v['energy'] - n, int(time.time()), n, gain, user['id']))
        db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (gain, user['id']))
        return {**view(db, user), 'got': gain}


@router.post('/api/bh/daily')
def daily(user: dict = Depends(current_user)):
    """Ежедневный бонус: 100$ × уровень дома и 1 звезда."""
    with session(write=True) as db:
        v = view(db, user)
        if not v['daily_ready']:
            raise HTTPException(409, 'Бонус уже получен, приходи завтра')
        reward = 100 * v['house']['level']
        db.execute('UPDATE players SET coins=coins+? WHERE telegram_id=?', (reward, user['id']))
        db.execute('UPDATE bh SET gems=gems+1, last_daily=?, earned=earned+? WHERE telegram_id=?',
                   (int(time.time()), reward, user['id']))
        return {**view(db, user), 'got': reward}


class Avatar(BaseModel):
    avatar: str


@router.post('/api/bh/avatar')
def set_avatar(data: Avatar, user: dict = Depends(current_user)):
    """Сменить аватар (только из списка AVATARS)."""
    if data.avatar not in AVATARS:
        raise HTTPException(400, 'Неверный аватар')
    with session(write=True) as db:
        db.execute('UPDATE bh SET avatar=? WHERE telegram_id=?', (data.avatar, user['id']))
        return view(db, user)


class Nickname(BaseModel):
    nickname: str


@router.post('/api/nickname')
def set_nickname(data: Nickname, user: dict = Depends(current_user)):
    """Сменить ник. Пустая строка — сброс на имя из Telegram."""
    name = data.nickname.strip()
    if len(name) > 24 or (name and (len(name) < 2 or not re.fullmatch(r'[\w -]+', name, re.UNICODE))):
        raise HTTPException(400, 'Ник: 2–24 символа, буквы, цифры, пробел, _ или -. Пустое поле — сброс.')
    with session(write=True) as db:
        db.execute('UPDATE players SET nickname=? WHERE telegram_id=?', (name or None, user['id']))
        return view(db, user)
