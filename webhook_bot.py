import os
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = "8777189255:AAGgSqTMIgnTqkBPVpY0VShLzMLGAMfJoOk"
GROQ_API_KEY = "gsk_NhxYXTpFTv1gPxXixkNPWGdyb3FYUQLOFHQBTmvyK7TrVjqLcyO"
PASSCODE = "67stien67"

MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

logged_users = set()
user_model = {}
user_memory = {}

MAX_MEMORY = 12

# ================= FLASK APP =================
app_web = Flask(__name__)

# ================= TELEGRAM APP =================
tg_app = Application.builder().token(TOKEN).build()


def is_logged(uid):
    return uid in logged_users


# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logged_users.discard(update.effective_user.id)
    await update.message.reply_text("🤖 Send passcode to login")


async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_logged(uid):
        return await update.message.reply_text("🔒 Login first")

    await update.message.reply_text("\n".join(MODELS))


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # LOGIN REQUIRED EVERY TIME
    if not is_logged(uid):
        if text == PASSCODE:
            logged_users.add(uid)
            user_model[uid] = MODELS[0]
            user_memory[uid] = []
            await update.message.reply_text("✅ Logged in")
        else:
            await update.message.reply_text("❌ Wrong passcode")
        return

    if text in MODELS:
        user_model[uid] = text
        await update.message.reply_text("🧠 Model set")
        return

    if uid not in user_memory:
        user_memory[uid] = []

    user_memory[uid].append({"role": "user", "content": text})

    if len(user_memory[uid]) > MAX_MEMORY:
        user_memory[uid] = user_memory[uid][-MAX_MEMORY:]

    model = user_model.get(uid, MODELS[0])

    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": model,
            "messages": user_memory[uid]
        }
    )

    try:
        reply = r.json()["choices"][0]["message"]["content"]
    except:
        reply = "API error"

    user_memory[uid].append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)


# ================= WEBHOOK ROUTE =================
@app_web.post(f"/{TOKEN}")
def webhook():
    update = Update.de_json(request.get_json(force=True), tg_app.bot)
    tg_app.process_update(update)
    return "ok"


# ================= REGISTER HANDLERS =================
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("model", model))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))


# ================= START SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    print("🚀 Bot running on webhook mode")

    tg_app.bot.set_webhook(url=f"https://YOUR-RENDER-URL.onrender.com/{TOKEN}")

    app_web.run(host="0.0.0.0", port=port)
