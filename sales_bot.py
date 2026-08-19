# -*- coding: utf-8 -*-
"""Бот активации ключей доступа к сессиям.

Пользователь присылает ключ вида ED-XXXX-XXXX-XXXX, бот запрашивает
webapp (Railway) POST /api/activate-key и возвращает ссылку на сессию.

Запуск:  python sales_bot.py
Переменные окружения:
  BOT_TOKEN              — токен бота
  PUBLIC_BASE_URL        — https://<railway>.up.railway.app
  ACTIVATE_API_URL       — полный URL эндпоинта (по умолчанию PUBLIC_BASE_URL + /api/activate-key)
"""

import os
import re
import asyncio
import logging

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('sales_bot')

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8894108730:AAG7acDemtNiicE_oHp1WqEm04Vj5lpneQc')
BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'https://qwsavdbsvs-production.up.railway.app').rstrip('/')
ACTIVATE_URL = os.environ.get('ACTIVATE_API_URL', f'{BASE_URL}/api/activate-key')
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip().isdigit()]

KEY_RE = re.compile(r'^[A-Za-z0-9]{4,64}$')

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

WELCOME = (
    '🛵 <b>Добро пожаловать!</b>\n\n'
    'Это бот активации доступа к сессиям.\n\n'
    '🔑 Введите ваш <b>ключ активации</b> — и получите '
    'ссылку на свою сессию.\n\n'
    'Пример ключа: <code>ED-XXXX-XXXX-XXXX</code>'
)

KEY_TIPS = (
    '🔑 Пришлите ваш ключ активации одним сообщением.\n'
    'Формат: <code>ED-XXXX-XXXX-XXXX</code>'
)

HELP_TEXT = (
    'ℹ️ <b>Как это работает</b>\n\n'
    '1. Вы приобретаете ключ у продавца.\n'
    '2. Присылаете его боту одним сообщением.\n'
    '3. Получаете ссылку на свою сессию и открываете её '
    'прямо в Telegram.\n\n'
    'Ключ можно использовать несколько раз.\n'
    'Остались вопросы — напишите @<b>support</b>'
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='❓ Как это работает', callback_data='help'),
            InlineKeyboardButton(text='🔄 Проверить ключ', callback_data='check'),
        ],
    ])


def success_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🚀 Открыть сессию', url=url)],
        [
            InlineKeyboardButton(text='❓ Помощь', callback_data='help'),
            InlineKeyboardButton(text='🔄 Другой ключ', callback_data='check'),
        ],
    ])


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(WELCOME, reply_markup=main_menu())


@dp.message(Command('help'))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@dp.callback_query(F.data == 'help')
async def cb_help(cb: CallbackQuery):
    await cb.message.edit_text(HELP_TEXT, reply_markup=main_menu())
    await cb.answer()


@dp.callback_query(F.data == 'check')
async def cb_check(cb: CallbackQuery):
    await cb.message.edit_text(KEY_TIPS)
    await cb.answer()


def _normalize(key: str) -> str:
    return re.sub(r'[\s\-]', '', key.strip()).upper()


def _activate(key: str, user_id: str):
    """Синхронный запрос к webapp. Возвращает dict или бросает ошибку."""
    r = requests.post(ACTIVATE_URL,
                      json={'key': key, 'user_id': user_id,
                            'base_url': BASE_URL}, timeout=20)
    try:
        data = r.json()
    except Exception:
        data = {}
    if not r.ok or not data.get('ok'):
        raise RuntimeError(data.get('error') or f'Ошибка сервера ({r.status_code})')
    return data


@dp.message(F.text)
async def on_key(message: Message):
    text = (message.text or '').strip()
    if text.lower() in ('/start', '/help'):
        return
    norm = _normalize(text)
    if not KEY_RE.match(norm):
        await message.answer(
            '⚠️ <b>Похоже, это не ключ.</b>\n\n'
            'Ключ выглядит так: <code>ED-XXXX-XXXX-XXXX</code>\n\n'
            'Пришлите ключ одним сообщением — без лишних слов.',
            reply_markup=main_menu(),
        )
        return

    sent = await message.answer('⏳ Проверяю ключ…')
    try:
        user_id = str(message.from_user.id) if message.from_user else ''
        data = await asyncio.to_thread(_activate, norm, user_id)
    except RuntimeError as e:
        await sent.edit_text(
            f'⚠️ <b>Не удалось активировать ключ.</b>\n\n{esc(str(e))}\n\n'
            'Проверьте ключ и попробуйте ещё раз.',
            reply_markup=main_menu(),
        )
        return
    except Exception as e:
        log.exception('activate error')
        await sent.edit_text(
            '⚠️ <b>Сервис временно недоступен.</b>\n\n'
            'Попробуйте ещё раз чуть позже.',
            reply_markup=main_menu(),
        )
        return

    sess = data.get('session', {})
    url = sess.get('url') or ''
    name = sess.get('name') or ''
    expires = sess.get('expires_at') or '—'
    first = sess.get('first')
    head = (f'✅ <b>Ключ активирован!</b>\n\n'
            f'🔑 Ваша сессия <b>{esc(name)}</b> готова.\n'
            f'⏳ Действует до: <b>{esc(expires)}</b>\n\n'
            f'Нажмите кнопку ниже, чтобы открыть сессию прямо в Telegram:')
    if first is False:
        head = (f'✅ <b>Это ваш ключ — доступ подтверждён.</b>\n\n'
                f'🔑 Сессия <b>{esc(name)}</b>.\n'
                f'⏳ Действует до: <b>{esc(expires)}</b>\n\n'
                f'Нажмите кнопку ниже, чтобы открыть её:')
    if url:
        await sent.edit_text(head, reply_markup=success_kb(url))
    else:
        await sent.edit_text(head + '\n\n(ссылка не получена)', reply_markup=main_menu())


def esc(s):
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


async def main():
    log.info('Бот запущен. BASE_URL=%s', BASE_URL)
    await dp.start_polling(bot)


def run_in_background():
    """Запуск бота как отдельного процесса (спавнится webapp при старте).

    aiogram не может работать в фоновом потоке внутри gunicorn
    (set_wakeup_fd only works in main thread), поэтому запускаем
    отдельный дочерний процесс python sales_bot.py.
    """
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop('SALES_BOT_ENABLED', None)
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__)],
        env=env,
    )
    return proc


if __name__ == '__main__':
    asyncio.run(main())