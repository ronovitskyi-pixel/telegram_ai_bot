import os
import sys
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

if not TOKEN or TOKEN == "YOUR_ACTUAL_TELEGRAM_TOKEN":
    print("\n" + "!"*50 + "\n🚨 MISSING TELEGRAM_TOKEN! 🚨\n" + "!"*50 + "\n", flush=True)
    sys.exit(1)

if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_ACTUAL_GROQ_API_KEY":
    print("\n" + "!"*50 + "\n🚨 MISSING GROQ_API_KEY! 🚨\n" + "!"*50 + "\n", flush=True)
    sys.exit(1)

# Exactly the models you requested
MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b"
]

# ================= STATE (MEMORY) =================
user_model = {}
user_memory = {}

# ================= UI & MENU =================
async def post_init(application: Application):
    # This creates the menu inside the "typing bar thing"!
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("model", "Change the AI model"),
        BotCommand("clear", "Clear the bot's memory")
    ])

def model_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(m, callback_data=f"model:{m}")] for m in MODELS]
    )

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome!** I am fully open and ready to chat.\n\n"
        "• I will remember our conversation.\n"
        "• Use /model to switch my brain.\n"
        "• Use /clear to wipe my memory if we change topics."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 Choose your model:", reply_markup=model_menu())

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_memory[uid] = []
    await update.message.reply_text("🧹 Memory completely cleared! What's next?")

# ================= CALLBACK (BUTTONS) =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data.startswith("model:"):
        model = q.data.split(":", 1)[1]
        user_model[uid] = model
        await q.edit_message_text(f"✅ Model successfully set to:\n**{model}**", parse_mode="Markdown")

# ================= CHAT (AI LOGIC) =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # 1. Setup memory for new users
    if uid not in user_memory:
        user_memory[uid] = []

    # 2. Add user message to memory
    user_memory[uid].append({"role": "user", "content": text})
    
    # Keep only the last 10 messages so the bot doesn't crash from memory overload
    user_memory[uid] = user_memory[uid][-10:]

    # 3. Get the user's chosen model (default to the first one)
    model = user_model.get(uid, MODELS[0])

    # 4. Talk to the API
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
            reply = f"⚠️ API Error: {r.status_code}\n(If this says 'Model not found', Groq doesn't support this specific model name!)"
        else:
            reply = r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        reply = f"⚠️ Network Error: {e}"

    # 5. Add bot's reply to memory so it remembers its own answers!
    user_memory[uid].append({"role": "assistant", "content": reply})
    
    await update.message.reply_text(reply)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

    print(f"🚀 Bot starting on port {port}...", flush=True)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # We add post_init here to push the commands to the Telegram menu
        tg_app = Application.builder().token(TOKEN).post_init(post_init).build()
        
        # Register commands so the AI doesn't "eat" them
        tg_app.add_handler(CommandHandler("start", start))
        tg_app.add_handler(CommandHandler("model", cmd_model))
        tg_app.add_handler(CommandHandler("clear", cmd_clear))
        
        tg_app.add_handler(CallbackQueryHandler(callback))
        
        # ~filters.COMMAND makes sure it ignores things starting with "/"
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
        
        tg_app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{RENDER_URL}/webhook"
        )
    except Exception as e:
        print(f"\n🚨 FATAL ERROR: {e} 🚨\n", flush=True)
