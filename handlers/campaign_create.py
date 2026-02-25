"""Campaign creation conversation handler — /newcampaign.

11-step flow: service → project name → target URL → talking points →
hashtags → mentions → reference URL → media → KOL count → deadline → confirm.
"""
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    SERVICES_REQUIRING_TARGET,
    SERVICES_REQUIRING_TALKING_POINTS,
    ADMIN_TELEGRAM_IDS,
    PAYMENT_WALLET_ADDRESS,
    PAYMENT_NETWORK,
)
from db.tier_repo import get_all_tiers
from handlers.common import require_customer, format_cents, format_service_type
from services.campaign_service import create_campaign, calculate_pricing

logger = logging.getLogger(__name__)

(
    SELECT_SERVICE,
    PROJECT_NAME,
    TARGET_URL,
    TALKING_POINTS,
    HASHTAGS,
    MENTIONS,
    REFERENCE_URL,
    MEDIA,
    KOL_COUNT,
    DEADLINE,
    CONFIRM,
) = range(11)


@require_customer
async def newcampaign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: show service type selector."""
    context.user_data["campaign"] = {}
    tiers = get_all_tiers()
    buttons = []
    for key, (name, rate, _min, _max) in tiers.items():
        buttons.append([InlineKeyboardButton(
            f"{name} — {format_cents(rate)}/KOL",
            callback_data=f"cc_svc:{key}",
        )])

    await update.message.reply_text(
        "Let's create a new campaign!\n\nSelect the service type:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECT_SERVICE


async def service_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    service_type = query.data.split(":")[1]
    context.user_data["campaign"]["service_type"] = service_type

    tiers = get_all_tiers()
    tier = tiers[service_type]
    await query.edit_message_text(
        f"Service: {tier[0]} ({format_cents(tier[1])}/KOL)\n\n"
        "What is your project name?"
    )
    return PROJECT_NAME


async def project_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["project_name"] = update.message.text.strip()
    service_type = context.user_data["campaign"]["service_type"]

    if service_type in SERVICES_REQUIRING_TARGET:
        await update.message.reply_text(
            "Paste the tweet URL that KOLs should retweet/quote:"
        )
        return TARGET_URL
    else:
        # For original content, target_url is optional
        context.user_data["campaign"]["target_url"] = None
        await update.message.reply_text(
            "What key talking points should KOLs cover in their posts?\n"
            "(Write them out, or send /skip)"
        )
        return TALKING_POINTS


async def target_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    context.user_data["campaign"]["target_url"] = url
    service_type = context.user_data["campaign"]["service_type"]

    if service_type in SERVICES_REQUIRING_TALKING_POINTS:
        await update.message.reply_text(
            "What key talking points should KOLs cover?\n"
            "(Write them out, or send /skip)"
        )
        return TALKING_POINTS
    else:
        # Retweet / Like+RT don't need talking points
        context.user_data["campaign"]["talking_points"] = None
        await update.message.reply_text(
            "Any hashtags to include? (comma-separated, or /skip)"
        )
        return HASHTAGS


async def talking_points_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["talking_points"] = update.message.text.strip()
    await update.message.reply_text(
        "Any hashtags to include? (comma-separated, or /skip)"
    )
    return HASHTAGS


async def skip_talking_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["talking_points"] = None
    await update.message.reply_text(
        "Any hashtags to include? (comma-separated, or /skip)"
    )
    return HASHTAGS


async def hashtags_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["hashtags"] = update.message.text.strip()
    await update.message.reply_text(
        "Any @mentions to include? (comma-separated, or /skip)"
    )
    return MENTIONS


async def skip_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["hashtags"] = None
    await update.message.reply_text(
        "Any @mentions to include? (comma-separated, or /skip)"
    )
    return MENTIONS


async def mentions_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["mentions"] = update.message.text.strip()
    await update.message.reply_text(
        "Any reference tweet URL for KOLs to look at? (or /skip)"
    )
    return REFERENCE_URL


async def skip_mentions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["mentions"] = None
    await update.message.reply_text(
        "Any reference tweet URL for KOLs to look at? (or /skip)"
    )
    return REFERENCE_URL


async def reference_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["reference_tweet_url"] = update.message.text.strip()
    await update.message.reply_text(
        "Upload an image or video for KOLs to use (or /skip)"
    )
    return MEDIA


async def skip_reference_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["reference_tweet_url"] = None
    await update.message.reply_text(
        "Upload an image or video for KOLs to use (or /skip)"
    )
    return MEDIA


async def media_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        file_id = update.message.video.file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        file_id = None
    context.user_data["campaign"]["media_file_id"] = file_id

    service_type = context.user_data["campaign"]["service_type"]
    tiers = get_all_tiers()
    tier = tiers[service_type]
    await update.message.reply_text(
        f"How many KOLs do you want? (min: {tier[2]}, max: {tier[3]})"
    )
    return KOL_COUNT


async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["campaign"]["media_file_id"] = None
    service_type = context.user_data["campaign"]["service_type"]
    tiers = get_all_tiers()
    tier = tiers[service_type]
    await update.message.reply_text(
        f"How many KOLs do you want? (min: {tier[2]}, max: {tier[3]})"
    )
    return KOL_COUNT


async def kol_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    service_type = context.user_data["campaign"]["service_type"]
    tiers = get_all_tiers()
    tier = tiers[service_type]
    min_kols, max_kols = tier[2], tier[3]

    try:
        count = int(text)
    except ValueError:
        await update.message.reply_text(f"Please enter a number between {min_kols} and {max_kols}.")
        return KOL_COUNT

    if count < min_kols or count > max_kols:
        await update.message.reply_text(f"Must be between {min_kols} and {max_kols}. Try again.")
        return KOL_COUNT

    context.user_data["campaign"]["kol_count"] = count
    await update.message.reply_text(
        "How many days until the deadline? (1-30)"
    )
    return DEADLINE


async def deadline_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        days = int(text)
    except ValueError:
        await update.message.reply_text("Please enter a number between 1 and 30.")
        return DEADLINE

    if days < 1 or days > 30:
        await update.message.reply_text("Must be between 1 and 30 days. Try again.")
        return DEADLINE

    deadline = datetime.utcnow() + timedelta(days=days)
    context.user_data["campaign"]["deadline"] = deadline.isoformat()

    # Show summary
    c = context.user_data["campaign"]
    pricing = calculate_pricing(c["service_type"], c["kol_count"])
    tier_name = format_service_type(c["service_type"])

    summary = (
        "Campaign Summary\n"
        "─────────────────\n"
        f"Project: {c['project_name']}\n"
        f"Service: {tier_name}\n"
        f"KOLs: {c['kol_count']}\n"
        f"Rate: {format_cents(pricing['per_kol_rate'])} per KOL\n"
        f"Platform fee (15%): {format_cents(pricing['platform_fee'])}\n"
        f"Total cost: {format_cents(pricing['total_cost'])}\n"
        f"Deadline: {deadline.strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    if c.get("target_url"):
        summary += f"Target URL: {c['target_url']}\n"
    if c.get("talking_points"):
        summary += f"Talking points: {c['talking_points']}\n"
    if c.get("hashtags"):
        summary += f"Hashtags: {c['hashtags']}\n"
    if c.get("mentions"):
        summary += f"Mentions: {c['mentions']}\n"

    summary += "\nConfirm this campaign?"

    await update.message.reply_text(
        summary,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Confirm", callback_data="cc_confirm"),
                InlineKeyboardButton("Cancel", callback_data="cc_cancel"),
            ]
        ]),
    )
    return CONFIRM


async def confirm_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cc_cancel":
        await query.edit_message_text("Campaign creation cancelled.")
        return ConversationHandler.END

    user = query.from_user
    c = context.user_data["campaign"]
    c["customer_telegram_id"] = user.id

    campaign_id = create_campaign(c)
    pricing = calculate_pricing(c["service_type"], c["kol_count"])

    payment_msg = (
        f"Campaign #{campaign_id} created!\n\n"
        f"Status: Pending Payment\n"
        f"Total: {format_cents(pricing['total_cost'])} USDC\n\n"
    )
    if PAYMENT_WALLET_ADDRESS:
        payment_msg += (
            f"Please send exactly {format_cents(pricing['total_cost'])} USDC to:\n\n"
            f"`{PAYMENT_WALLET_ADDRESS}`\n"
            f"Network: {PAYMENT_NETWORK}\n\n"
            "Once payment is received, an admin will activate your campaign.\n"
            "You'll be notified when it goes live."
        )
    else:
        payment_msg += (
            "An admin will reach out with payment details and activate the campaign.\n"
            "You'll be notified when it goes live."
        )

    await query.edit_message_text(payment_msg, parse_mode="Markdown")

    # Notify admins with inline confirm button
    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Confirm Payment", callback_data=f"adm:pay:{campaign_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"adm:cancel:{campaign_id}"),
        ]
    ])
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"New campaign #{campaign_id} awaiting payment!\n\n"
                    f"Customer: {user.first_name} (ID: {user.id})\n"
                    f"Project: {c['project_name']}\n"
                    f"Service: {format_service_type(c['service_type'])}\n"
                    f"KOLs: {c['kol_count']}\n"
                    f"Total: {format_cents(pricing['total_cost'])} USDC\n\n"
                    "Confirm once payment is received:"
                ),
                reply_markup=admin_keyboard,
            )
        except Exception as e:
            logger.warning("Could not notify admin %s: %s", admin_id, e)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Campaign creation cancelled.")
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    skip_cmd = CommandHandler("skip", None)  # placeholder, replaced per-state

    return ConversationHandler(
        entry_points=[CommandHandler("newcampaign", newcampaign)],
        states={
            SELECT_SERVICE: [CallbackQueryHandler(service_selected, pattern="^cc_svc:")],
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name_received)],
            TARGET_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_url_received)],
            TALKING_POINTS: [
                CommandHandler("skip", skip_talking_points),
                MessageHandler(filters.TEXT & ~filters.COMMAND, talking_points_received),
            ],
            HASHTAGS: [
                CommandHandler("skip", skip_hashtags),
                MessageHandler(filters.TEXT & ~filters.COMMAND, hashtags_received),
            ],
            MENTIONS: [
                CommandHandler("skip", skip_mentions),
                MessageHandler(filters.TEXT & ~filters.COMMAND, mentions_received),
            ],
            REFERENCE_URL: [
                CommandHandler("skip", skip_reference_url),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reference_url_received),
            ],
            MEDIA: [
                CommandHandler("skip", skip_media),
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, media_received),
            ],
            KOL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, kol_count_received)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deadline_received)],
            CONFIRM: [CallbackQueryHandler(confirm_campaign, pattern="^cc_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
