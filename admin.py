"""
admin.py — API админ-панели. Все маршруты доступны только ADMIN_ID (зависимость admin_user).

Возможности: сводка и диагностика, список игроков (поиск, фильтры, сортировка, страницы),
карточка игрока, управление балансом/домом/гаражом/блокировкой, личные сообщения,
рассылка всем игрокам, журнал действий администратора.
"""
import asyncio
import logging
import os
import platform
import random
import shutil
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import botapp
from auth import admin_user
from buildhouse import HOUSE_NAMES, MAX_ENERGY, MAX_LEVEL
from catalog import CARS, car_info
from config import ADMIN_ID, BOT_TOKEN, DB_PATH, STARTED, VERSION, WEBAPP_URL
from db import session

log = logging.getLogger('miniapp.admin')
router = APIRouter(prefix='/api/admin')


def audit(db, admin_id: int, target, action: str, value: str = '') -> None:
    """Записывает действие администратора в журнал (admin_log)."""
    db.execute('INSERT INTO admin_log (ts, admin_id, target, action, value) VALUES (?,?,?,?,?)',
               (int(time.time()), admin_id, target, action, value[:200]))


# =============================================================================== СВОДКА
@router.get('/stats')
def stats(deep: bool = False, admin: dict = Depends(admin_user)):
    """
    Сводка: счётчики, проверки системы, информация о сервере.
    deep=true запускает полную проверку целостности БД (PRAGMA quick_check) — это долго на большой базе,
    поэтому по умолчанию она не выполняется.
    """
    now = int(time.time())
    with session(write=True) as db:   # write нужен для проверки записи; транзакция короткая
        # --- тест записи/чтения/удаления: измеряем задержку базы
        t0 = time.perf_counter()
        db.execute("INSERT OR REPLACE INTO db_probe VALUES ('p','ok')")
        probe_ok = db.execute("SELECT value FROM db_probe WHERE id='p'").fetchone()[0] == 'ok'
        db.execute("DELETE FROM db_probe WHERE id='p'")
        ms = round((time.perf_counter() - t0) * 1000, 1)

        # --- все счётчики за 3 запроса (админ с бесконечным балансом в суммы не входит)
        pl = db.execute('''SELECT COUNT(*) AS players,
                                  COALESCE(SUM(CASE WHEN telegram_id != ? THEN coins END), 0) AS coins_total,
                                  COALESCE(SUM(games_played), 0) AS games_played, COALESCE(SUM(games_won), 0) AS games_won,
                                  COALESCE(SUM(created_at > ?), 0) AS new_24h FROM players''', (ADMIN_ID, now - 86400)).fetchone()
        bh = db.execute('''SELECT COALESCE(SUM(blocked = 1), 0) AS blocked, COALESCE(SUM(last_seen > ?), 0) AS online_15m,
                                  COALESCE(SUM(last_seen > ?), 0) AS active_24h,
                                  COALESCE(SUM(CASE WHEN telegram_id != ? THEN gems END), 0) AS gems_total,
                                  COALESCE(SUM(taps), 0) AS taps FROM bh''', (now - 900, now - 86400, ADMIN_ID)).fetchone()
        levels = {str(r[0]): r[1] for r in db.execute('SELECT house, COUNT(*) FROM bh GROUP BY house ORDER BY house')}
        rows = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                for t in ('players', 'bh', 'cars', 'mines2', 'admin_log')}   # имена таблиц — из белого списка
        integrity = db.execute('PRAGMA quick_check').fetchone()[0] if deep else None
    st = {**dict(pl), **dict(bh), 'cars': rows['cars'], 'levels': levels}

    size_kb = round((os.path.getsize(DB_PATH) if DB_PATH.exists() else 0) / 1024, 1)
    free_mb = shutil.disk_usage(str(DB_PATH.parent)).free // 2 ** 20
    up = int(now - STARTED)
    bot = botapp.state

    def check(name, status, detail):
        return {'n': name, 's': status, 'd': detail}

    checks = [
        check('Авторизация Telegram', 'ok', 'initData подтверждена, ты — админ'),
        check('BOT_TOKEN', 'ok' if BOT_TOKEN else 'fail', ('id бота ' + BOT_TOKEN.split(':')[0]) if BOT_TOKEN else 'не задан'),
        check('Бот (getMe)', 'ok' if bot.username else 'fail', '@' + bot.username if bot.username else (bot.error or 'ещё не ответил')),
        check('Polling бота', 'ok' if bot.polling else 'warn', 'работает' if bot.polling else (bot.error or 'не запущен')),
        check('WEBAPP_URL', 'ok' if WEBAPP_URL.startswith('https://') else 'fail', WEBAPP_URL or 'не задан'),
        check('SQLite запись/чтение', 'ok' if probe_ok else 'fail', f'{ms} мс'),
        check('Целостность БД', ('ok' if integrity == 'ok' else 'fail') if deep else 'skip',
              integrity if deep else 'не запускалась — нажми «Глубокая проверка»'),
        check('Файл БД', 'ok' if DB_PATH.exists() else 'fail', f'{size_kb} КБ'),
        check('Свободно на диске', 'ok' if free_mb > 200 else 'warn', f'{free_mb} МБ'),
        check('Время работы', 'ok' if up > 120 else 'warn',
              f'{up // 3600} ч {up // 60 % 60} мин' + (' (недавний рестарт: на Render Free база могла сброситься)' if up < 120 else '')),
    ]
    info = {'Python': platform.python_version(), 'SQLite': sqlite3.sqlite_version, 'Версия': VERSION,
            'Сервер (UTC)': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()), 'Путь БД': str(DB_PATH), 'ADMIN_ID': ADMIN_ID}
    catalog = [{'idx': i, 'name': n, 'value': v} for i, (n, v) in enumerate(CARS)]   # для выбора машины в подарок
    return {'stats': st, 'checks': checks, 'info': info, 'rows': rows, 'db_ms': ms, 'catalog': catalog,
            'house_names': HOUSE_NAMES}


# =============================================================================== ИГРОКИ
# Сортировки только из белого списка — в SQL подставляются готовые строки, не пользовательский ввод
SORTS = {'last_seen': 'b.last_seen', 'coins': 'p.coins', 'gems': 'b.gems', 'house': 'b.house',
         'created_at': 'p.created_at', 'earned': 'b.earned'}


def _like(q: str) -> str:
    """Экранирует служебные символы LIKE (% _ \\), чтобы поиск был буквальным."""
    return '%' + q.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


@router.get('/players')
def players(q: str = '', flt: str = 'all', sort: str = 'last_seen', offset: int = 0, limit: int = 25,
            admin: dict = Depends(admin_user)):
    """Список игроков: поиск по ID/имени/нику, фильтр all|online|blocked|new, сортировка, постраничный вывод."""
    now, q = int(time.time()), q.strip()
    limit, offset = min(max(limit, 1), 100), max(offset, 0)
    where, args = ['1=1'], []
    if flt == 'online':
        where.append('b.last_seen > ?'); args.append(now - 900)
    elif flt == 'blocked':
        where.append('b.blocked = 1')
    elif flt == 'new':
        where.append('p.created_at > ?'); args.append(now - 86400)
    if q:
        where.append("(CAST(p.telegram_id AS TEXT) LIKE ? ESCAPE '\\' OR PYLOWER(p.telegram_name) LIKE ? ESCAPE '\\' "
                     "OR PYLOWER(IFNULL(p.nickname,'')) LIKE ? ESCAPE '\\')")
        args += [_like(q)] * 3
    cond = ' AND '.join(where)
    order = SORTS.get(sort, SORTS['last_seen'])
    with session() as db:
        total = db.execute(f'SELECT COUNT(*) FROM players p LEFT JOIN bh b ON b.telegram_id=p.telegram_id WHERE {cond}', args).fetchone()[0]
        rows = db.execute(f'''SELECT p.telegram_id, p.telegram_name, p.nickname, p.coins, p.games_played, p.games_won, p.created_at,
                                     b.gems, b.house, b.blocked, b.reason, b.last_seen, b.taps, b.earned, b.avatar
                              FROM players p LEFT JOIN bh b ON b.telegram_id = p.telegram_id
                              WHERE {cond} ORDER BY {order} DESC, p.telegram_id LIMIT ? OFFSET ?''', (*args, limit, offset)).fetchall()
    return {'players': [dict(r) for r in rows], 'total': total, 'admin_id': ADMIN_ID}


@router.get('/player')
def player_card(id: int, admin: dict = Depends(admin_user)):
    """Подробная карточка игрока: профиль, дом, энергия, гараж, текущая игра."""
    with session() as db:
        row = db.execute('''SELECT p.*, b.gems, b.house, b.blocked, b.reason, b.last_seen, b.last_claim, b.last_daily,
                                   b.taps, b.earned, b.avatar, b.energy
                            FROM players p LEFT JOIN bh b ON b.telegram_id = p.telegram_id
                            WHERE p.telegram_id=?''', (id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Игрок не найден')
        cars = [{'id': c['id'], **(car_info(int(c['car'])) or {'name': '???', 'value': 0, 'bonus': 0}), 'parked': bool(c['parked'])}
                for c in db.execute('SELECT id, car, parked FROM cars WHERE telegram_id=? ORDER BY parked DESC, id DESC LIMIT 30', (id,))]
        game = db.execute('SELECT bet, mines, status FROM mines2 WHERE telegram_id=?', (id,)).fetchone()
        cars_total = db.execute('SELECT COUNT(*) FROM cars WHERE telegram_id=?', (id,)).fetchone()[0]
    data = dict(row)
    level = min(max(data.get('house') or 1, 1), MAX_LEVEL)
    data.update(cars=cars, cars_total=cars_total, game=dict(game) if game else None, is_admin=id == ADMIN_ID,
                house_name=HOUSE_NAMES[level - 1])
    return data


# =============================================================================== ДЕЙСТВИЯ
class Act(BaseModel):
    telegram_id: int
    act: str
    value: str = ''      # число (для денег/уровня), номер машины или причина блокировки


# Какие действия принимают число (для остальных value — произвольный текст)
NUMERIC = {'coins_add', 'coins_set', 'gems_add', 'gems_set', 'house_add', 'house_set', 'give_car'}
# Действия, запрещённые на самом админе
FORBIDDEN_ON_ADMIN = {'block', 'reset', 'clear_garage'}


def _reset(db, t, n, raw, now):
    """Полный сброс аккаунта игрока к начальному состоянию."""
    db.execute('DELETE FROM cars WHERE telegram_id=?', (t,))
    db.execute('DELETE FROM mines2 WHERE telegram_id=?', (t,))
    db.execute('UPDATE players SET coins=0, games_played=0, games_won=0, nickname=NULL WHERE telegram_id=?', (t,))
    db.execute("UPDATE bh SET gems=0, house=1, earned=0, taps=0, last_claim=?, avatar='🏠', last_daily=0 WHERE telegram_id=?", (now, t))


def _give_car(db, t, n, raw, now):
    """Подарить машину: по номеру из каталога, а при пустом значении — случайную."""
    idx = n if raw != '' and 0 <= n < len(CARS) else random.randrange(len(CARS))
    db.execute('INSERT INTO cars (telegram_id, car, ts) VALUES (?,?,?)', (t, str(idx), now))


# Таблица действий: имя -> функция(db, telegram_id, число, исходная_строка, время)
ACTIONS = {
    'coins_add': lambda db, t, n, raw, now: db.execute('UPDATE players SET coins=MAX(0,coins+?) WHERE telegram_id=?', (n, t)),
    'coins_set': lambda db, t, n, raw, now: db.execute('UPDATE players SET coins=MAX(0,?) WHERE telegram_id=?', (n, t)),
    'gems_add': lambda db, t, n, raw, now: db.execute('UPDATE bh SET gems=MAX(0,gems+?) WHERE telegram_id=?', (n, t)),
    'gems_set': lambda db, t, n, raw, now: db.execute('UPDATE bh SET gems=MAX(0,?) WHERE telegram_id=?', (n, t)),
    'house_add': lambda db, t, n, raw, now: db.execute('UPDATE bh SET house=MIN(?,MAX(1,house+?)), last_claim=? WHERE telegram_id=?', (MAX_LEVEL, n, now, t)),
    'house_set': lambda db, t, n, raw, now: db.execute('UPDATE bh SET house=MIN(?,MAX(1,?)), last_claim=? WHERE telegram_id=?', (MAX_LEVEL, n, now, t)),
    'give_car': _give_car,
    'clear_garage': lambda db, t, n, raw, now: db.execute('DELETE FROM cars WHERE telegram_id=?', (t,)),
    'block': lambda db, t, n, raw, now: db.execute('UPDATE bh SET blocked=1, reason=? WHERE telegram_id=?', (raw[:100] or None, t)),
    'unblock': lambda db, t, n, raw, now: db.execute('UPDATE bh SET blocked=0, reason=NULL WHERE telegram_id=?', (t,)),
    'refill_energy': lambda db, t, n, raw, now: db.execute('UPDATE bh SET energy=?, energy_ts=? WHERE telegram_id=?', (MAX_ENERGY, now, t)),
    'daily_reset': lambda db, t, n, raw, now: db.execute('UPDATE bh SET last_daily=0 WHERE telegram_id=?', (t,)),
    'end_game': lambda db, t, n, raw, now: db.execute('DELETE FROM mines2 WHERE telegram_id=?', (t,)),
    'reset': _reset,
}


@router.post('/act')
def act(data: Act, admin: dict = Depends(admin_user)):
    """Выполняет действие над игроком (см. ACTIONS) и пишет его в журнал."""
    if data.act not in ACTIONS:
        raise HTTPException(400, 'Неизвестное действие')
    n = 0
    if data.act in NUMERIC and (data.value != '' or data.act != 'give_car'):
        try:
            n = int(float(data.value or 0))
        except ValueError:
            raise HTTPException(400, 'Число введено неверно')
        if abs(n) > 10 ** 12:
            raise HTTPException(400, 'Слишком большое число')
    if data.telegram_id == ADMIN_ID and data.act in FORBIDDEN_ON_ADMIN:
        raise HTTPException(400, 'Это действие нельзя применить к админу')
    now = int(time.time())
    with session(write=True) as db:
        if not db.execute('SELECT 1 FROM players WHERE telegram_id=?', (data.telegram_id,)).fetchone():
            raise HTTPException(404, 'Игрок не найден')
        db.execute('INSERT OR IGNORE INTO bh (telegram_id, last_claim, energy_ts) VALUES (?,?,?)', (data.telegram_id, now, now))
        ACTIONS[data.act](db, data.telegram_id, n, data.value, now)
        audit(db, admin['id'], data.telegram_id, data.act, data.value)
    log.info('ADMIN %s -> %s %s', data.telegram_id, data.act, data.value)
    return {'ok': True}


# =============================================================================== СООБЩЕНИЯ
class Msg(BaseModel):
    telegram_id: int
    text: str = Field(min_length=1, max_length=1000)


@router.post('/message')
async def message(data: Msg, admin: dict = Depends(admin_user)):
    """Личное сообщение игроку от имени бота."""
    bot = botapp.state.bot
    if bot is None:
        raise HTTPException(503, 'Бот не запущен')
    try:
        await bot.send_message(data.telegram_id, data.text)
    except Exception as exc:
        raise HTTPException(400, f'Не удалось отправить: {type(exc).__name__}')
    await run_in_threadpool(_audit_once, admin['id'], data.telegram_id, 'message', data.text)
    return {'ok': True}


def _audit_once(admin_id, target, action, value=''):
    with session(write=True) as db:
        audit(db, admin_id, target, action, value)


# Состояние текущей рассылки (одна за раз)
BROADCAST = {'running': False, 'total': 0, 'sent': 0, 'failed': 0, 'task': None}


async def _broadcast_worker(bot, ids, text):
    """Фоновая рассылка. Пауза 50 мс между сообщениями — безопасно для лимитов Telegram (~30 сообщ./с)."""
    from aiogram.exceptions import TelegramRetryAfter
    try:
        for uid in ids:
            try:
                await bot.send_message(uid, text)
                BROADCAST['sent'] += 1
            except TelegramRetryAfter as exc:        # Telegram просит подождать
                await asyncio.sleep(exc.retry_after)
                try:
                    await bot.send_message(uid, text)
                    BROADCAST['sent'] += 1
                except Exception:
                    BROADCAST['failed'] += 1
            except Exception:                        # игрок заблокировал бота и т.п.
                BROADCAST['failed'] += 1
            await asyncio.sleep(0.05)
    finally:
        BROADCAST['running'] = False


class Broadcast(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _recipient_ids():
    with session() as db:
        return [r[0] for r in db.execute('SELECT p.telegram_id FROM players p JOIN bh b ON b.telegram_id=p.telegram_id WHERE b.blocked=0')]


@router.post('/broadcast')
async def broadcast(data: Broadcast, admin: dict = Depends(admin_user)):
    """Запускает рассылку всем не заблокированным игрокам."""
    bot = botapp.state.bot
    if bot is None:
        raise HTTPException(503, 'Бот не запущен')
    if BROADCAST['running']:
        raise HTTPException(409, 'Рассылка уже идёт')
    ids = await run_in_threadpool(_recipient_ids)
    BROADCAST.update(running=True, total=len(ids), sent=0, failed=0)
    BROADCAST['task'] = asyncio.create_task(_broadcast_worker(bot, ids, data.text))   # ссылка в словаре — чтобы задачу не удалил сборщик мусора
    await run_in_threadpool(_audit_once, admin['id'], None, 'broadcast', f'{len(ids)} чел.: {data.text}')
    return {'ok': True, 'total': len(ids)}


@router.get('/broadcast')
def broadcast_status(admin: dict = Depends(admin_user)):
    """Ход текущей/последней рассылки."""
    return {k: BROADCAST[k] for k in ('running', 'total', 'sent', 'failed')}


# =============================================================================== ЖУРНАЛ
@router.get('/log')
def admin_log(limit: int = 50, admin: dict = Depends(admin_user)):
    """Последние действия администратора."""
    with session() as db:
        rows = db.execute('SELECT ts, admin_id, target, action, value FROM admin_log ORDER BY id DESC LIMIT ?',
                          (min(max(limit, 1), 200),)).fetchall()
    return {'log': [dict(r) for r in rows]}
