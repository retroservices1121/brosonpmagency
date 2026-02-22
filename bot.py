import io
import os
import logging

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from database import init_db, save_kol, get_kol, save_customer, export_csv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
CHOOSE_ROLE, KOL_NAME, KOL_X, KOL_WALLET, CUST_NAME, CUST_X, CUST_TG = range(7)

CHANNEL_LINK = "https://t.me/+UV2UD42DM5gwZjFh"
POSTER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poster.png")
ADMIN_USERNAME = "Game4Charity"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [
            InlineKeyboardButton("Register as KOL", callback_data="kol"),
            InlineKeyboardButton("Register as Customer", callback_data="customer"),
        ]
    ]
    with open(POSTER_PATH, "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=(
                "Welcome to BrosOnPM Agency!\n"
                "The prediction markets amplification agency.\n\n"
                "🎙 Influencers — this is for you if you already talk about Polymarket on X.\n\n"
                "🏗 Customers — this is for you if you are building on top of Polymarket.\n\n"
                "How would you like to register?"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return CHOOSE_ROLE


async def role_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    context.user_data["telegram_handle"] = f"@{user.username}" if user.username else None

    if query.data == "kol":
        context.user_data["role"] = "kol"
        existing = get_kol(user.id)
        if existing:
            await query.edit_message_caption(
                caption=(
                    f"You're already registered as a KOL!\n\n"
                    f"Name: {existing['name']}\n"
                    f"X Account: {existing['x_account']}\n"
                    f"Telegram: {existing['telegram_handle']}\n\n"
                    f"Type your name to re-register, or /cancel to keep your current info."
                )
            )
        else:
            await query.edit_message_caption(caption="Great! What is your name?")
        return KOL_NAME

    elif query.data == "customer":
        context.user_data["role"] = "customer"
        await query.edit_message_caption(
            caption="Thanks for your interest in a campaign!\n\nWhat is your name?"
        )
        return CUST_NAME


# --- KOL flow ---

async def kol_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "What is your X (Twitter) handle? (e.g. @yourhandle)"
    )
    return KOL_X


async def kol_x_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["x_account"] = update.message.text.strip().lstrip("@")
    await update.message.reply_text(
        "What is your USDC wallet address on Base? (for payouts)"
    )
    return KOL_WALLET


async def kol_wallet_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wallet_address = update.message.text.strip()
    user = update.effective_user
    name = context.user_data["name"]
    x_account = context.user_data["x_account"]
    telegram_handle = context.user_data["telegram_handle"] or str(user.id)

    save_kol(
        telegram_id=user.id,
        telegram_handle=telegram_handle,
        name=name,
        x_account=x_account,
        wallet_address=wallet_address,
    )

    await update.message.reply_text(
        "Registration complete! Here's your info:\n\n"
        f"Name: {name}\n"
        f"X Account: @{x_account}\n"
        f"Wallet (Base): {wallet_address}\n"
        f"Telegram: {telegram_handle}\n\n"
        f"Join the BrosAgency Channel: {CHANNEL_LINK}"
    )
    return ConversationHandler.END


# --- Customer flow ---

async def cust_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "What is your project's X (Twitter) account? (e.g. @projecthandle)"
    )
    return CUST_X


async def cust_x_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["project_x"] = update.message.text.strip().lstrip("@")
    user = update.effective_user
    telegram_handle = context.user_data["telegram_handle"]

    if telegram_handle:
        # We already have their Telegram handle, skip asking
        return await _finish_customer(update, context, telegram_handle)

    await update.message.reply_text(
        "What is your Telegram handle? (e.g. @yourhandle)"
    )
    return CUST_TG


async def cust_tg_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_handle = update.message.text.strip()
    if not telegram_handle.startswith("@"):
        telegram_handle = f"@{telegram_handle}"
    return await _finish_customer(update, context, telegram_handle)


async def _finish_customer(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_handle: str) -> int:
    user = update.effective_user
    name = context.user_data["name"]
    project_x = context.user_data["project_x"]

    save_customer(
        telegram_id=user.id,
        telegram_handle=telegram_handle,
        name=name,
        project_x_account=project_x,
    )

    await update.message.reply_text(
        "Thank you! An admin will reach out soon to discuss our campaign offerings.\n\n"
        f"Your info:\n"
        f"Name: {name}\n"
        f"Project X Account: @{project_x}\n"
        f"Telegram: {telegram_handle}"
    )

    # Alert admin
    try:
        await context.bot.send_message(
            chat_id=f"@{ADMIN_USERNAME}",
            text=(
                "New customer registration!\n\n"
                f"Name: {name}\n"
                f"Project X Account: @{project_x}\n"
                f"Telegram: {telegram_handle}"
            ),
        )
    except Exception as e:
        logger.warning(f"Could not notify admin @{ADMIN_USERNAME}: {e}")

    return ConversationHandler.END


# --- Export & Cancel ---

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    csv_kols = export_csv("kols")
    buf_kols = io.BytesIO(csv_kols.encode("utf-8"))
    buf_kols.name = "kols_export.csv"
    await update.message.reply_document(document=buf_kols, caption="KOLs registration export")

    csv_customers = export_csv("customers")
    buf_cust = io.BytesIO(csv_customers.encode("utf-8"))
    buf_cust.name = "customers_export.csv"
    await update.message.reply_document(document=buf_cust, caption="Customers registration export")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Create a .env file with your bot token (see .env.example)."
        )

    init_db()

    app = ApplicationBuilder().token(token).build()

    text_no_cmd = MessageHandler(filters.TEXT & ~filters.COMMAND, None)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ROLE: [CallbackQueryHandler(role_chosen)],
            KOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_name_received)],
            KOL_X: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_x_received)],
            KOL_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_wallet_received)],
            CUST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_name_received)],
            CUST_X: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_x_received)],
            CUST_TG: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_tg_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("export", export))

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
