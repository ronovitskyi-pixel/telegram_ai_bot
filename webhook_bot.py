import os
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# 🔑 GET TOKENS FROM RENDER ENV VARIABLES
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 🔒 HARDCODED PASSCODE
PASSCODE = "67stien67"

# 🧠 MODELS
MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

# 🧾 SESSION STORAGE (RAM)
logged_users = set()
user_model = {}

# ------------------ AUTH ------------------

def is_logged(user_id):
    return user_id in logged_users

async def require_login(update: Update):
    await update.message.reply_text("🔒 Enter passcode:")

# ------------------ COMMANDS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Force logout every /start
    if user_id in logged_users:
        logged_users.remove(user_id)

    keyboard = [
        ["/login", "/models"]
    ]

    await update.message.reply_text(
        "🤖 AI Communicator Bot\n\n"
        "🔐 You must login first.\n"
        "Use /login and enter passcode.\n\n"
        "Commands:\n"
        "/login - login\n"
        "/models - choose AI model",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 Send passcode:")

async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_logged(user_id):
        return await require_login(update)

    keyboard = [[m] for m in MODELS]

    await update.message.reply_text(
        "🧠 Choose a model:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ------------------ MESSAGE HANDLER ------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 🔒 LOGIN CHECK EVERY TIME
    if not is_logged(user_id):
        if text == PASSCODE:
            logged_users.add(user_id)
            user_model[user_id] = MODELS[0]
            await update.message.reply_text("✅ Logged in! You can now chat.")
        else:
            await update.message.reply_text("❌ Wrong passcode. Try again.")
        return

    # 🔁 MODEL SWITCH
    if text in MODELS:
        user_model[user_id] = text
        await update.message.reply_text(f"✅ Model switched to:\n{text}")
        return

    # 🤖 CHAT WITH GROQ
    model = user_model.get(user_id, MODELS[0])

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": text}
                ]
            },
            timeout=30
        )

        data = response.json()

        if "choices" not in data:
            await update.message.reply_text(f"⚠️ API error:\n{data}")
            return

        reply = data["choices"][0]["message"]["content"]

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# ------------------ MAIN ------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("models", models))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
