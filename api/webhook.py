import os
import asyncio
import random
import re
import time
from http.server import BaseHTTPRequestHandler

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

# ==== НАСТРОЙКИ ====
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CMD_COOLDOWN = 60      # 60 секунд кд на команду /trainsimulatorstavki
USER_COOLDOWN = 3      # 3 секунды кд на попытку угадать для одного юзера
# ===================

dp = Dispatcher()

# Память
active_games = {}       # { chat_id: {'correct': int, 'options': list} }
chat_cooldowns = {}     # { chat_id: timestamp }
user_cooldowns = {}     # { (chat_id, user_id): timestamp }

def get_player_name(message: Message):
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.first_name

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == 'private':
        await message.answer("Я жив! 🟢\nДобавь меня в группу и напиши /trainsimulatorstavki")

@dp.message(Command("trainsimulatorstavki"))
async def cmd_start_bets(message: Message):
    chat_id = message.chat.id
    now = time.time()

    # Проверка кд на команду
    if now < chat_cooldowns.get(chat_id, 0):
        wait = int(chat_cooldowns[chat_id] - now)
        await message.reply(f"⏳ Подождите ещё {wait} сек. перед новыми ставками!")
        return

    # Генерируем 5 случайных годов от 2026 до 5000
    options = random.sample(range(2026, 5001), 5)
    correct_year = random.choice(options)

    # Сохраняем игру
    active_games[chat_id] = {
        'correct': correct_year,
        'options': options
    }

    chat_cooldowns[chat_id] = now + CMD_COOLDOWN

    options_text = ", ".join(str(year) for year in options)
    
    text = (f"Ставки Когда Выйдет Train Simulator!\n"
            f"Ответы (5 Вариантов): {options_text}\n"
            f"Я думаю {correct_year}! А ты?\n"
            f"Один вариант Верный!")

    await message.answer(text)

@dp.message()
async def handle_guesses(message: Message):
    # ЗАЩИТА 1: Игнорируем всё, что не текст (стикеры, фото, видео)
    if not message.text:
        return

    chat_id = message.chat.id
    
    # Если в чате нет активной игры — ничего не делаем
    if chat_id not in active_games:
        return

    # ЗАЩИТА 2: Если в тексте нет цифр вообще, даже не ищем их
    if not any(char.isdigit() for char in message.text):
        return

    user_id = message.from_user.id
    now = time.time()

    # ЗАЩИТА 3: Личный кулдаун для защиты от спама цифрами
    cooldown_key = (chat_id, user_id)
    if now < user_cooldowns.get(cooldown_key, 0):
        return 
    
    # Ищем 4-значные числа
    numbers = re.findall(r'\b\d{4}\b', message.text)
    if not numbers:
        return

    # Ставим кулдаун юзеру на 3 секунды
    user_cooldowns[cooldown_key] = now + USER_COOLDOWN

    correct_year = active_games[chat_id]['correct']
    player_name = get_player_name(message)

    # Проверяем, угадал ли кто-то
    for num_str in numbers:
        if int(num_str) == correct_year:
            await message.reply(f"{player_name} Угадал Когда Выйдет TrainSimulator! Он выйдет {correct_year}!")
            del active_games[chat_id]
            break

# ==== ОБЕРТКА ДЛЯ VERCEL ====
async def _async_process_update(update: Update):
    bot = Bot(token=BOT_TOKEN)
    try:
        await dp.feed_update(bot, update)
    finally:
        await bot.session.close()

def _process_update(update: Update):
    try:
        asyncio.run(_async_process_update(update))
    except Exception as e:
        print("PROCESS ERROR:", repr(e))

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = Update.model_validate_json(body)
            _process_update(update)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            print("HANDLER ERROR:", repr(e))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bets Bot is running")
