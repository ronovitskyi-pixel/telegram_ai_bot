import os
import requests
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
# Use Environment Variables instead of hardcoding sensitive keys!
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PASSCODE = "67stien67"

# NOTE: I updated your models. "openai/gpt-oss-120b" does not exist on Groq's API.
# Using invalid models will cause the bot to silently fail or return an API error.
MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

# ================= STATE =================
logged_users = set()
user_model = {}
user_memory = {}

# ================= APP =================
tg_app = Application.builder().token(TOKEN).build()

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
        # Note: requests.post is synchronous. In a busy bot, this would freeze the bot 
        # for other users while it waits for Groq. For a personal bot, it is fine.
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

        if r.status_code != 200:
            reply = f"⚠️ API Error: {r.status_code} - {r.text}"
        else:
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
    
    # Render automatically provides this environment variable for Web Services
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", f"https://your-app-name.onrender.com")

    print(f"🚀 Bot starting on port {port}...")
    print(f"🔗 Webhook URL: {RENDER_URL}/webhook")
    
    # Use python-telegram-bot's built-in webhook runner instead of Flask
    tg_app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",
        webhook_url=f"{RENDER_URL}/webhook"
    )
