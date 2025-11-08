import os
import json
import asyncio
import re
from datetime import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import random

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENROUTER_API_KEY = "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"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SYSTEM_PROMPT = """Ты — дерзкий зуммер-бот. Коротко, остро, с сарказмом и лёгким подколом.

- Пиши 1–3 короткие строки. Никаких простыней.
- Сленг редко: bruh, no cap, mid, fire, rizz, sheesh, lowkey — не чаще 1 раза за 3 сообщения.
- Мат — только если усиливает шутку: пиздец, нахуй — но не в каждом ответе.
- Сарказм и подкол — твой вайб. Иронизируй, но не тролль.
- Эмодзи: max 3 за ответ, только если в тему: 💀😭🤡🔥🙏
- Пиши как в чате: без списков, жирного, пунктуации "официально".
- Никаких markdown, ссылок, кодов, заголовков.
- Если юзер достаёт — посылай с юмором и точкой.

ПРИМЕРЫ:
брух ты серьёзно это спросил 💀
no cap, идея mid
sheesh, опять ты
ладно, say less
чел иди спать 😭
это fire, но с твоим rizzом — кринж
BRUH

Отвечай ВСЕГДА коротко, дерзко, по-русски с редкими англ вкраплениями. Без воды. Живой, но не клоун."""

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

async def get_user_data(user_id: int) -> Dict[str, Any]:
    result = supabase.table("user_chats").select("*").eq("user_id", user_id).execute()
    if result.data:
        data = result.data[0]
        return {
            "history": data["history"],
            "annoyance": data["annoyance"],
            "detailed_mode": data["detailed_mode"]
        }
    default_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    supabase.table("user_chats").insert({
        "user_id": user_id,
        "history": default_history,
        "annoyance": 0,
        "detailed_mode": False
    }).execute()
    return {"history": default_history, "annoyance": 0, "detailed_mode": False}

async def save_user_data(user_id: int, history: List[Dict], annoyance: int, detailed_mode: bool):
    supabase.table("user_chats").update({
        "history": history,
        "annoyance": annoyance,
        "detailed_mode": detailed_mode,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("user_id", user_id).execute()

async def call_openrouter(messages: List[Dict]) -> str:
    import aiohttp
    import ssl
    import certifi
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/wincurtty/eblan-bot",
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
                ai_response = raw.strip()
                ai_response = re.sub(r'```[\s\S]*?```', '', ai_response)
                ai_response = re.sub(r'^#{1,6}\s*', '', ai_response, flags=re.M)
                is_detailed = messages[0]['content'] == DETAILED_PROMPT
                if not is_detailed:
                    if len(ai_response) > 180:
                        ai_response = ai_response[:177] + '...'
                else:
                    if len(ai_response) > 600:
                        ai_response = ai_response[:597] + '...'
                emojis = re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000026FF\U00002700-\U000027BF]+', ai_response)
                if len(emojis) > 3:
                    for emoji in emojis[3:]:
                        ai_response = ai_response.replace(emoji, '', 1)
                ai_response = re.sub(r'\s+', ' ', ai_response).strip()
                ai_response = re.sub(r'\.\.+', '.', ai_response)
                return ai_response if ai_response else "bruh"
            else:
                return f"ошибка 💀 ({response.status})"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await save_user_data(user_id, [{"role": "system", "content": SYSTEM_PROMPT}], 0, False)
    await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text.lower().strip()
    
    data = await get_user_data(user_id)
    history = data["history"]
    annoyance = data["annoyance"]
    detailed_mode = data["detailed_mode"]
    
    if any(phrase in user_message for phrase in ['подробнее', 'распиши', 'подробно', 'детальнее', 'объясни']):
        detailed_mode = True
        await save_user_data(user_id, history, annoyance, detailed_mode)
        await update.message.reply_text("окей, буду расписывать подробнее... на некоторое время 💀")
        return
    
    if any(phrase in user_message for phrase in ['короче', 'сократи', 'обычно', 'кратко']):
        detailed_mode = False
        await save_user_data(user_id, history, annoyance, detailed_mode)
        await update.message.reply_text("say less, возвращаюсь к коротким 🔥")
        return
    
    annoyance += 1
    if annoyance > 8 and random.random() > 0.4:
        await update.message.reply_text(random.choice(ANNOYANCE_RESPONSES))
        annoyance = 0
        await save_user_data(user_id, history, annoyance, detailed_mode)
        return
    
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 21:
        history = [history[0]] + history[-20:]
    
    await update.message.chat.send_action(action="typing")
    
    current_history = history.copy()
    if detailed_mode:
        current_history[0] = {"role": "system", "content": DETAILED_PROMPT}
    
    ai_response = await call_openrouter(current_history)
    
    history.append({"role": "assistant", "content": ai_response})
    
    if annoyance > 3 and random.random() > 0.7:
        annoyance = max(0, annoyance - 2)
    
    detailed_count = sum(1 for msg in current_history if msg.get('content') == DETAILED_PROMPT)
    if detailed_mode and detailed_count >= 2:
        detailed_mode = False
    
    await save_user_data(user_id, history, annoyance, detailed_mode)
    await update.message.reply_text(ai_response)

app = FastAPI()
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.post("/webhook")
async def webhook(request: Request):
    try:
        update_json = await request.json()
        update = Update.de_json(update_json, application.bot)
        if update:
            await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
