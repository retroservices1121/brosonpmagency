"""Post campaign announcements to the Telegram channel."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

from config import ANNOUNCEMENT_CHANNEL_ID
from db.tier_repo import get_all_tiers
from db.campaign_repo import set_announcement_message_id
from handlers.common import format_cents

logger = logging.getLogger(__name__)


async def announce_campaign(bot: Bot, campaign: dict):
    """Post a campaign announcement to the channel with an Accept button."""
    if not ANNOUNCEMENT_CHANNEL_ID:
        logger.info("No ANNOUNCEMENT_CHANNEL_ID set, skipping announcement for campaign #%d", campaign["id"])
        return

    tiers = get_all_tiers()
    tier = tiers.get(campaign["service_type"], (campaign["service_type"],))
    tier_name = tier[0]
    remaining = campaign["kol_count"] - campaign["accepted_count"]

    text = (
        f"NEW CAMPAIGN #{campaign['id']}\n\n"
        f"Project: {campaign['project_name']}\n"
        f"Service: {tier_name}\n"
        f"Rate: {format_cents(campaign['per_kol_rate'])} per KOL\n"
        f"Spots: {remaining} available\n"
        f"Deadline: {str(campaign['deadline'])[:16]}\n"
    )
    if campaign.get("target_url"):
        text += f"\nTarget: {campaign['target_url']}"
    if campaign.get("talking_points"):
        text += f"\n\nKey points:\n{campaign['talking_points']}"
    if campaign.get("hashtags"):
        text += f"\n\nHashtags: {campaign['hashtags']}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Accept Campaign", callback_data=f"accept_campaign:{campaign['id']}")]
    ])

    try:
        msg = await bot.send_message(
            chat_id=ANNOUNCEMENT_CHANNEL_ID,
            text=text,
            reply_markup=keyboard,
        )
        set_announcement_message_id(campaign["id"], str(msg.message_id))
        logger.info("Announced campaign #%d in channel", campaign["id"])
    except Exception as e:
        logger.error("Failed to announce campaign #%d: %s", campaign["id"], e)


async def update_announcement(bot: Bot, campaign: dict):
    """Edit the channel announcement to reflect updated slot count or status."""
    if not ANNOUNCEMENT_CHANNEL_ID or not campaign.get("announcement_message_id"):
        return

    tiers = get_all_tiers()
    tier = tiers.get(campaign["service_type"], (campaign["service_type"],))
    tier_name = tier[0]
    remaining = campaign["kol_count"] - campaign["accepted_count"]

    if campaign["status"] in ("filled", "completed", "expired", "cancelled"):
        status_line = f"\n\nStatus: {campaign['status'].upper()} — No longer accepting KOLs"
        keyboard = None
    else:
        status_line = ""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Accept Campaign", callback_data=f"accept_campaign:{campaign['id']}")]
        ])

    text = (
        f"CAMPAIGN #{campaign['id']}\n\n"
        f"Project: {campaign['project_name']}\n"
        f"Service: {tier_name}\n"
        f"Rate: {format_cents(campaign['per_kol_rate'])} per KOL\n"
        f"Spots: {remaining} available\n"
        f"Deadline: {str(campaign['deadline'])[:16]}"
        f"{status_line}"
    )

    try:
        await bot.edit_message_text(
            chat_id=ANNOUNCEMENT_CHANNEL_ID,
            message_id=int(campaign["announcement_message_id"]),
            text=text,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("Could not update announcement for campaign #%d: %s", campaign["id"], e)
