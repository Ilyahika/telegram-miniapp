"""
db.py — работа с SQLite: подключение, схема, миграции.

Главные причины прежних «вечных загрузок» были здесь:
  * каждый запрос заново выполнял CREATE TABLE и писал last_seen -> блокировки базы;
  * журнал был в режиме DELETE: пишущий запрос блокировал всех читающих.
Теперь: схема создаётся ОДИН раз при старте, включён режим WAL (читатели не ждут писателя),
а запись в «был онлайн» делается не чаще раза в 30 секунд.
"""
import logging
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

log = logging.getLogger('miniapp.db')

# --------------------------------------------------------------------------- схема
SCHEMA = '''
CREATE TABLE IF NOT EXISTS players (          -- основной профиль игрока
    telegram_id   INTEGER PRIMARY KEY,
    telegram_name TEXT    NOT NULL,
    nickname      TEXT,
    coins         INTEGER NOT NULL DEFAULT 0, -- доллары
    games_played  INTEGER NOT NULL DEFAULT 0,
    games_won     INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bh (               -- данные «дома»: звёзды, уровень, энергия, блокировка
    telegram_id INTEGER PRIMARY KEY,
    gems        INTEGER NOT NULL DEFAULT 0,   -- звёзды
    house       INTEGER NOT NULL DEFAULT 1,   -- уровень дома
    last_claim  INTEGER NOT NULL DEFAULT 0,   -- когда последний раз забирали доход
    blocked     INTEGER NOT NULL DEFAULT 0,
    reason      TEXT,
    last_seen   INTEGER NOT NULL DEFAULT 0,
    energy      REAL    NOT NULL DEFAULT 50,
    energy_ts   INTEGER NOT NULL DEFAULT 0,
    last_daily  INTEGER NOT NULL DEFAULT 0,
    taps        INTEGER NOT NULL DEFAULT 0,
    earned      INTEGER NOT NULL DEFAULT 0,
    avatar      TEXT    NOT NULL DEFAULT '🏠'
);
CREATE TABLE IF NOT EXISTS cars (             -- гараж
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    car         TEXT    NOT NULL,             -- индекс машины в catalog.CARS
    ts          INTEGER NOT NULL,
    parked      INTEGER NOT NULL DEFAULT 0    -- 1 = машина дает бонус к доходу
);
CREATE TABLE IF NOT EXISTS mines2 (           -- текущая игра «Мины» (одна на игрока)
    telegram_id INTEGER PRIMARY KEY,
    bet         INTEGER,
    mines       INTEGER,
    mines_json  TEXT,
    opened_json TEXT,
    status      TEXT,
    created_at  INTEGER
);
CREATE TABLE IF NOT EXISTS admin_log (        -- журнал действий администратора
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    target   INTEGER,
    action   TEXT NOT NULL,
    value    TEXT
);
CREATE TABLE IF NOT EXISTS db_probe (id TEXT PRIMARY KEY, value TEXT NOT NULL);  -- проверка записи в админке
'''

# Индексы создаются после миграций (в старых базах колонок могло не быть)
INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_bh_seen      ON bh(last_seen);
CREATE INDEX IF NOT EXISTS idx_bh_house     ON bh(house, blocked);
CREATE INDEX IF NOT EXISTS idx_players_made ON players(created_at);
CREATE INDEX IF NOT EXISTS idx_players_coin ON players(coins);
CREATE INDEX IF NOT EXISTS idx_cars_owner   ON cars(telegram_id, parked);
CREATE INDEX IF NOT EXISTS idx_log_ts       ON admin_log(ts);
'''

# Колонки, которые могли отсутствовать в базах старых версий
MIGRATIONS = {
    'bh': {
        'energy': 'REAL NOT NULL DEFAULT 50', 'energy_ts': 'INTEGER NOT NULL DEFAULT 0',
        'last_daily': 'INTEGER NOT NULL DEFAULT 0', 'taps': 'INTEGER NOT NULL DEFAULT 0',
        'earned': 'INTEGER NOT NULL DEFAULT 0', "avatar": "TEXT NOT NULL DEFAULT '🏠'",
        'blocked': 'INTEGER NOT NULL DEFAULT 0', 'reason': 'TEXT', 'last_seen': 'INTEGER NOT NULL DEFAULT 0',
    },
    'cars': {'parked': 'INTEGER NOT NULL DEFAULT 0'},
}


def _lower(value):
    """SQL-функция PYLOWER: регистронезависимый поиск, работает и для кириллицы (встроенный LOWER — только латиница)."""
    return value.lower() if isinstance(value, str) else ''


def _connect() -> sqlite3.Connection:
    """Новое соединение с нужными настройками."""
    # isolation_level=None -> автокоммит: транзакциями управляем сами (BEGIN/COMMIT ниже)
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row                  # доступ к колонкам по имени: row['coins']
    conn.execute('PRAGMA busy_timeout=15000')       # ждать освобождения блокировки до 15 с, а не падать сразу
    conn.execute('PRAGMA synchronous=NORMAL')       # безопасно в режиме WAL и заметно быстрее записи
    conn.create_function('PYLOWER', 1, _lower, deterministic=True)
    return conn


@contextmanager
def session(write: bool = False):
    """
    Соединение с БД на время одного запроса.

    write=False — только чтение (блокировок нет, WAL позволяет читать параллельно с записью).
    write=True  — сразу берём блокировку записи (BEGIN IMMEDIATE): два одновременных клика
                  игрока не смогут «потратить» одни и те же деньги дважды.
    При исключении (в т.ч. HTTPException) транзакция откатывается. Соединение закрывается всегда.
    """
    conn = _connect()
    try:
        if write:
            conn.execute('BEGIN IMMEDIATE')
        yield conn
        if write:
            conn.execute('COMMIT')
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Создаёт таблицы, добавляет недостающие колонки и индексы. Вызывается один раз при старте."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute('PRAGMA journal_mode=WAL')     # режим журнала сохраняется в файле БД навсегда
        conn.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            have = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            for column, ddl in columns.items():
                if column not in have:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
                    log.info('Миграция: %s.%s добавлена', table, column)
        conn.execute("DELETE FROM cars WHERE car NOT GLOB '[0-9]*'")   # мусор от старых версий
        conn.executescript(INDEXES)
    finally:
        conn.close()
    log.info('База готова: %s', DB_PATH)
