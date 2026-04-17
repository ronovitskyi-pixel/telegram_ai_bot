import os
import sys
import logging
import traceback
from typing import Dict

# Required for Render's environment
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

# --- Webhook related imports ---
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
import uvicorn
from telegram.ext import ApplicationBuilder, AIORateLimiter
from telegram.request import HTTPXRequest

# -------------------- Configuration --------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Render provides a PORT environment variable. Default to 10000 for local testing.
PORT = int(os.environ.get("PORT", 10000))
# The public URL of your Render app. You'll get this after creating the Web Service.
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# -------------------- Logging --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Validate tokens
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing.")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.critical("❌ GROQ_API_KEY missing.")
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
user_data: Dict[int, dict] = {}

def get_user(uid: int) -> dict:
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

# -------------------- Handlers (unchanged logic) --------------------
async def enforce_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if user["verified"]:
        return ConversationHandler.END
    await update.message.reply_text("🔐 Please enter the passcode:")
    return WAITING_PASSCODE

async def check_passcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if update.message.text.strip() == PASSCODE:
        user["verified"] = True
        await update.message.reply_text("✅ Passcode accepted! Choose a model:", reply_markup=model_keyboard())
        return SELECTING_MODEL
    await update.message.reply_text("❌ Incorrect. Try again:")
    return WAITING_PASSCODE

async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if not user["verified"]:
        await update.message.reply_text("🔐 Passcode first:")
        return WAITING_PASSCODE
    await update.message.reply_text("Choose a model:", reply_markup=model_keyboard())
    return SELECTING_MODEL

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = get_user(update.effective_user.id)
    if user["verified"] and user["current_model"]:
        await update.message.reply_text(
            f"✅ Logged in with `{user['current_model']}`. Chat away!",
            parse_mode="Markdown"
        )
        return CHATTING
    await update.message.reply_text("🔐 Enter passcode:")
    return WAITING_PASSCODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled. /start to begin.")
    return ConversationHandler.END

# -------------------- Webhook Setup --------------------
async def health(_):
    """Simple health check endpoint for Render."""
    return Response("OK", status_code=200)

async def webhook(request):
    """Process incoming updates from Telegram."""
    if request.method == "POST":
        try:
            # Get the application instance from app.state
            ptb_app = request.app.state.ptb_app
            # Decode the request body
            body = await request.body()
            # Let python-telegram-bot process the update
            await ptb_app.update_queue.put(
                Update.de_json(body.decode("utf-8"), ptb_app.bot)
            )
            return Response("OK", status_code=200)
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return Response("Error", status_code=500)
    return Response("Method not allowed", status_code=405)

async def set_webhook(_):
    """Set the webhook with Telegram (called on startup)."""
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL not set. Webhook will not be configured.")
        return
    try:
        # We need a temporary application instance just to set the webhook
        temp_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        await temp_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
        await temp_app.shutdown()
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")

# -------------------- Main Application --------------------
def main():
    """Run the bot with a web server."""
    # Create the PTB Application
    ptb_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add conversation handler
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
    ptb_app.add_handler(conv)

    # Initialize the PTB application (this starts the background polling, but we'll disable it)
    # Instead, we just want the bot to be ready to process updates from webhooks.
    # We'll use initialize() and start() manually.
    
    # Create Starlette app for webhooks
    starlette_app = Starlette(
        routes=[
            Route("/healthcheck", health, methods=["GET"]),
            Route("/webhook", webhook, methods=["POST"]),
        ],
    )
    # Attach the PTB app to the Starlette app's state
    starlette_app.state.ptb_app = ptb_app

    # Startup event to initialize PTB and set webhook
    @starlette_app.on_event("startup")
    async def startup():
        logger.info("Initializing PTB application...")
        await ptb_app.initialize()
        await ptb_app.start()
        # Set webhook after startup
        await set_webhook(None)
        logger.info("✅ Webhook bot started successfully.")

    @starlette_app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down PTB application...")
        await ptb_app.stop()
        await ptb_app.shutdown()

    # Run the server
    uvicorn.run(starlette_app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
