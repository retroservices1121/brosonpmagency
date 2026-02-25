"""Admin pricing management — /pricing command."""
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

from db.tier_repo import get_all_tiers, get_tier, update_tier
from handlers.common import require_admin, is_admin, format_cents

logger = logging.getLogger(__name__)

SHOW_TIERS, EDIT_RATE, EDIT_MIN, EDIT_MAX = range(4)


@require_admin
async def pricing_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show all service tiers with Edit buttons."""
    tiers = get_all_tiers()
    if not tiers:
        await update.message.reply_text("No service tiers configured.")
        return ConversationHandler.END

    lines = ["Current Pricing\n─────────────────"]
    buttons = []
    for key, (name, rate, mn, mx) in tiers.items():
        lines.append(f"\n{name}: {format_cents(rate)}/KOL (min {mn}, max {mx})")
        buttons.append([InlineKeyboardButton(f"Edit {name}", callback_data=f"pr_edit:{key}")])

    buttons.append([InlineKeyboardButton("Done", callback_data="pr_done")])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SHOW_TIERS


async def tier_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "pr_done":
        await query.edit_message_text("Pricing management closed.")
        return ConversationHandler.END

    key = query.data.split(":")[1]
    tier = get_tier(key)
    if not tier:
        await query.edit_message_text("Tier not found.")
        return ConversationHandler.END

    context.user_data["edit_tier_key"] = key
    context.user_data["edit_tier"] = tier

    await query.edit_message_text(
        f"Editing: {tier['display_name']}\n\n"
        f"Current rate: {format_cents(tier['per_kol_rate'])}/KOL\n"
        f"Current min KOLs: {tier['min_kols']}\n"
        f"Current max KOLs: {tier['max_kols']}\n\n"
        f"Enter new rate in dollars (e.g. 25 for $25.00), or /skip to keep current:"
    )
    return EDIT_RATE


async def rate_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        dollars = float(text)
        if dollars <= 0:
            raise ValueError
        context.user_data["new_rate"] = int(dollars * 100)
    except ValueError:
        await update.message.reply_text("Please enter a valid dollar amount (e.g. 25 or 12.50):")
        return EDIT_RATE

    tier = context.user_data["edit_tier"]
    await update.message.reply_text(
        f"New rate: {format_cents(context.user_data['new_rate'])}/KOL\n\n"
        f"Enter new minimum KOLs (currently {tier['min_kols']}), or /skip:"
    )
    return EDIT_MIN


async def skip_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_rate"] = None
    tier = context.user_data["edit_tier"]
    await update.message.reply_text(
        f"Rate unchanged.\n\n"
        f"Enter new minimum KOLs (currently {tier['min_kols']}), or /skip:"
    )
    return EDIT_MIN


async def min_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        mn = int(text)
        if mn < 1:
            raise ValueError
        context.user_data["new_min"] = mn
    except ValueError:
        await update.message.reply_text("Please enter a positive number:")
        return EDIT_MIN

    tier = context.user_data["edit_tier"]
    await update.message.reply_text(
        f"New min: {mn}\n\n"
        f"Enter new maximum KOLs (currently {tier['max_kols']}), or /skip:"
    )
    return EDIT_MAX


async def skip_min(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_min"] = None
    tier = context.user_data["edit_tier"]
    await update.message.reply_text(
        f"Min unchanged.\n\n"
        f"Enter new maximum KOLs (currently {tier['max_kols']}), or /skip:"
    )
    return EDIT_MAX


async def max_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        mx = int(text)
        if mx < 1:
            raise ValueError
        context.user_data["new_max"] = mx
    except ValueError:
        await update.message.reply_text("Please enter a positive number:")
        return EDIT_MAX

    return await _save_tier(update, context)


async def skip_max(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_max"] = None
    return await _save_tier(update, context)


async def _save_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = context.user_data["edit_tier_key"]
    new_rate = context.user_data.get("new_rate")
    new_min = context.user_data.get("new_min")
    new_max = context.user_data.get("new_max")

    update_tier(key, per_kol_rate=new_rate, min_kols=new_min, max_kols=new_max)

    # Show updated tier
    tier = get_tier(key)
    await update.message.reply_text(
        f"Updated: {tier['display_name']}\n\n"
        f"Rate: {format_cents(tier['per_kol_rate'])}/KOL\n"
        f"Min KOLs: {tier['min_kols']}\n"
        f"Max KOLs: {tier['max_kols']}\n\n"
        "Use /pricing to edit another tier."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Pricing edit cancelled.")
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("pricing", pricing_start)],
        states={
            SHOW_TIERS: [CallbackQueryHandler(tier_selected, pattern=r"^pr_")],
            EDIT_RATE: [
                CommandHandler("skip", skip_rate),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rate_received),
            ],
            EDIT_MIN: [
                CommandHandler("skip", skip_min),
                MessageHandler(filters.TEXT & ~filters.COMMAND, min_received),
            ],
            EDIT_MAX: [
                CommandHandler("skip", skip_max),
                MessageHandler(filters.TEXT & ~filters.COMMAND, max_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
