import os
import sys
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG & DIAGNOSTICS =================
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# 🚨 Self-Diagnostic Check 🚨
if not TOKEN or TOKEN == "YOUR_ACTUAL_TELEGRAM_TOKEN":
    print("\n" + "!"*50)
    print("🚨 CRITICAL ERROR: TELEGRAM_TOKEN IS MISSING OR INVALID! 🚨")
    print("Make sure you added it exactly as 'TELEGRAM_TOKEN' in Render Environment Variables.")
    print("!"*50 + "\n", flush=True)
    sys.exit(1)

if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_ACTUAL_GROQ_API_KEY":
    print("\n" + "!"*50)
    print("🚨 CRITICAL ERROR: GROQ_API_KEY IS MISSING OR INVALID! 🚨")
    print("Make sure you added it exactly as 'GROQ_API_KEY' in Render Environment Variables.")
    print("!"*50 + "\n", flush=True)
    sys.exit(1)

PASSCODE = "67stien67"

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

        if r.status_code != 200:
            reply = f"⚠️ API Error: {r.status_code} - {r.text}"
        else:
            reply = r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        reply = f"⚠️ Error: {e}"

    user_memory[uid].append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

    print(f"🚀 Bot starting on port {port}...", flush=True)
    print(f"🔗 Webhook URL: {RENDER_URL}/webhook", flush=True)
    
    try:
        # Explicitly create and set the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Initialize application
        tg_app = Application.builder().token(TOKEN).build()
        
        # Register handlers
        tg_app.add_handler(CommandHandler("start", start))
        tg_app.add_handler(CallbackQueryHandler(callback))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
        
        # Run Webhook
        tg_app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{RENDER_URL}/webhook"
        )
    except Exception as e:
        print("\n" + "!"*50)
        print(f"🚨 FATAL ERROR STARTING BOT: {e} 🚨")
        print("!"*50 + "\n", flush=True)
