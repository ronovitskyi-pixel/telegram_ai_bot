import os
import sys
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ================= CONFIG & DIAGNOSTICS =================
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "").strip()

if not TOKEN:
    print("\n🚨 MISSING TELEGRAM_TOKEN! 🚨\n", flush=True)
    sys.exit(1)

# ================= MODEL DICTIONARY =================
MODEL_CONFIGS = {
    # Groq Models (Ultra-fast, permanent free tier)
    "llama-3.3-70b-versatile": {"provider": "groq"},
    "llama-3.1-8b-instant": {"provider": "groq"},
    "mixtral-8x7b-32768": {"provider": "groq"},
    "gemma2-9b-it": {"provider": "groq"},
    
    # Z.AI Models (The 100% Free Tier models)
    "glm-4-flash": {"provider": "zai"},
    "glm-4-flashx": {"provider": "zai"}
}

MODELS = list(MODEL_CONFIGS.keys())

# Group the models for the UI Categories
PROVIDER_GROUPS = {
    "🟢 Groq Models": [m for m, c in MODEL_CONFIGS.items() if c["provider"] == "groq"],
    "🟣 Z.ai Models": [m for m, c in MODEL_CONFIGS.items() if c["provider"] == "zai"],
}

# ================= STATE (MEMORY) =================
user_model = {}
user_memory = {}

# ================= KEYBOARDS =================
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["🧠 Change Model", "🧹 Clear Memory"]],
        resize_keyboard=True,
        is_persistent=True
    )

def category_keyboard():
    # DeepSeek removed from the menu
    return ReplyKeyboardMarkup(
        [
            ["🟢 Groq Models", "🟣 Z.ai Models"],
            ["🔙 Back to Chat"]
        ],
        resize_keyboard=True
    )

def provider_keyboard(category_name):
    models = PROVIDER_GROUPS.get(category_name, [])
    keyboard = []
    
    for i in range(0, len(models), 2):
        keyboard.append(models[i:i+2])
        
    keyboard.append(["🔙 Back to Categories"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome!**\n\n"
        "Use the buttons below to switch models or clear your chat memory."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ================= CHAT & MULTI-API LOGIC =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # --- MENU INTERCEPTORS ---
    if text == "🧹 Clear Memory":
        user_memory[uid] = []
        await update.message.reply_text("🧹 Memory cleared! What's next?", reply_markup=main_keyboard())
        return

    if text == "🧠 Change Model" or text == "🔙 Back to Categories":
        await update.message.reply_text("📂 Choose an AI Provider:", reply_markup=category_keyboard())
        return

    if text == "🔙 Back to Chat":
        await update.message.reply_text("Cancelled. Back to chatting!", reply_markup=main_keyboard())
        return

    if text in PROVIDER_GROUPS:
        await update.message.reply_text(f"👇 Select a model from {text}:", reply_markup=provider_keyboard(text))
        return

    if text in MODELS:
        user_model[uid] = text
        await update.message.reply_text(f"✅ Model set to:\n**{text}**\n\nSay hello!", parse_mode="Markdown", reply_markup=main_keyboard())
        return

    # --- AI CHAT LOGIC ---
    if uid not in user_memory:
        user_memory[uid] = []

    user_memory[uid].append({"role": "user", "content": text})
    user_memory[uid] = user_memory[uid][-10:]

    model_name = user_model.get(uid, MODELS[0])
    provider = MODEL_CONFIGS[model_name]["provider"]

    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = GROQ_API_KEY
    elif provider == "zai":
        url = "https://api.z.ai/api/paas/v4/chat/completions"
        api_key = ZAI_API_KEY

    if not api_key:
        await update.message.reply_text(f"⚠️ You need to add {provider.upper()}_API_KEY to your Render Environment Variables to use this model!", reply_markup=main_keyboard())
        user_memory[uid].pop() 
        return

    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_name,
                "messages": user_memory[uid]
            },
            timeout=30
        )

        if r.status_code != 200:
            reply = f"⚠️ API Error ({r.status_code}): {r.text}"
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
