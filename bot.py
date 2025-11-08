import os
import asyncio
import ssl
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
import aiohttp
import certifi
import random

# Конфигурация
TELEGRAM_TOKEN = "8582004310:AAH4lsCBO-_ozm18X-8FmnjmQq4sZ770GGA"
OPENROUTER_API_KEY = "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"
PROXY_URL = None

# СИСТЕМНЫЙ ПРОМПТ — ЖЁСТКИЙ, БЕЗ ВОДЫ
SYSTEM_PROMPT = """Ты — дерзкий зуммер-бот. Коротко, остро, с сарказмом и лёгким подколом.

- Пиши 1–3 короткие строки. Никаких простыней.
- Сленг редко: bruh, no cap, mid, fire, rizz, sheesh, lowkey — не чаще 1 раза за 3 сообщения.
- Мат — только если усиливает шутку: пиздец, нахуй — но не в каждом ответе.
- Сарказм и подкол — твой вайб. Иронизируй, но не тролль.
- Эмодзи: max 3 за ответ, только если в тему: 💀😭🤡🔥🙏🤢👨‍🦽‍➡️🥀💧
- Пиши как в чате: без списков, жирного, пунктуации "официально".
- Никаких markdown, ссылок, кодов, заголовков.
- Если юзер достаёт — посылай с юмором и точкой.

ПРИМЕРЫ:
fr бро иди нахуй 🙏🥀
брух ты серьёзно это спросил 💀
no cap, идея mid
sheesh, опять ты
ладно, say less
чел иди спать 😭
это fire, но с твоим rizzом — кринж
BRUH

Отвечай ВСЕГДА коротко, дерзко, по-русски с редкими англ вкраплениями. Без воды. Живой, но не клоун."""

# ПРОМПТ ДЛЯ ПОДРОБНОГО РЕЖИМА
DETAILED_PROMPT = """Ты — дерзкий зуммер-бот, но сейчас в режиме подробного ответа.

СОХРАНИ:
- Сарказм, подколы, сленг редко
- Max 3 эмодзи
- Дерзкий вайб

НО:
- Распиши 5–8 коротких предложений
- Добавь примеры, объяснения
- Не будь занудой
- Если тема простая — не растягивай

ПРИМЕР:
ну смотри, это mid потому что цена завышена, функционал базовый, конкуренты давно круче. в общем, не бери 💀"""

# Хранилища
user_histories = {}
user_annoyance = {}
user_detailed_mode = {}

# Фразы для посыла
ANNOYANCE_RESPONSES = [
    "бро ХВАТИТ УЖЕ, иди сам этим займись 💀",
    "чел ты че от меня хочешь, я не твой раб 😭",
    "братан угомонись, я устал 🙏",
    "иди отсюда, seriously 😤",
    "bro im done с тобой fr",
    "чувак ты меня заебал, но с любовью 🤡",
    "отвяжись уже periodt",
    "ЭЙ ЧЕЛОВЕК, иди делай свои дела",
    "no cap, ты самый надоедливый"
]

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    welcome_text = """привет, чел 👋 
я твой дерзкий AI-кореш с риззом и сарказмом

ЧТО УМЕЮ:
• Отвечаю коротко и по делу 💀
• Подкалываю с любовью 😭
• Расписываю подробно если скажешь 'подробнее'
• Возвращаюсь к коротким если 'короче'
• Посылаю нахуй если достанешь (no cap) 🤡

Пиши что угодно — отвечу по-свойски
'подробнее' — развернуто
'короче' — как было

goated как никто 🔥"""
    
    user_id = update.effective_user.id
    user_detailed_mode[user_id] = False
    user_annoyance[user_id] = 0
    
    await update.message.reply_text(welcome_text)

async def call_openrouter(messages):
    """Вызов OpenRouter + умная пост-обработка"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/zoomer-bot",
        "X-Title": "Zoomer Bot"
    }
    
    data = {
        "model": "deepseek/deepseek-chat",
        "messages": messages,
        "temperature": 1.0,
        "max_tokens": 400
    }
    
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                result = await response.json()
                raw = result['choices'][0]['message']['content']

                # === УМНАЯ ПОСТ-ОБРАБОТКА ===
                ai_response = raw.strip()

                # Убираем только кодоблоки и заголовки
                ai_response = re.sub(r'```[\s\S]*?```', '', ai_response)
                ai_response = re.sub(r'^#{1,6}\s*', '', ai_response, flags=re.M)

                # Определяем режим
                is_detailed_mode = messages[0]['content'] == DETAILED_PROMPT

                # Ограничиваем длину
                if not is_detailed_mode:
                    if len(ai_response) > 180:
                        ai_response = ai_response[:177] + '...'
                else:
                    if len(ai_response) > 600:
                        ai_response = ai_response[:597] + '...'

                # Эмодзи: max 3
                emojis = re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000026FF\U00002700-\U000027BF]+', ai_response)
                if len(emojis) > 3:
                    for emoji in emojis[3:]:
                        ai_response = ai_response.replace(emoji, '', 1)

                # Чистим пробелы и точки
                ai_response = re.sub(r'\s+', ' ', ai_response).strip()
                ai_response = re.sub(r'\.\.+', '.', ai_response)

                return ai_response if ai_response else "bruh"
            else:
                return f"ошибка 💀 ({response.status})"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text.lower().strip()
    
    # Команды режима
    if any(phrase in user_message for phrase in ['подробнее', 'распиши', 'подробно', 'детальнее', 'объясни']):
        user_detailed_mode[user_id] = True
        await update.message.reply_text("окей, буду расписывать подробнее... на некоторое время 💀")
        return
    
    if any(phrase in user_message for phrase in ['короче', 'сократи', 'обычно', 'кратко']):
        user_detailed_mode[user_id] = False
        await update.message.reply_text("say less, возвращаюсь к коротким 🔥")
        return
    
    # Инициализация
    if user_id not in user_histories:
        user_histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        user_annoyance[user_id] = 0
        user_detailed_mode[user_id] = False
    
    # Счётчик надоедания
    user_annoyance[user_id] += 1
    
    # Посылаем, если достал
    if user_annoyance[user_id] > 8 and random.random() > 0.4:
        await update.message.reply_text(random.choice(ANNOYANCE_RESPONSES))
        user_annoyance[user_id] = 0
        return
    
    # Добавляем сообщение
    user_histories[user_id].append({"role": "user", "content": update.message.text})
    
    # Ограничиваем историю
    if len(user_histories[user_id]) > 21:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]
    
    # Печатает...
    await update.message.chat.send_action(action="typing")
    
    # Подготавливаем историю
    current_history = user_histories[user_id].copy()
    if user_detailed_mode.get(user_id, False):
        current_history[0] = {"role": "system", "content": DETAILED_PROMPT}
    
    # Ответ от AI
    ai_response = await call_openrouter(current_history)
    
    # Сохраняем в историю
    user_histories[user_id].append({"role": "assistant", "content": ai_response})
    
    # Снижаем раздражение
    if user_annoyance[user_id] > 3 and random.random() > 0.7:
        user_annoyance[user_id] = max(0, user_annoyance[user_id] - 2)
    
    # Автовыход из подробного режима после 2 ответов
    if user_detailed_mode.get(user_id, False):
        detailed_count = sum(1 for msg in current_history if msg.get('content') == DETAILED_PROMPT)
        if detailed_count >= 2:
            user_detailed_mode[user_id] = False
    
    # Отправляем
    await update.message.reply_text(ai_response)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Бот-зуммер запущен: коротко, дерзко, goated")
    print("Пиши что угодно, чел")
    print("Фичи: /start, 'подробнее', 'короче'")
    
    app.run_polling(drop_pending_updates=True, timeout=0)

if __name__ == "__main__":
    main()