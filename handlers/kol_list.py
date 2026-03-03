"""Interactive KOL roster — /kols command with paginated list and detail views."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from db.kol_repo import get_all_kols, get_kol
from handlers.common import is_admin

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


def _format_kol_line(kol, index: int, admin_view: bool = False) -> str:
    """One-line summary for the paginated list."""
    status = ""
    if kol.get("is_verified"):
        status += " [verified]"
    if admin_view and not kol.get("is_active", True):
        status += " [inactive]"
    followers = kol.get("follower_count") or 0
    return (
        f"{index}. {kol['name']}  —  @{kol['x_account']}"
        f"  |  {followers:,} followers{status}"
    )


def _list_page(kols, page: int, admin_view: bool = False):
    """Build message text + keyboard for a given page."""
    total = len(kols)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_kols = kols[start:end]

    lines = [f"KOL Roster  ({total} total)  —  page {page + 1}/{total_pages}\n"]
    for i, kol in enumerate(page_kols, start=start + 1):
        lines.append(_format_kol_line(kol, i, admin_view))

    # Detail buttons for each KOL on this page
    detail_buttons = [
        [InlineKeyboardButton(
            f"{kol['name']}",
            callback_data=f"kols:detail:{kol['telegram_id']}:{page}",
        )]
        for kol in page_kols
    ]

    # Navigation row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("<< Prev", callback_data=f"kols:page:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next >>", callback_data=f"kols:page:{page + 1}"))

    # Refresh button
    refresh_row = [InlineKeyboardButton("Refresh", callback_data=f"kols:page:{page}")]

    rows = detail_buttons
    if nav:
        rows.append(nav)
    rows.append(refresh_row)

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _detail_view(kol, back_page: int, admin_view: bool = False):
    """Build detail text + keyboard for a single KOL."""
    verified = "Yes" if kol.get("is_verified") else "No"
    followers = kol.get("follower_count") or 0

    lines = [
        f"KOL Details — {kol['name']}\n",
        f"X Account: @{kol['x_account']}",
        f"Followers: {followers:,}",
        f"Verified: {verified}",
    ]

    if admin_view:
        active = "Yes" if kol.get("is_active", True) else "No"
        reputation = kol.get("reputation_score", 100.0)
        registered = str(kol.get("registered_at", ""))[:16]
        lines.extend([
            f"Telegram: {kol.get('telegram_handle', 'N/A')}",
            f"Telegram ID: {kol['telegram_id']}",
            f"Wallet: {kol.get('wallet_address', 'N/A')}",
            f"Active: {active}",
            f"Reputation: {reputation:.1f}",
            f"Registered: {registered}",
        ])

    buttons = []
    if admin_view:
        toggle_label = "Deactivate" if kol.get("is_active", True) else "Activate"
        buttons.append([InlineKeyboardButton(
            toggle_label,
            callback_data=f"kols:toggle:{kol['telegram_id']}:{back_page}",
        )])
    buttons.append([InlineKeyboardButton(
        "<< Back to list",
        callback_data=f"kols:page:{back_page}",
    )])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _toggle_active(telegram_id: int):
    """Toggle a KOL's is_active flag and return the new value."""
    from db.connection import get_conn, ph
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    # Read current value
    cur.execute(f"SELECT is_active FROM kols WHERE telegram_id = {p}", (telegram_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    current = row[0]
    new_val = not current
    cur.execute(
        f"UPDATE kols SET is_active = {p} WHERE telegram_id = {p}",
        (new_val, telegram_id),
    )
    conn.commit()
    conn.close()
    return new_val


def _get_visible_kols(admin_view: bool):
    """Return KOLs visible to the user. Admins see all; others see only active."""
    kols = get_all_kols()
    if admin_view:
        return kols
    return [k for k in kols if k.get("is_active", True)]


async def kols_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the interactive KOL roster (public command)."""
    admin_view = is_admin(update.effective_user)
    kols = _get_visible_kols(admin_view)
    if not kols:
        await update.message.reply_text("No KOLs registered yet.")
        return

    text, keyboard = _list_page(kols, 0, admin_view)
    await update.message.reply_text(text, reply_markup=keyboard)


async def kols_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all kols: button presses."""
    query = update.callback_query
    admin_view = is_admin(query.from_user)
    await query.answer()

    data = query.data  # e.g. "kols:page:0", "kols:detail:123:0", "kols:toggle:123:0"
    parts = data.split(":")

    action = parts[1]

    if action == "page":
        page = int(parts[2])
        kols = _get_visible_kols(admin_view)
        if not kols:
            await query.edit_message_text("No KOLs registered yet.")
            return
        text, keyboard = _list_page(kols, page, admin_view)
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            pass  # message unchanged (same page refresh, no new data)

    elif action == "detail":
        telegram_id = int(parts[2])
        back_page = int(parts[3])
        kol = get_kol(telegram_id)
        if not kol:
            await query.edit_message_text("KOL not found.")
            return
        # Non-admins can't view inactive KOLs
        if not admin_view and not kol.get("is_active", True):
            await query.edit_message_text("KOL not found.")
            return
        text, keyboard = _detail_view(kol, back_page, admin_view)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif action == "toggle":
        if not admin_view:
            await query.edit_message_text("Admins only.")
            return
        telegram_id = int(parts[2])
        back_page = int(parts[3])
        new_val = _toggle_active(telegram_id)
        if new_val is None:
            await query.edit_message_text("KOL not found.")
            return
        status_text = "activated" if new_val else "deactivated"
        # Show updated detail view
        kol = get_kol(telegram_id)
        text, keyboard = _detail_view(kol, back_page, admin_view)
        text = f"KOL {status_text}!\n\n" + text
        await query.edit_message_text(text, reply_markup=keyboard)


def get_handlers():
    return [
        CommandHandler("kols", kols_command),
        CallbackQueryHandler(kols_callback, pattern=r"^kols:"),
    ]
