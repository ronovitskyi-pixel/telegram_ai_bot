import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 🔑 HARD CODED
TOKEN = "8777189255:AAGgSqTMIgnTqkBPVpY0VShLzMLGAMfJoOk"
GROQ_API_KEY = "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"

PASSCODE = "67stien67"

MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

# ---------------- MEMORY ----------------
logged_users = set()

user_model = {}

# 👇 MEMORY STORAGE
user_memory = {}  # {user_id: [messages]}

MAX_MEMORY = 12  # keep last N messages


def is_logged(user_id):
    return user_id in logged_users


def trim_memory(user_id):
    """Keep memory small so API doesn't explode tokens"""
    if user_id not in user_memory:
        return

    if len(user_memory[user_id]) > MAX_MEMORY:
        user_memory[user_id] = user_memory[user_id][-MAX_MEMORY:]


# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logged_users.discard(user_id)

    await update.message.reply_text(
        "🤖 AI Bot with Memory\n\n"
        "🔐 Use /login and enter passcode.\n"
        "🧠 Bot remembers your chat (session-based)."
    )


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 Send passcode:")


async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_logged(user_id):
        return await update.message.reply_text("🔒 Login first")

    await update.message.reply_text(
        "Choose model:",
        reply_markup=ReplyKeyboardMarkup([[m] for m in MODELS], resize_keyboard=True)
    )


# ---------------- CHAT HANDLER ----------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 🔒 LOGIN
    if not is_logged(user_id):
        if text == PASSCODE:
            logged_users.add(user_id)
            user_model[user_id] = MODELS[0]
            user_memory[user_id] = []  # init memory

            await update.message.reply_text("✅ Logged in + memory enabled")
        else:
            await update.message.reply_text("❌ Wrong passcode")
        return

    # 🔁 MODEL SWITCH
    if text in MODELS:
        user_model[user_id] = text
        await update.message.reply_text(f"🧠 Model set: {text}")
        return

    # 🧠 INIT MEMORY IF NEEDED
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
            await update.message.reply_text(f"⚠️ API error:\n{data}")
            return

        reply = data["choices"][0]["message"]["content"]

        # store bot reply
        user_memory[user_id].append({"role": "assistant", "content": reply})
        trim_memory(user_id)

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")


# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("models", models))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🚀 Bot running with memory...")
    app.run_polling()


if __name__ == "__main__":
    main()
