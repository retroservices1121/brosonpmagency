"""BrosKOLs Telegram Bot — bootstrap and handler registration."""
import logging

from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_IDS, ANNOUNCEMENT_CHANNEL_ID
from db.migrations import run_migrations
from handlers import registration, campaign_create, campaign_browse, campaign_submit, campaign_dashboard, admin, pricing, kol_list
from handlers.common import is_admin, notify_admins
from services.campaign_service import expire_campaigns
from services.integrity_service import run_integrity_check

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Role-based help."""
    user = update.effective_user
    lines = [
        "BrosOnPM Agency Bot\n",
        "/start — Register as KOL or Customer",
        "/help — Show this message",
        "/myid — Show your Telegram ID",
        "/kols — Browse KOL roster",
        "/cancel — Cancel current operation",
    ]

    from db.customer_repo import get_customer
    from db.kol_repo import get_kol

    if get_customer(user.id):
        lines.append("\nCustomer commands:")
        lines.append("/newcampaign — Create a new campaign")
        lines.append("/mycampaigns — View your campaigns")

    if get_kol(user.id):
        lines.append("\nKOL commands:")
        lines.append("/campaigns — Browse available campaigns")
        lines.append("/mywork — View your accepted work")
        lines.append("/submit — Submit proof of work")

    if is_admin(user):
        lines.append("\nAdmin commands:")
        lines.append("/admin — Admin panel")
        lines.append("/pricing — Manage service pricing")
        lines.append("/bulkverify — Verify all KOLs via X API")
        lines.append("/integrity — Check for deleted proof-of-work tweets")
        lines.append("/export — Export data as CSV")

    await update.message.reply_text("\n".join(lines))


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user their Telegram numeric ID (useful for setting ADMIN_TELEGRAM_IDS)."""
    user = update.effective_user
    await update.message.reply_text(
        f"Your Telegram ID: `{user.id}`\n\n"
        "Add this to ADMIN_TELEGRAM_IDS in .env to get admin access.",
        parse_mode="Markdown",
    )


async def post_init(application):
    """Set bot commands for the menu button."""
    commands = [
        BotCommand("start", "Register as KOL or Customer"),
        BotCommand("help", "Show available commands"),
        BotCommand("myid", "Show your Telegram ID"),
        BotCommand("newcampaign", "Create a campaign (Customer)"),
        BotCommand("mycampaigns", "View your campaigns (Customer)"),
        BotCommand("campaigns", "Browse campaigns (KOL)"),
        BotCommand("mywork", "View accepted work (KOL)"),
        BotCommand("submit", "Submit proof of work (KOL)"),
        BotCommand("admin", "Admin panel"),
        BotCommand("kols", "Browse KOL roster"),
        BotCommand("pricing", "Manage pricing (Admin)"),
        BotCommand("bulkverify", "Verify all KOLs via X (Admin)"),
        BotCommand("integrity", "Check for deleted tweets (Admin)"),
        BotCommand("export", "Export data (Admin)"),
        BotCommand("cancel", "Cancel current operation"),
    ]
    await application.bot.set_my_commands(commands)


def expire_campaigns_job(context: ContextTypes.DEFAULT_TYPE):
    """Hourly job to expire campaigns past their deadline."""
    count = expire_campaigns()
    if count:
        logger.info("Expired %d campaign(s)", count)


async def integrity_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Daily job to check verified tweets for deletions."""
    logger.info("Running daily tweet integrity check...")
    result = await run_integrity_check()
    logger.info(
        "Integrity check done: %d checked, %d ok, %d deleted, %d errors",
        result["total"], result["ok"], result["deleted"], result["errors"],
    )
    if result["bans"]:
        lines = ["Tweet Integrity Alert — KOLs Banned\n─────────────────────────────"]
        for b in result["bans"]:
            paid_flag = " [PAID]" if b["paid"] else ""
            lines.append(
                f"- {b['kol_name']} (@{b['x_account']}){paid_flag}\n"
                f"  Campaign #{b['campaign_id']}: {b['project_name']}\n"
                f"  Tweet: {b['tweet_url']}"
            )
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + f"\n\n... ({len(result['bans'])} total bans)"
        await notify_admins(context.bot, text)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Create a .env file with your bot token (see .env.example)."
        )

    # Startup warnings for missing config
    if not ADMIN_TELEGRAM_IDS:
        logger.warning(
            "ADMIN_TELEGRAM_IDS not set! Admin DMs will fall back to @username. "
            "Use /myid in the bot to get your numeric ID, then add it to .env."
        )
    if not ANNOUNCEMENT_CHANNEL_ID:
        logger.warning(
            "ANNOUNCEMENT_CHANNEL_ID not set! Campaign announcements will be skipped. "
            "Add the channel's numeric ID to .env (e.g. -1001234567890)."
        )

    run_migrations()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # --- Conversation handlers (order matters: first match wins) ---
    app.add_handler(registration.get_conversation_handler())
    app.add_handler(campaign_create.get_conversation_handler())
    app.add_handler(campaign_submit.get_conversation_handler())
    app.add_handler(pricing.get_conversation_handler())

    # --- Standalone command handlers ---
    for handler in campaign_browse.get_handlers():
        app.add_handler(handler)
    for handler in campaign_dashboard.get_handlers():
        app.add_handler(handler)
    for handler in admin.get_handlers():
        app.add_handler(handler)
    for handler in kol_list.get_handlers():
        app.add_handler(handler)

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid_command))

    # --- Scheduled jobs ---
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(expire_campaigns_job, interval=3600, first=60)
        logger.info("Scheduled hourly campaign expiration check")
        job_queue.run_repeating(integrity_check_job, interval=86400, first=300)
        logger.info("Scheduled daily tweet integrity check")

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
