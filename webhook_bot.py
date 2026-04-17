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
pending_model_confirm = {}

MAX_MEMORY = 12

# ================= FLASK =================
app_web = Flask(__name__)

tg_app = Application.builder().token(TOKEN).build()


# ================= HELPERS =================
def is_logged(uid):
    return uid in logged_users


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Login", callback_data="login")],
        [InlineKeyboardButton("🧠 Model", callback_data="models")]
    ])


def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])


def model_menu():
    buttons = [[InlineKeyboardButton(m, callback_data=f"pick:{m}")] for m in MODELS]
    buttons.append([InlineKeyboardButton("⬅ Back", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def confirm_menu(model):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{model}"),
            InlineKeyboardButton("❌ Cancel", callback_data="models")
        ]
    ])


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    await update.message.reply_text(
        "🤖 AI BOT READY\n\n🔒 Login required to continue",
        reply_markup=main_menu()
    )


# ================= CALLBACKS =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data

    # ---------------- BACK ----------------
    if data == "back":
        await query.edit_message_text("🏠 Main Menu", reply_markup=main_menu())
        return

    # ---------------- LOGIN ----------------
    if data == "login":
        if is_logged(uid):
            await query.edit_message_text(
                "✅ You are already logged in.",
                reply_markup=main_menu()
            )
            return

        await query.edit_message_text("🔑 Send passcode now:")
        return

    # ---------------- MODEL MENU ----------------
    if data == "models":
        if not is_logged(uid):
            await query.edit_message_text("🔒 Login first", reply_markup=back_menu())
            return

        await query.edit_message_text("🧠 Choose model:", reply_markup=model_menu())
        return

    # ---------------- PICK MODEL ----------------
    if data.startswith("pick:"):
        model = data.split(":", 1)[1]
        pending_model_confirm[uid] = model

        await query.edit_message_text(
            f"⚠️ Confirm model:\n\n{model}",
            reply_markup=confirm_menu(model)
        )
        return

    # ---------------- CONFIRM MODEL ----------------
    if data.startswith("confirm:"):
        model = data.split(":", 1)[1]

        user_model[uid] = model
        pending_model_confirm.pop(uid, None)

        await query.edit_message_text(
            f"✅ Model selected:\n{model}",
            reply_markup=main_menu()
        )
        return


# ================= MESSAGE HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # 🔒 LOGIN SYSTEM (NO SPAM FIX)
    if not is_logged(uid):
        if text == PASSCODE:
            logged_users.add(uid)
            user_model[uid] = MODELS[0]
            user_memory[uid] = []

            await update.message.reply_text(
                "✅ Logged in successfully!",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text("🔒 Wrong passcode")
        return

    # ---------------- MEMORY INIT ----------------
    if uid not in user_memory:
        user_memory[uid] = []

    user_memory[uid].append({"role": "user", "content": text})

    if len(user_memory[uid]) > MAX_MEMORY:
        user_memory[uid] = user_memory[uid][-MAX_MEMORY:]

    model = user_model.get(uid, MODELS[0])

    # ---------------- GROQ CALL ----------------
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

    await update.message.reply_text(reply, reply_markup=main_menu())


# ================= WEBHOOK =================
@app_web.post(f"/{TOKEN}")
def webhook():
    update = Update.de_json(request.get_json(force=True), tg_app.bot)
    tg_app.process_update(update)
    return "ok"


# ================= REGISTER HANDLERS =================
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CallbackQueryHandler(callback))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    print("🚀 Bot running (final version)")

    tg_app.bot.set_webhook(
        url=f"https://telegram-ai-bot-3370.onrender.com/{TOKEN}"
    )

    app_web.run(host="0.0.0.0", port=port)
