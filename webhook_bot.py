import asyncio
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# 🔑 HARD CODED CONFIG
TOKEN = "8777189255:AAGgSqTMIgnTqkBPVpY0VShLzMLGAMfJoOk"
GROQ_API_KEY = "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"
PASSCODE = "67stien67"

# 🧠 MODELS
MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

# ---------------- STATE ----------------
logged_users = set()
user_model = {}
user_memory = {}

MAX_MEMORY = 12


def is_logged(user_id):
    return user_id in logged_users


def trim_memory(user_id):
    if user_id in user_memory and len(user_memory[user_id]) > MAX_MEMORY:
        user_memory[user_id] = user_memory[user_id][-MAX_MEMORY:]


# ---------------- START MENU ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logged_users.discard(user_id)

    keyboard = [
        ["/login"],
        ["/model"],
        ["/help"]
    ]

    await update.message.reply_text(
        "🤖 AI BOT MENU\n\n"
        "1️⃣ /login - enter passcode\n"
        "2️⃣ /model - choose AI model\n"
        "3️⃣ chat normally after login\n\n"
        "👇 Use buttons below:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


# ---------------- LOGIN ----------------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 Send passcode:")


# ---------------- MODEL MENU ----------------
async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_logged(user_id):
        return await update.message.reply_text("🔒 Login first using /login")

    await update.message.reply_text(
        "🧠 Choose model:",
        reply_markup=ReplyKeyboardMarkup([[m] for m in MODELS], resize_keyboard=True)
    )


# ---------------- HELP ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Commands:\n\n"
        "/start - menu\n"
        "/login - authenticate\n"
        "/model - select AI model\n\n"
        "After login, just chat normally."
    )


# ---------------- MESSAGE HANDLER ----------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 🔒 LOGIN CHECK
    if not is_logged(user_id):
        if text == PASSCODE:
            logged_users.add(user_id)
            user_model[user_id] = MODELS[0]
            user_memory[user_id] = []

            await update.message.reply_text("✅ Logged in successfully!")
        else:
            await update.message.reply_text("❌ Wrong passcode")
        return

    # 🧠 MODEL SWITCH
    if text in MODELS:
        user_model[user_id] = text
        await update.message.reply_text(f"🧠 Model set to:\n{text}")
        return

    # 🧠 INIT MEMORY
    if user_id not in user_memory:
        user_memory[user_id] = []

    # store user message
    user_memory[user_id].append({"role": "user", "content": text})
    trim_memory(user_id)

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
                "messages": user_memory[user_id]
            },
            timeout=30
        )

        data = response.json()

        if "choices" not in data:
            await update.message.reply_text(f"⚠️ API Error:\n{data}")
            return

        reply = data["choices"][0]["message"]["content"]

        user_memory[user_id].append({"role": "assistant", "content": reply})
        trim_memory(user_id)

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error:\n{e}")


# ---------------- MAIN (RENDER SAFE) ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("model", model))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🚀 Bot running...")

    async def run():
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

    asyncio.run(run())


if __name__ == "__main__":
    main()
