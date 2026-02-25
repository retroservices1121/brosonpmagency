"""Registration conversation handler — extracted from original bot.py.

Handles /start → role selection → KOL or Customer registration flow.
"""
import logging
import os
import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import CHANNEL_LINK, POSTER_PATH, X_API_BEARER_TOKEN
from db.kol_repo import save_kol, get_kol, update_kol_verification
from db.customer_repo import save_customer
from handlers.common import notify_admins
from services import x_api

logger = logging.getLogger(__name__)

# Conversation states
(
    CHOOSE_ROLE,
    KOL_NAME,
    KOL_X,
    KOL_WALLET,
    KOL_VERIFY_PROMPT,
    KOL_VERIFY_CHECK,
    CUST_NAME,
    CUST_X,
    CUST_TG,
) = range(9)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [
            InlineKeyboardButton("Register as KOL", callback_data="reg_kol"),
            InlineKeyboardButton("Register as Customer", callback_data="reg_customer"),
        ]
    ]
    if os.path.exists(POSTER_PATH):
        with open(POSTER_PATH, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    "Welcome to BrosOnPM Agency!\n"
                    "The prediction markets amplification agency.\n\n"
                    "Influencers — this is for you if you already talk about Polymarket on X.\n\n"
                    "Customers — this is for you if you are building on top of Polymarket.\n\n"
                    "How would you like to register?"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
    else:
        await update.message.reply_text(
            "Welcome to BrosOnPM Agency!\n\nHow would you like to register?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return CHOOSE_ROLE


async def role_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    context.user_data["telegram_handle"] = f"@{user.username}" if user.username else None

    if query.data == "reg_kol":
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

    elif query.data == "reg_customer":
        context.user_data["role"] = "customer"
        await query.edit_message_caption(
            caption="Thanks for your interest in a campaign!\n\nWhat is your name?"
        )
        return CUST_NAME

    return ConversationHandler.END


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

    # If X API is configured, offer verification
    if X_API_BEARER_TOKEN:
        code = secrets.token_hex(4).upper()
        context.user_data["verify_code"] = code
        await update.message.reply_text(
            f"Registration saved! Now let's verify your X account.\n\n"
            f"Please tweet the following code from @{x_account}:\n\n"
            f"Verifying my BrosOnPM KOL account: {code}\n\n"
            f"Then click 'Verify' below, or /skip to skip verification for now.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Verify", callback_data="reg_verify_check")],
                [InlineKeyboardButton("Skip", callback_data="reg_verify_skip")],
            ]),
        )
        return KOL_VERIFY_PROMPT

    # No X API — finish without verification
    await update.message.reply_text(
        "Registration complete! Here's your info:\n\n"
        f"Name: {name}\n"
        f"X Account: @{x_account}\n"
        f"Wallet (Base): {wallet_address}\n"
        f"Telegram: {telegram_handle}\n\n"
        f"Join the BrosAgency Channel: {CHANNEL_LINK}"
    )
    return ConversationHandler.END


async def kol_verify_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "reg_verify_skip":
        user = query.from_user
        kol = get_kol(user.id)
        await query.edit_message_text(
            "Verification skipped. You can verify later.\n\n"
            f"Registration complete!\n"
            f"Name: {kol['name']}\n"
            f"X Account: @{kol['x_account']}\n"
            f"Wallet (Base): {kol['wallet_address']}\n\n"
            f"Join the BrosAgency Channel: {CHANNEL_LINK}"
        )
        return ConversationHandler.END

    # reg_verify_check — attempt verification
    user = query.from_user
    x_account = context.user_data.get("x_account", "")
    code = context.user_data.get("verify_code", "")

    await query.edit_message_text("Checking your X account for the verification tweet...")

    x_user = await x_api.get_user_by_username(x_account)
    if not x_user:
        await query.message.reply_text(
            f"Could not find X user @{x_account}. Please check the handle and try again.\n"
            "Use /skip to skip verification for now.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Retry", callback_data="reg_verify_check")],
                [InlineKeyboardButton("Skip", callback_data="reg_verify_skip")],
            ]),
        )
        return KOL_VERIFY_PROMPT

    x_user_id = x_user["id"]
    followers = x_user.get("public_metrics", {}).get("followers_count", 0)

    verified = await x_api.verify_user_tweet(x_user_id, code)
    if verified:
        update_kol_verification(user.id, x_user_id, followers, True)
        kol = get_kol(user.id)
        await query.message.reply_text(
            "X account verified!\n\n"
            f"Registration complete!\n"
            f"Name: {kol['name']}\n"
            f"X Account: @{kol['x_account']} (verified)\n"
            f"Followers: {followers:,}\n"
            f"Wallet (Base): {kol['wallet_address']}\n\n"
            f"Join the BrosAgency Channel: {CHANNEL_LINK}"
        )
        return ConversationHandler.END
    else:
        await query.message.reply_text(
            "Verification tweet not found yet. Make sure you tweeted the exact code.\n"
            "It may take a minute to propagate. Try again or skip.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Retry", callback_data="reg_verify_check")],
                [InlineKeyboardButton("Skip", callback_data="reg_verify_skip")],
            ]),
        )
        return KOL_VERIFY_PROMPT


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
        "Thank you! You can now create campaigns with /newcampaign.\n\n"
        f"Your info:\n"
        f"Name: {name}\n"
        f"Project X Account: @{project_x}\n"
        f"Telegram: {telegram_handle}"
    )

    # Alert admins
    await notify_admins(
        context.bot,
        text=(
            "New customer registration!\n\n"
            f"Name: {name}\n"
            f"Project X Account: @{project_x}\n"
            f"Telegram: {telegram_handle}"
        ),
    )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /skip during verification."""
    user = update.effective_user
    kol = get_kol(user.id)
    if kol:
        await update.message.reply_text(
            "Verification skipped.\n\n"
            f"Registration complete!\n"
            f"Name: {kol['name']}\n"
            f"X Account: @{kol['x_account']}\n"
            f"Wallet (Base): {kol['wallet_address']}\n\n"
            f"Join the BrosAgency Channel: {CHANNEL_LINK}"
        )
    else:
        await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ROLE: [CallbackQueryHandler(role_chosen, pattern="^reg_")],
            KOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_name_received)],
            KOL_X: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_x_received)],
            KOL_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_wallet_received)],
            KOL_VERIFY_PROMPT: [CallbackQueryHandler(kol_verify_action, pattern="^reg_verify_")],
            CUST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_name_received)],
            CUST_X: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_x_received)],
            CUST_TG: [MessageHandler(filters.TEXT & ~filters.COMMAND, cust_tg_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("skip", skip),
        ],
        allow_reentry=True,
    )
