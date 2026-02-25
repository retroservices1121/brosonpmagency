"""Proof-of-work submission handler — /submit command."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db.kol_repo import get_kol
from db.acceptance_repo import get_acceptances_for_kol
from handlers.common import format_service_type
from services.verification_service import verify_submission

logger = logging.getLogger(__name__)

SELECT_CAMPAIGN, ENTER_TWEET_URL = range(2)


async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show KOL's accepted campaigns that need submission."""
    user = update.effective_user
    kol = get_kol(user.id)
    if not kol:
        await update.message.reply_text(
            "You need to register as a KOL first. Use /start to register."
        )
        return ConversationHandler.END

    acceptances = get_acceptances_for_kol(user.id)
    pending = [a for a in acceptances if a["status"] == "accepted"]

    if not pending:
        await update.message.reply_text(
            "You have no campaigns waiting for submission.\n"
            "Use /campaigns to browse and accept campaigns."
        )
        return ConversationHandler.END

    buttons = []
    for a in pending:
        label = f"#{a['campaign_id']}: {a['project_name']} ({format_service_type(a['service_type'])})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"sub_pick:{a['campaign_id']}:{a['id']}")])

    await update.message.reply_text(
        "Which campaign are you submitting for?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECT_CAMPAIGN


async def campaign_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    campaign_id = int(parts[1])
    acceptance_id = int(parts[2])
    context.user_data["submit_acceptance_id"] = acceptance_id
    context.user_data["submit_campaign_id"] = campaign_id

    await query.edit_message_text(
        f"Submitting for campaign #{campaign_id}.\n\n"
        "Paste your tweet URL:"
    )
    return ENTER_TWEET_URL


async def tweet_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tweet_url = update.message.text.strip()
    acceptance_id = context.user_data.get("submit_acceptance_id")

    if not acceptance_id:
        await update.message.reply_text("Something went wrong. Please try /submit again.")
        return ConversationHandler.END

    await update.message.reply_text("Verifying your submission...")

    result = await verify_submission(acceptance_id, tweet_url)

    if result["verified"]:
        await update.message.reply_text(
            f"Submission verified!\n\n{result['reason']}\n\n"
            "Your payout will be processed by the admin."
        )
    elif result["auto"]:
        await update.message.reply_text(
            f"Verification failed: {result['reason']}\n\n"
            "You can try /submit again with a different URL."
        )
    else:
        await update.message.reply_text(
            f"Auto-verification could not confirm: {result['reason']}\n\n"
            "Your submission has been queued for manual review by an admin."
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Submission cancelled.")
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("submit", submit_start)],
        states={
            SELECT_CAMPAIGN: [CallbackQueryHandler(campaign_picked, pattern=r"^sub_pick:")],
            ENTER_TWEET_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, tweet_url_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
