import os
import sys
import logging
import traceback

# 🔧 Fix for Render's asyncio conflict – apply BEFORE any other imports
import nest_asyncio
nest_asyncio.apply()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from groq import Groq

# -------------------- Configuration --------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# -------------------- Logging --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Validate tokens
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing. Check Render environment variables.")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.critical("❌ GROQ_API_KEY missing. Check Render environment variables.")
    sys.exit(1)

AVAILABLE_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
]

PASSCODE = "67stien67"

WAITING_PASSCODE, SELECTING_MODEL, CHATTING = range(3)

# -------------------- Groq Client --------------------
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("✅ Groq client ready.")
except Exception as e:
    logger.critical(f"❌ Groq client init failed: {e}")
    sys.exit(1)

# -------------------- In‑memory user store --------------------
user_data = {}

def get_user(uid: int):
    if uid not in user_data:
        user_data[uid] = {
            "verified": False,
            "current_model": None,
            "histories": {},
        }
    return user_data[uid]

def model_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(m, callback_data=f"model:{m}")] for m in AVAILABLE_MODELS
    ])

# -------------------- Handlers --------------------
async def enforce_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user["verified"]:
        return ConversationHandler.END
    await update.message.reply_text("🔐 Please enter the passcode:")
    return WAITING_PASSCODE

async def check_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if update.message.text.strip() == PASSCODE:
        user["verified"] = True
        await update.message.reply_text("✅ Passcode accepted! Choose a model:", reply_markup=model_keyboard())
        return SELECTING_MODEL
    await update.message.reply_text("❌ Incorrect. Try again:")
    return WAITING_PASSCODE

async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("model:"):
        return SELECTING_MODEL
    model = query.data.split(":", 1)[1]
    user = get_user(update.effective_user.id)
    user["current_model"] = model
    user["histories"].setdefault(model, [])
    await query.edit_message_text(
        f"🤖 Model set to `{model}`.\nYou can now chat!",
        parse_mode="Markdown"
    )
    return CHATTING

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user["verified"]:
        await update.message.reply_text("🔐 Passcode first:")
        return WAITING_PASSCODE
    await update.message.reply_text("Choose a model:", reply_markup=model_keyboard())
    return SELECTING_MODEL

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user["verified"] or not user["current_model"]:
        await update.message.reply_text("⚠️ Session error. /start again.")
        return ConversationHandler.END

    model = user["current_model"]
    history = user["histories"][model]
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 20:
        history = history[-20:]
        user["histories"][model] = history

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        resp = groq_client.chat.completions.create(
            model=model,
            messages=history,
            temperature=0.7,
            max_tokens=1024,
        )
        reply = resp.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Groq error: {e}")
        await update.message.reply_text("❌ AI service error. Try again later.")
    return CHATTING

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user["verified"] and user["current_model"]:
        await update.message.reply_text(
            f"✅ Logged in with `{user['current_model']}`. Chat away!",
            parse_mode="Markdown"
        )
        return CHATTING
    await update.message.reply_text("🔐 Enter passcode:")
    return WAITING_PASSCODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. /start to begin.")
    return ConversationHandler.END

# -------------------- Main --------------------
def main():
    logger.info("🚀 Starting bot...")
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
    except Exception as e:
        logger.critical(f"❌ PTB build failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.ALL & ~filters.COMMAND, enforce_passcode),
            CommandHandler(["model", "cancel"], enforce_passcode),
        ],
        states={
            WAITING_PASSCODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_passcode),
                CommandHandler(["model", "cancel", "start"], enforce_passcode),
            ],
            SELECTING_MODEL: [
                CallbackQueryHandler(model_callback, pattern="^model:"),
                CommandHandler("cancel", cancel),
            ],
            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat),
                CommandHandler("model", model_command),
                CommandHandler("start", start),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)

    logger.info("✅ Bot polling started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")
    except Exception as e:
        logger.critical(f"❌ Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
