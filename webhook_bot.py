import os
import requests
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG =================
TOKEN = "PASTE_YOUR_TELEGRAM_TOKEN"
GROQ_API_KEY = "PASTE_YOUR_GROQ_KEY"
PASSCODE = "67stien67"

BASE_URL = "https://telegram-ai-bot-3370.onrender.com"

MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

# ================= STATE =================
logged_users = set()
user_model = {}
user_memory = {}

MAX_MEMORY = 12

# ================= APP =================
app_web = Flask(__name__)
tg_app = Application.builder().token(TOKEN).build()


# ================= ROOT =================
@app_web.get("/")
def home():
    return "Bot running", 200


# ================= MENUS =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Login", callback_data="login")],
        [InlineKeyboardButton("🧠 Model", callback_data="models")]
    ])


def model_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(m, callback_data=f"pick:{m}")] for m in MODELS]
    )


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 AI BOT READY\n🔒 Login required",
        reply_markup=main_menu()
    )


# ================= CALLBACK =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data

    if data == "login":
        await q.edit_message_text("🔑 Send passcode:")
        return

    if data == "models":
        await q.edit_message_text("🧠 Choose model:", reply_markup=model_menu())
        return

    if data.startswith("pick:"):
        model = data.split(":")[1]
        user_model[uid] = model
        await q.edit_message_text(f"✅ Model set:\n{model}", reply_markup=main_menu())


# ================= MESSAGE =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # LOGIN CHECK
    if uid not in logged_users:
        if text == PASSCODE:
            logged_users.add(uid)
            user_model[uid] = MODELS[0]
            user_memory[uid] = []
            await update.message.reply_text("✅ Logged in!", reply_markup=main_menu())
        else:
            await update.message.reply_text("🔒 Wrong passcode")
        return

    # MEMORY
    user_memory.setdefault(uid, [])
    user_memory[uid].append({"role": "user", "content": text})
    user_memory[uid] = user_memory[uid][-MAX_MEMORY:]

    model = user_model.get(uid, MODELS[0])

    # GROQ CALL
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": user_memory[uid]
            },
            timeout=30
        )

        reply = r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        reply = f"Error: {e}"

    user_memory[uid].append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)


# ================= WEBHOOK =================
@app_web.post("/webhook")
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, tg_app.bot)

    asyncio.run(tg_app.process_update(update))
    return "ok"


# ================= RUN =================
async def setup_webhook():
    await tg_app.bot.set_webhook(f"{BASE_URL}/webhook")


def main():
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CallbackQueryHandler(callback))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    # FIX: correct async webhook setup
    asyncio.run(setup_webhook())

    print("🚀 Bot running FIXED")

    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
