"""Admin panel — /admin, payment confirmation, manual verification, /export, /bulkverify."""
import asyncio
import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from db.campaign_repo import get_campaign, get_campaigns_by_status, get_all_campaigns
from db.acceptance_repo import get_pending_verifications, get_acceptances_for_campaign, get_unpaid_verified, mark_paid, get_acceptance_by_id
from db.kol_repo import get_all_kols, update_kol_verification
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
from services.integrity_service import run_integrity_check
from services import x_api

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
        try:
            await query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(text, reply_markup=keyboard)

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

    # Post to announcement channel
    channel_error = await announce_campaign(context.bot, campaign)

    if channel_error:
        await query.edit_message_text(
            f"Campaign #{campaign_id} is now LIVE!\n\n"
            f"Channel post failed: {channel_error}\n"
            "Make sure the bot is an admin of the channel."
        )
    else:
        await query.edit_message_text(
            f"Campaign #{campaign_id} is now LIVE!\n"
            "Announced in channel."
        )

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


@require_admin
async def bulk_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Look up all unverified KOLs on X and update their profiles."""
    kols = get_all_kols()
    unverified = [k for k in kols if not k.get("is_verified")]

    if not unverified:
        await update.message.reply_text("All KOLs are already verified!")
        return

    if not x_api.is_configured():
        await update.message.reply_text("X API is not configured. Cannot verify KOLs.")
        return

    if not await x_api.is_read_available():
        await update.message.reply_text("X API read access not available. Cannot verify KOLs.")
        return

    total = len(unverified)
    progress_msg = await update.message.reply_text(
        f"Starting bulk verification for {total} KOL(s)...\n"
        "This may take a while due to API rate limits (~9s per KOL).\n"
        "Other bot commands will continue to work normally."
    )

    # Run in background so the bot can process other commands
    chat_id = update.effective_chat.id
    context.application.create_task(
        _run_bulk_verify(context.bot, chat_id, progress_msg, unverified),
        update=update,
    )


async def _run_bulk_verify(bot, chat_id, progress_msg, unverified):
    """Background task for bulk KOL verification."""
    total = len(unverified)
    verified_count = 0
    failed = []

    for i, kol in enumerate(unverified):
        x_account = kol.get("x_account", "")
        if not x_account:
            failed.append(f"{kol['name']} — no X account")
            continue

        # Rate limit: ~9 seconds between calls (35 calls / 5 min = 1 per 8.6s)
        if i > 0:
            await asyncio.sleep(9)

        x_user = await x_api.get_user_by_username(x_account)
        if x_user:
            x_user_id = x_user["id"]
            followers = (x_user.get("public_metrics") or {}).get("followers_count", 0)
            update_kol_verification(kol["telegram_id"], x_user_id, followers, True)
            verified_count += 1
        else:
            failed.append(f"{kol['name']} (@{x_account}) — not found on X")

        # Update progress every 5 KOLs
        if (i + 1) % 5 == 0 or i == total - 1:
            try:
                await progress_msg.edit_text(
                    f"Bulk verification in progress... {i + 1}/{total}\n"
                    f"Verified: {verified_count} | Failed: {len(failed)}"
                )
            except Exception:
                pass

    lines = [f"Bulk verification complete: {verified_count}/{total} verified."]
    if failed:
        lines.append(f"\nFailed ({len(failed)}):")
        for f_msg in failed:
            lines.append(f"  - {f_msg}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + f"\n\n... ({len(failed)} total failures, list truncated)"

    await bot.send_message(chat_id=chat_id, text=text)


@require_admin
async def integrity_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check recently verified tweets for deletions and ban offenders."""
    if not x_api.is_configured():
        await update.message.reply_text("X API is not configured. Cannot run integrity check.")
        return

    if not await x_api.is_read_available():
        await update.message.reply_text("X API read access not available. Cannot run integrity check.")
        return

    progress_msg = await update.message.reply_text(
        "Starting tweet integrity check...\n"
        "Checking verified tweets from the last 10 days.\n"
        "This may take a while due to API rate limits (~9s per tweet)."
    )

    chat_id = update.effective_chat.id
    context.application.create_task(
        _run_integrity_check(context.bot, chat_id, progress_msg),
        update=update,
    )


async def _run_integrity_check(bot, chat_id, progress_msg):
    """Background task for tweet integrity check."""
    async def on_progress(checked, total):
        await progress_msg.edit_text(
            f"Integrity check in progress... {checked}/{total} tweets\n"
            "Checking for deleted proof-of-work tweets."
        )

    result = await run_integrity_check(progress_callback=on_progress)

    lines = [
        "Tweet Integrity Check Complete\n"
        "─────────────────────────────",
        f"Tweets checked: {result['total']}",
        f"Still live: {result['ok']}",
        f"Deleted: {result['deleted']}",
        f"API errors (skipped): {result['errors']}",
    ]

    if result["bans"]:
        lines.append(f"\nKOLs banned ({len(result['bans'])}):")
        for b in result["bans"]:
            paid_flag = " [PAID]" if b["paid"] else ""
            lines.append(
                f"  - {b['kol_name']} (@{b['x_account']}){paid_flag}\n"
                f"    Campaign #{b['campaign_id']}: {b['project_name']}"
            )
    else:
        lines.append("\nNo deleted tweets found. All clear!")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + f"\n\n... ({len(result['bans'])} total bans, list truncated)"

    await bot.send_message(chat_id=chat_id, text=text)


def get_handlers():
    return [
        CommandHandler("admin", admin_panel),
        CommandHandler("export", export),
        CommandHandler("bulkverify", bulk_verify),
        CommandHandler("integrity", integrity_check),
        CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
    ]
