"""Campaign browsing and FCFS acceptance — /campaigns command + accept callback."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from config import SERVICE_TIERS
from db.campaign_repo import get_campaign, get_live_campaigns
from db.kol_repo import get_kol
from handlers.common import format_cents, format_service_type
from services.acceptance_service import accept_campaign, AcceptanceError

logger = logging.getLogger(__name__)


async def browse_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show live campaigns for KOLs to browse."""
    user = update.effective_user
    kol = get_kol(user.id)
    if not kol:
        await update.message.reply_text(
            "You need to register as a KOL first. Use /start to register."
        )
        return

    campaigns = get_live_campaigns()
    live = [c for c in campaigns if c["status"] == "live"]

    if not live:
        await update.message.reply_text("No campaigns available right now. Check back later!")
        return

    for c in live:
        remaining = c["kol_count"] - c["accepted_count"]
        if remaining <= 0:
            continue

        tier_name = format_service_type(c["service_type"])
        text = (
            f"Campaign #{c['id']}: {c['project_name']}\n"
            f"Service: {tier_name}\n"
            f"Rate: {format_cents(c['per_kol_rate'])} per KOL\n"
            f"Spots remaining: {remaining}/{c['kol_count']}\n"
            f"Deadline: {str(c['deadline'])[:16]}"
        )
        if c.get("target_url"):
            text += f"\nTarget: {c['target_url']}"
        if c.get("talking_points"):
            text += f"\n\nKey points:\n{c['talking_points']}"
        if c.get("hashtags"):
            text += f"\nHashtags: {c['hashtags']}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Accept", callback_data=f"accept_campaign:{c['id']}")]
        ])
        await update.message.reply_text(text, reply_markup=keyboard)


async def accept_campaign_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Accept Campaign button press (from channel or /campaigns)."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    kol = get_kol(user.id)
    if not kol:
        # Send DM if from channel
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="You need to register as a KOL first. Use /start to register.",
            )
        except Exception:
            pass
        return

    campaign_id = int(query.data.split(":")[1])

    try:
        result = accept_campaign(campaign_id, user.id)
    except AcceptanceError as e:
        # Try to reply in DM
        try:
            await context.bot.send_message(chat_id=user.id, text=str(e))
        except Exception:
            pass
        return

    campaign = get_campaign(campaign_id)
    remaining = result["kol_count"] - result["accepted_count"]

    # Send confirmation DM to KOL
    try:
        msg = (
            f"You accepted Campaign #{campaign_id}: {campaign['project_name']}!\n\n"
            f"Service: {format_service_type(campaign['service_type'])}\n"
            f"Rate: {format_cents(campaign['per_kol_rate'])}\n"
            f"Deadline: {str(campaign['deadline'])[:16]}\n\n"
        )
        if campaign.get("target_url"):
            msg += f"Target: {campaign['target_url']}\n"
        if campaign.get("talking_points"):
            msg += f"Talking points: {campaign['talking_points']}\n"
        if campaign.get("hashtags"):
            msg += f"Hashtags: {campaign['hashtags']}\n"
        if campaign.get("mentions"):
            msg += f"Mentions: {campaign['mentions']}\n"
        msg += "\nWhen done, use /submit to submit your tweet URL."

        await context.bot.send_message(chat_id=user.id, text=msg)
    except Exception as e:
        logger.warning("Could not DM KOL %s: %s", user.id, e)

    # Update channel announcement if it exists
    if campaign and campaign.get("announcement_message_id"):
        from services.announcement_service import update_announcement
        await update_announcement(context.bot, get_campaign(campaign_id))


def get_handlers():
    return [
        CommandHandler("campaigns", browse_campaigns),
        CallbackQueryHandler(accept_campaign_callback, pattern=r"^accept_campaign:\d+$"),
    ]
