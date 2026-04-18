import os
import sys
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
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

# ================= KEYBOARDS (THE TYPING MENU) =================
def main_keyboard():
    # The buttons that sit at the bottom of the screen normally
    return ReplyKeyboardMarkup(
        [["🧠 Change Model", "🧹 Clear Memory"]],
        resize_keyboard=True,
        is_persistent=True
    )

def model_keyboard():
    # Creates a neat grid of buttons for the models
    keyboard = []
    # Put 2 models per row so it looks nice on a phone screen
    for i in range(0, len(MODELS), 2):
        keyboard.append(MODELS[i:i+2])
    # Add a back button at the bottom
    keyboard.append(["🔙 Back to Chat"])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome back!**\n\n"
        "Check out your new menu at the bottom of the screen! 👇\n"
        "Use the buttons to change your AI model or wipe my memory."
    )
    # Send the main keyboard when they type /start
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ================= CHAT & MENU LOGIC =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # --- MENU BUTTON INTERCEPTORS ---
    # If they press a menu button, we handle it here and stop the AI from replying to it.

    if text == "🧹 Clear Memory":
        user_memory[uid] = []
        await update.message.reply_text("🧹 Memory completely cleared! Ready for a new topic.", reply_markup=main_keyboard())
        return

    if text == "🧠 Change Model":
        await update.message.reply_text("🧠 Choose your new brain from the keyboard below:", reply_markup=model_keyboard())
        return

    if text == "🔙 Back to Chat":
        await update.message.reply_text("Cancelled. Back to chatting!", reply_markup=main_keyboard())
        return

    if text in MODELS:
        user_model[uid] = text
        await update.message.reply_text(f"✅ Model successfully set to:\n**{text}**\n\nSay hello!", parse_mode="Markdown", reply_markup=main_keyboard())
        return

    # --- AI CHAT LOGIC ---
    # If the text wasn't a menu button, treat it as a normal message for the AI.

    if uid not in user_memory:
        user_memory[uid] = []

    user_memory[uid].append({"role": "user", "content": text})
    user_memory[uid] = user_memory[uid][-10:]

    model = user_model.get(uid, MODELS[0])

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
            reply = f"⚠️ API Error: {r.status_code}\n(If this says 'Model not found', Groq doesn't host this specific model!)"
        else:
            reply = r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        reply = f"⚠️ Network Error: {e}"

    user_memory[uid].append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply, reply_markup=main_keyboard())

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

    print(f"🚀 Bot starting on port {port}...", flush=True)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        tg_app = Application.builder().token(TOKEN).build()
        
        tg_app.add_handler(CommandHandler("start", start))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
        
        tg_app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{RENDER_URL}/webhook"
        )
    except Exception as e:
        print(f"\n🚨 FATAL ERROR: {e} 🚨\n", flush=True)
