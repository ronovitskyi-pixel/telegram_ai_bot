import os
import requests
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

# ================= STATE =================
logged_users = set()
user_model = {}
user_memory = {}

# ================= APP =================
app = Flask(__name__)
tg_app = Application.builder().token(TOKEN).build()

# ================= ROUTES =================
@app.get("/")
def home():
    return "Bot is running", 200

@app.post("/webhook")
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, tg_app.bot)
    tg_app.create_task(tg_app.process_update(update))
    return "ok"

# ================= UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Login", callback_data="login")],
        [InlineKeyboardButton("🧠 Model", callback_data="models")]
    ])

def model_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(m, callback_data=f"model:{m}")] for m in MODELS]
    )

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot ready\n🔒 Please login",
        reply_markup=main_menu()
    )

# ================= CALLBACK =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "login":
        await q.edit_message_text("🔑 Send passcode:")
        return

    if q.data == "models":
        if uid not in logged_users:
            await q.edit_message_text("🔒 Login first")
            return

        await q.edit_message_text("🧠 Choose model:", reply_markup=model_menu())
        return

    if q.data.startswith("model:"):
        model = q.data.split(":", 1)[1]
        user_model[uid] = model
        await q.edit_message_text(f"✅ Model set:\n{model}")
        return

# ================= CHAT =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # LOGIN
    if uid not in logged_users:
        if text == PASSCODE:
            logged_users.add(uid)
            user_model[uid] = MODELS[0]
            user_memory[uid] = []
            await update.message.reply_text("✅ Logged in!", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Wrong passcode")
        return

    # MEMORY
    user_memory.setdefault(uid, [])
    user_memory[uid].append({"role": "user", "content": text})
    user_memory[uid] = user_memory[uid][-10:]

    model = user_model.get(uid, MODELS[0])

    # GROQ API
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
        reply = f"⚠️ Error: {e}"

    user_memory[uid].append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)

# ================= REGISTER =================
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CallbackQueryHandler(callback))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("🚀 Bot running (FINAL WORKING)")
    app.run(host="0.0.0.0", port=port)
