"""
config.py — настройки приложения.

Все значения берутся из переменных окружения (на Render: Environment).
Этот модуль ничего не импортирует из проекта, поэтому циклических импортов не бывает.
"""
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent   # папка, где лежит проект
STARTED = time.time()                    # момент запуска сервера (для аптайма в админке)
VERSION = 'BuildHouse 4.0'


def _env(name: str, default: str = '') -> str:
    """Читает переменную окружения и убирает пробелы, переносы строк и случайные кавычки."""
    return os.getenv(name, default).strip().strip('"').strip("'").strip()


BOT_TOKEN = _env('BOT_TOKEN')                          # токен бота от @BotFather
_url = _env('WEBAPP_URL').rstrip('/')
WEBAPP_URL = _url + '/' if _url else ''                # адрес Mini App (https://...), всегда со слешем в конце
ADMIN_ID = int(_env('ADMIN_ID', '1181838335') or 0)    # Telegram ID администратора
DB_PATH = Path(_env('DB_PATH') or ROOT / 'database.db')  # путь к SQLite (на Render с диском: /var/data/database.db)

INIT_DATA_MAX_AGE = 24 * 3600   # сколько секунд действует подпись initData от Telegram
LAST_SEEN_EVERY = 30            # как часто (сек) обновлять «был онлайн», чтобы не писать в БД на каждый клик

# CORS нужен только если страница лежит на другом домене (например, GitHub Pages)
_p = urlsplit(WEBAPP_URL)
CORS_ORIGINS = [f'{_p.scheme}://{_p.netloc}'] if WEBAPP_URL else []
