import os
import sys
import logging
import traceback
import asyncio
from typing import Dict

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

# -------------------- Logging (show everything) --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,   # Ensure logs go to Render's console
)
logger = logging.getLogger(__name__)

# Validate tokens early
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN is not set in environment variables.")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.critical("❌ GROQ_API_KEY is not set in environment variables.")
    sys.exit(1)

AVAILABLE_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
]

PASSCODE = "67stien67"

# Conversation states
WAITING_PASSCODE, SELECTING_MODEL, CHATTING = range(3)

# -------------------- Groq Client --------------------
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("✅ Groq client initialized.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize Groq client: {e}")
    sys.exit(1)

# -------------------- User Data Storage (in‑memory) --------------------
user_data: Dict[int, dict] = {}

def get_user(uid: int) -> dict:
    if uid not in user_data:
        user_data[uid] = {
            "verified": False,
            "current_model": None,
            "histories": {},
        }
    return user_data[uid]

def model_selection_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(model, callback_data=f"model:{model}")]
        for model in AVAILABLE_MODELS
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------- Handlers (unchanged logic) --------------------
async def enforce_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if user["verified"]:
        return ConversationHandler.END
    await update.message.reply_text("🔐 You are not logged in. Please enter the passcode to continue:")
    return WAITING_PASSCODE

async def check_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip()
    user = get_user(update.effective_user.id)
    if user_input == PASSCODE:
        user["verified"] = True
        await update.message.reply_text(
            "✅ Passcode accepted! Choose a model:",
            reply_markup=model_selection_keyboard()
        )
        return SELECTING_MODEL
    else:
        await update.message.reply_text("❌ Incorrect passcode. Try again:")
        return WAITING_PASSCODE

async def model_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("model:"):
        return SELECTING_MODEL
    model_name = query.data.split(":", 1)[1]
    user = get_user(update.effective_user.id)
    user["current_model"] = model_name
    if model_name not in user["histories"]:
        user["histories"][model_name] = []
    await query.edit_message_text(
        f"🤖 Model set to: `{model_name}`\n\n"
        f"You can now chat! Send me a message.\n"
        f"Use /model to switch models anytime.",
        parse_mode="Markdown"
    )
    return CHATTING

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if not user["verified"]:
        await update.message.reply_text("🔐 Please enter the passcode first:")
        return WAITING_PASSCODE
    await update.message.reply_text(
        "Choose a new model:",
        reply_markup=model_selection_keyboard()
    )
    return SELECTING_MODEL

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    user_message = update.message.text
    if not user["verified"] or not user["current_model"]:
        await update.message.reply_text("⚠️ Session error. Please /start again.")
        return ConversationHandler.END

    model = user["current_model"]
    history = user["histories"][model]
    history.append({"role": "user", "content": user_message})
    if len(history) > 20:
        user["histories"][model] = history[-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        completion = groq_client.chat.completions.create(
            model=model,
            messages=history,
            temperature=0.7,
            max_tokens=1024,
        )
        bot_reply = completion.choices[0].message.content
        history.append({"role": "assistant", "content": bot_reply})
        user["histories"][model] = history
        await update.message.reply_text(bot_reply)
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        await update.message.reply_text(
            "❌ Sorry, something went wrong with the AI service. Please try again later."
        )
    return CHATTING

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if user["verified"] and user["current_model"]:
        await update.message.reply_text(
            f"✅ You're logged in with model `{user['current_model']}`.\n"
            f"Send a message or use /model to switch.",
            parse_mode="Markdown"
        )
        return CHATTING
    else:
        await update.message.reply_text("🔐 Please enter the passcode to continue:")
        return WAITING_PASSCODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled. Send /start to begin again.")
    return ConversationHandler.END

# -------------------- Main Application --------------------
def main() -> None:
    """Build and run the bot with comprehensive error logging."""
    logger.info("🚀 Starting bot initialization...")

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ PTB Application built.")
    except Exception as e:
        logger.critical(f"❌ Failed to build Application: {e}")
        traceback.print_exc()
        sys.exit(1)

    # Conversation handler setup
    conv_handler = ConversationHandler(
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
                CallbackQueryHandler(model_selection_callback, pattern="^model:"),
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
    application.add_handler(conv_handler)

    logger.info("✅ Handlers registered. Starting polling...")
    try:
        # This will block and run until interrupted
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"❌ Bot crashed during polling: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Ensure we're in a proper asyncio environment
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"❌ Unhandled exception in main: {e}")
        traceback.print_exc()
        sys.exit(1)
