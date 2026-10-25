"""
botapp.py — Telegram-бот (aiogram).

Бот работает в фоне и НЕ блокирует запуск сайта. Раньше сервер ждал ответа Telegram (getMe,
deleteWebhook — до 60 секунд каждый) ещё до того, как начинал принимать запросы: отсюда
долгая загрузка Mini App после «засыпания» Render.
"""
import asyncio
import logging
from types import SimpleNamespace
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from config import BOT_TOKEN, WEBAPP_URL

log = logging.getLogger('miniapp.bot')
dp = Dispatcher()  # диспетчер: раздаёт входящие сообщения обработчикам ниже

# Общее состояние бота (читает /health и админ-панель)
state = SimpleNamespace(bot=None, username='', polling=False, error='')


def create_bot() -> Optional[Bot]:
    """Создаёт объект бота. Возвращает None, если токен не задан или имеет неверный формат."""
    if not BOT_TOKEN:
        state.error = 'BOT_TOKEN не задан'
        return None
    try:
        return Bot(token=BOT_TOKEN)
    except Exception as exc:  # aiogram проверяет формат токена при создании
        state.error = f'BOT_TOKEN имеет неверный формат ({type(exc).__name__})'
        return None


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start — отправляет кнопку, открывающую Mini App."""
    if not WEBAPP_URL.startswith('https://'):
        await message.answer('⚠️ Администратор ещё не указал WEBAPP_URL.')
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🚀 Открыть', web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer('🏠 BuildHouse: строй дом, играй в «Мины», открывай кейсы!', reply_markup=keyboard)


async def run_bot(bot: Bot) -> None:
    """Фоновая задача: проверяет токен, сбрасывает вебхук и запускает long polling."""
    attempt = 0
    while True:
        try:
            me = await bot.get_me()                 # узнаём @username бота (нужен для подсказок об ошибках)
            state.username, state.error = me.username or str(me.id), ''
            log.info('Бот авторизован: @%s', state.username)
            break
        except TelegramUnauthorizedError:           # токен неверный — повторять бессмысленно
            state.error = 'BOT_TOKEN неверный или отозван: возьми новый в @BotFather'
            log.error(state.error)
            return
        except Exception:                           # сеть/таймаут — пробуем снова с растущей паузой
            attempt += 1
            delay = min(60, 2 ** attempt)
            log.warning('getMe не удался (попытка %d), повтор через %d с', attempt, delay)
            await asyncio.sleep(delay)

    try:
        await bot.delete_webhook(drop_pending_updates=True)  # polling и webhook одновременно не работают
    except Exception:
        log.exception('delete_webhook не удался')

    state.polling = True
    try:
        await dp.start_polling(bot, handle_signals=False)    # handle_signals=False: сигналы обрабатывает uvicorn
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        state.error = f'Polling остановился: {type(exc).__name__}'
        log.exception('Polling упал')
    finally:
        state.polling = False
