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

# Список месяцев для красивого вывода
MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", 
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]
# ===================

dp = Dispatcher()

# Память
active_games = {}       # { chat_id: {'correct': (day, month, year), 'options': list} }
chat_cooldowns = {}     # { chat_id: timestamp }
user_cooldowns = {}     # { (chat_id, user_id): timestamp }

def get_player_name(message: Message):
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.first_name

def generate_random_date():
    """Генерирует случайную дату: день (1-28), месяц (1-12), год (2026-5000)."""
    day = random.randint(1, 28) # Берем до 28, чтобы не было проблем с 30/31 февраля
    month = random.randint(1, 12)
    year = random.randint(2026, 5000)
    return (day, month, year)

def format_date(date_tuple):
    """Превращает (15, 5, 2026) в красивую строку '15 Май 2026'."""
    day, month, year = date_tuple
    return f"{day} {MONTHS[month-1]} {year}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == 'private':
        await message.answer("Я жив! 🟢\nДобавь меня в группу и напиши /trainsimulatorstavki")

@dp.message(Command("trainsimulatorstavki"))
async def cmd_start_bets(message: Message):
    chat_id = message.chat.id
    now = time.time()

    if now < chat_cooldowns.get(chat_id, 0):
        wait = int(chat_cooldowns[chat_id] - now)
        await message.reply(f"⏳ Подождите ещё {wait} сек. перед новыми ставками!")
        return

    # Генерируем 5 случайных дат
    options = [generate_random_date() for _ in range(5)]
    correct_date = random.choice(options)

    # Сохраняем игру
    active_games[chat_id] = {
        'correct': correct_date,
        'options': options
    }

    chat_cooldowns[chat_id] = now + CMD_COOLDOWN

    # Красиво форматируем список вариантов
    options_text = "\n".join([f"• {format_date(opt)}" for opt in options])
    correct_text = format_date(correct_date)
    
    text = (f"Ставки Когда Выйдет Train Simulator!\n"
            f"Ответы (5 Вариантов):\n{options_text}\n\n"
            f"Я думаю {correct_text}! А ты?\n"
            f"Один вариант Верный!\n"
            f"(Угадайте день, месяц или год)")

    await message.answer(text)


@dp.message()
async def handle_guesses(message: Message):
    # ЗАЩИТА 1: Игнорируем всё, что не текст
    if not message.text:
        return

    chat_id = message.chat.id
    
    # Если игры нет — выходим
    if chat_id not in active_games:
        return

    text_lower = message.text.lower()
    
    # ЗАЩИТА 2: Игнорируем, если нет ни цифр, ни букв
    if not any(char.isdigit() for char in text_lower) and not any(char.isalpha() for char in text_lower):
        return

    user_id = message.from_user.id
    now = time.time()

    # ЗАЩИТА 3: Личный кулдаун от спама
    cooldown_key = (chat_id, user_id)
    if now < user_cooldowns.get(cooldown_key, 0):
        return 
    
    user_cooldowns[cooldown_key] = now + USER_COOLDOWN

    correct_day, correct_month, correct_year = active_games[chat_id]['correct']
    player_name = get_player_name(message)

    # Вытаскиваем все числа из сообщения
    numbers = re.findall(r'\b\d+\b', text_lower)
    
    guessed_part = None

    # ПРОВЕРКА: Угадал ли год, месяц (цифрой) или день (цифрой)
    if str(correct_year) in numbers:
        guessed_part = "год"
    elif str(correct_month) in numbers:
        guessed_part = "месяц"
    elif str(correct_day) in numbers:
        guessed_part = "день"
    # ПРОВЕРКА: Угадал ли месяц словом (например, написал "май")
    elif MONTHS[correct_month-1].lower() in text_lower:
        guessed_part = "месяц"

    if guessed_part:
        full_date = format_date(active_games[chat_id]['correct'])
        
        await message.reply(
            f"🎉 {player_name} Угадал {guessed_part} Когда Выйдет TrainSimulator!\n"
            f"Он выйдет {full_date}!"
        )
        # Удаляем игру, так как победитель найден
        del active_games[chat_id]


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
