import csv
import io
import logging
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS, ADMIN_USERNAME
from db.kol_repo import get_kol
from db.customer_repo import get_customer
from db.tier_repo import get_all_tiers

logger = logging.getLogger(__name__)


def is_admin(user) -> bool:
    """Check if a Telegram user is an admin."""
    if user.id in ADMIN_TELEGRAM_IDS:
        return True
    if user.username and user.username.lower() == ADMIN_USERNAME.lower():
        return True
    return False


def require_admin(func):
    """Decorator that restricts a handler to admins only."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not is_admin(user):
            await update.effective_message.reply_text("This command is for admins only.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def require_customer(func):
    """Decorator that restricts a handler to registered customers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        cust = get_customer(user.id)
        if not cust:
            await update.effective_message.reply_text(
                "You need to register as a Customer first. Use /start to register."
            )
            return
        context.user_data["customer"] = cust
        return await func(update, context, *args, **kwargs)
    return wrapper


def require_kol(func):
    """Decorator that restricts a handler to registered KOLs."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        kol = get_kol(user.id)
        if not kol:
            await update.effective_message.reply_text(
                "You need to register as a KOL first. Use /start to register."
            )
            return
        context.user_data["kol"] = kol
        return await func(update, context, *args, **kwargs)
    return wrapper


async def notify_admins(bot, text: str, reply_markup=None):
    """Send a message to all admins. Tries ADMIN_TELEGRAM_IDS first, falls back to @ADMIN_USERNAME."""
    sent = False
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, reply_markup=reply_markup)
            sent = True
        except Exception as e:
            logger.warning("Could not notify admin %s: %s", admin_id, e)

    if not sent and ADMIN_USERNAME:
        try:
            await bot.send_message(chat_id=f"@{ADMIN_USERNAME}", text=text, reply_markup=reply_markup)
            sent = True
        except Exception as e:
            logger.warning("Could not notify admin @%s: %s", ADMIN_USERNAME, e)

    if not sent:
        logger.error("No admins could be notified! Set ADMIN_TELEGRAM_IDS in .env")


def format_cents(cents: int) -> str:
    """Format cents as dollar string: 1500 → '$15.00'."""
    return f"${cents / 100:.2f}"


def format_service_type(service_type: str) -> str:
    """Get display name for a service type."""
    tiers = get_all_tiers()
    tier = tiers.get(service_type)
    return tier[0] if tier else service_type


def format_campaign_summary(c: dict) -> str:
    """Format a campaign dict into a readable summary."""
    tier_name = format_service_type(c["service_type"])
    remaining = c["kol_count"] - c["accepted_count"]
    lines = [
        f"Campaign #{c['id']}: {c['project_name']}",
        f"Service: {tier_name}",
        f"Rate: {format_cents(c['per_kol_rate'])} per KOL",
        f"Slots: {remaining}/{c['kol_count']} remaining",
        f"Status: {c['status']}",
        f"Deadline: {str(c['deadline'])[:16]}",
    ]
    if c.get("target_url"):
        lines.append(f"Target: {c['target_url']}")
    return "\n".join(lines)


def export_csv_data(table="kols"):
    """Generate CSV string for KOLs or Customers."""
    from db.connection import get_conn
    conn = get_conn()
    cur = conn.cursor()

    if table == "customers":
        q = "SELECT name, project_x_account, telegram_handle, telegram_id, registered_at FROM customers"
    else:
        q = "SELECT name, x_account, wallet_address, telegram_handle, telegram_id, registered_at FROM kols"

    cur.execute(q)
    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()
