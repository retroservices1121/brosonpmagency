"""Admin panel — /admin, payment confirmation, manual verification, /export."""
import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from db.campaign_repo import get_campaign, get_campaigns_by_status, get_all_campaigns
from db.acceptance_repo import get_pending_verifications, get_acceptances_for_campaign, get_unpaid_verified, mark_paid, get_acceptance_by_id
from handlers.common import (
    is_admin,
    require_admin,
    format_cents,
    format_service_type,
    format_campaign_summary,
    export_csv_data,
)
from services.campaign_service import activate_campaign, cancel_campaign
from services.announcement_service import announce_campaign
from services.verification_service import manually_verify, manually_reject

logger = logging.getLogger(__name__)


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with action buttons."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Pending Payments", callback_data="adm:pending")],
        [InlineKeyboardButton("Pending Payouts", callback_data="adm:payouts")],
        [InlineKeyboardButton("Campaign Overview", callback_data="adm:overview")],
        [InlineKeyboardButton("Manual Verifications", callback_data="adm:verify")],
    ])
    await update.message.reply_text("Admin Panel", reply_markup=keyboard)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button presses."""
    query = update.callback_query
    user = query.from_user
    if not is_admin(user):
        await query.answer("Admins only.", show_alert=True)
        return
    await query.answer()

    action = query.data

    if action == "adm:pending":
        await _show_pending_payments(query, context)

    elif action == "adm:payouts":
        await _show_pending_payouts(query, context)

    elif action == "adm:overview":
        await _show_overview(query)

    elif action == "adm:verify":
        await _show_pending_verifications(query, context)

    elif action.startswith("adm:pay:"):
        campaign_id = int(action.split(":")[2])
        await _confirm_payment(query, context, campaign_id)

    elif action.startswith("adm:mark_paid:"):
        acceptance_id = int(action.split(":")[2])
        await _mark_kol_paid(query, context, acceptance_id)

    elif action.startswith("adm:v_approve:"):
        acceptance_id = int(action.split(":")[2])
        await _approve_verification(query, context, acceptance_id)

    elif action.startswith("adm:v_reject:"):
        acceptance_id = int(action.split(":")[2])
        await _reject_verification(query, context, acceptance_id)

    elif action.startswith("adm:cancel:"):
        campaign_id = int(action.split(":")[2])
        await _cancel_campaign(query, context, campaign_id)


async def _show_pending_payments(query, context):
    campaigns = get_campaigns_by_status("pending_payment")
    if not campaigns:
        await query.edit_message_text("No campaigns pending payment.")
        return

    for c in campaigns:
        text = (
            f"Campaign #{c['id']}: {c['project_name']}\n"
            f"Service: {format_service_type(c['service_type'])}\n"
            f"KOLs: {c['kol_count']}\n"
            f"Total: {format_cents(c['total_cost'])}\n"
            f"Created: {str(c['created_at'])[:16]}\n"
            f"Customer ID: {c['customer_telegram_id']}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Confirm Payment", callback_data=f"adm:pay:{c['id']}"),
                InlineKeyboardButton("Cancel", callback_data=f"adm:cancel:{c['id']}"),
            ]
        ])
        await query.message.reply_text(text, reply_markup=keyboard)

    await query.edit_message_text(f"Found {len(campaigns)} campaign(s) pending payment (shown above).")


async def _show_overview(query):
    campaigns = get_all_campaigns()
    if not campaigns:
        await query.edit_message_text("No campaigns yet.")
        return

    lines = [f"All Campaigns ({len(campaigns)} total)\n─────────────────"]
    for c in campaigns:
        lines.append("")
        lines.append(format_campaign_summary(c))

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (truncated)"
    await query.edit_message_text(text)


async def _show_pending_verifications(query, context):
    subs = get_pending_verifications()
    if not subs:
        await query.edit_message_text("No submissions pending manual review.")
        return

    for s in subs:
        text = (
            f"Submission #{s['id']}\n"
            f"Campaign #{s['campaign_id']}: {s['project_name']}\n"
            f"KOL: {s['kol_name']} (@{s['x_account']})\n"
            f"Service: {format_service_type(s['service_type'])}\n"
            f"Tweet: {s.get('submission_tweet_url', 'N/A')}\n"
            f"Submitted: {str(s.get('submitted_at', ''))[:16]}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Approve", callback_data=f"adm:v_approve:{s['id']}"),
                InlineKeyboardButton("Reject", callback_data=f"adm:v_reject:{s['id']}"),
            ]
        ])
        await query.message.reply_text(text, reply_markup=keyboard)

    await query.edit_message_text(f"Found {len(subs)} submission(s) pending review (shown above).")


async def _show_pending_payouts(query, context):
    unpaid = get_unpaid_verified()
    if not unpaid:
        await query.edit_message_text("No pending KOL payouts.")
        return

    for a in unpaid:
        text = (
            f"Payout — Submission #{a['id']}\n"
            f"Campaign #{a['campaign_id']}: {a['project_name']}\n"
            f"KOL: {a['kol_name']} (@{a['x_account']})\n"
            f"Service: {format_service_type(a['service_type'])}\n"
            f"Amount: {format_cents(a['per_kol_rate'])} USDC\n"
            f"Wallet: `{a['kol_wallet']}`"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Mark Paid", callback_data=f"adm:mark_paid:{a['id']}")]
        ])
        await query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    await query.edit_message_text(f"Found {len(unpaid)} pending payout(s) (shown above).")


async def _mark_kol_paid(query, context, acceptance_id):
    acceptance = get_acceptance_by_id(acceptance_id)
    if not acceptance:
        await query.edit_message_text(f"Acceptance #{acceptance_id} not found.")
        return

    mark_paid(acceptance_id)
    campaign = get_campaign(acceptance["campaign_id"])
    project_name = campaign["project_name"] if campaign else "Unknown"
    per_kol_rate = campaign["per_kol_rate"] if campaign else 0

    await query.edit_message_text(
        f"Submission #{acceptance_id} marked as PAID!\n"
        f"({format_cents(per_kol_rate)} USDC to KOL {acceptance['kol_telegram_id']})"
    )

    # Notify KOL
    try:
        await context.bot.send_message(
            chat_id=acceptance["kol_telegram_id"],
            text=(
                f"Payment sent!\n\n"
                f"Campaign #{acceptance['campaign_id']}: {project_name}\n"
                f"Amount: {format_cents(per_kol_rate)} USDC\n\n"
                "The payment has been sent to your registered wallet. "
                "Thank you for your work!"
            ),
        )
    except Exception as e:
        logger.warning("Could not notify KOL %s about payment: %s", acceptance["kol_telegram_id"], e)


async def _confirm_payment(query, context, campaign_id):
    campaign = activate_campaign(campaign_id)
    if not campaign:
        await query.edit_message_text(
            f"Could not activate campaign #{campaign_id}. It may already be active or not in pending_payment status."
        )
        return

    await query.edit_message_text(f"Campaign #{campaign_id} is now LIVE!")

    # Post to announcement channel
    await announce_campaign(context.bot, campaign)

    # Notify the customer
    try:
        await context.bot.send_message(
            chat_id=campaign["customer_telegram_id"],
            text=(
                f"Your campaign #{campaign_id} ({campaign['project_name']}) is now LIVE!\n\n"
                "KOLs can now accept and start working on it.\n"
                "Use /mycampaigns to track progress."
            ),
        )
    except Exception as e:
        logger.warning("Could not notify customer: %s", e)


async def _approve_verification(query, context, acceptance_id):
    if manually_verify(acceptance_id):
        await query.edit_message_text(f"Submission #{acceptance_id} verified!")
    else:
        await query.edit_message_text(f"Could not verify submission #{acceptance_id}.")


async def _reject_verification(query, context, acceptance_id):
    if manually_reject(acceptance_id):
        await query.edit_message_text(f"Submission #{acceptance_id} rejected.")
    else:
        await query.edit_message_text(f"Could not reject submission #{acceptance_id}.")


async def _cancel_campaign(query, context, campaign_id):
    if cancel_campaign(campaign_id):
        await query.edit_message_text(f"Campaign #{campaign_id} cancelled.")
    else:
        await query.edit_message_text(f"Could not cancel campaign #{campaign_id}.")


@require_admin
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export KOL and Customer data as CSV."""
    csv_kols = export_csv_data("kols")
    buf_kols = io.BytesIO(csv_kols.encode("utf-8"))
    buf_kols.name = "kols_export.csv"
    await update.message.reply_document(document=buf_kols, caption="KOLs registration export")

    csv_customers = export_csv_data("customers")
    buf_cust = io.BytesIO(csv_customers.encode("utf-8"))
    buf_cust.name = "customers_export.csv"
    await update.message.reply_document(document=buf_cust, caption="Customers registration export")


def get_handlers():
    return [
        CommandHandler("admin", admin_panel),
        CommandHandler("export", export),
        CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
    ]
