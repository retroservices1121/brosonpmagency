"""Dashboard views — /mycampaigns (customer) and /mywork (KOL)."""
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from db.kol_repo import get_kol
from db.customer_repo import get_customer
from db.campaign_repo import get_campaigns_by_customer
from db.acceptance_repo import get_acceptances_for_kol
from handlers.common import format_cents, format_service_type, format_campaign_summary, send_campaign_media

logger = logging.getLogger(__name__)


async def my_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show customer's campaigns."""
    user = update.effective_user
    cust = get_customer(user.id)
    if not cust:
        await update.message.reply_text(
            "You need to register as a Customer first. Use /start to register."
        )
        return

    campaigns = get_campaigns_by_customer(user.id)
    if not campaigns:
        await update.message.reply_text(
            "You haven't created any campaigns yet. Use /newcampaign to create one."
        )
        return

    lines = ["Your Campaigns\n─────────────────"]
    for c in campaigns:
        lines.append("")
        lines.append(format_campaign_summary(c))

    # Split into chunks if too long
    text = "\n".join(lines)
    if len(text) > 4000:
        # Send in chunks
        for i in range(0, len(lines), 20):
            chunk = "\n".join(lines[i:i+20])
            if chunk.strip():
                await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(text)


async def my_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show KOL's accepted campaigns and their status."""
    user = update.effective_user
    kol = get_kol(user.id)
    if not kol:
        await update.message.reply_text(
            "You need to register as a KOL first. Use /start to register."
        )
        return

    acceptances = get_acceptances_for_kol(user.id)
    if not acceptances:
        await update.message.reply_text(
            "You haven't accepted any campaigns yet. Use /campaigns to browse."
        )
        return

    lines = ["Your Work\n─────────────────"]
    for a in acceptances:
        status_emoji = {
            "accepted": "[PENDING]",
            "submitted": "[SUBMITTED]",
            "verified": "[VERIFIED]",
            "rejected": "[REJECTED]",
            "expired": "[EXPIRED]",
        }.get(a["status"], a["status"])

        lines.append("")
        entry = (
            f"Campaign #{a['campaign_id']}: {a['project_name']}\n"
            f"Service: {format_service_type(a['service_type'])}\n"
            f"Your status: {status_emoji}\n"
            f"Campaign status: {a['campaign_status']}\n"
            f"Deadline: {str(a['deadline'])[:16]}"
        )
        if a.get("target_url"):
            entry += f"\nTarget: {a['target_url']}"
        if a.get("talking_points"):
            entry += f"\nTalking points: {a['talking_points']}"
        if a.get("hashtags"):
            entry += f"\nHashtags: {a['hashtags']}"
        if a.get("mentions"):
            entry += f"\nMentions: {a['mentions']}"
        if a.get("submission_tweet_url"):
            entry += f"\nSubmitted: {a['submission_tweet_url']}"
        lines.append(entry)

    text = "\n".join(lines)
    if len(text) > 4000:
        for i in range(0, len(lines), 20):
            chunk = "\n".join(lines[i:i+20])
            if chunk.strip():
                await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(text)

    # Send any attached media for active campaigns
    for a in acceptances:
        if a.get("media_file_id") and a["status"] in ("accepted", "submitted"):
            await send_campaign_media(
                context.bot, update.effective_chat.id, a["media_file_id"],
                caption=f"Media for Campaign #{a['campaign_id']}"
            )


def get_handlers():
    return [
        CommandHandler("mycampaigns", my_campaigns),
        CommandHandler("mywork", my_work),
    ]
