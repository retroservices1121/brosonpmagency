"""FCFS campaign acceptance with database-level locking."""
import logging

from db.connection import get_conn, is_postgres, ph, dict_cursor
from db import campaign_repo, acceptance_repo
from services import campaign_service

logger = logging.getLogger(__name__)


class AcceptanceError(Exception):
    pass


def accept_campaign(campaign_id: int, kol_telegram_id: int) -> dict:
    """Atomically accept a campaign slot for a KOL.

    Uses PG advisory locks (or SQLite BEGIN IMMEDIATE) to prevent race conditions.
    Returns the acceptance dict on success.
    Raises AcceptanceError with user-friendly message on failure.
    """
    # Check if already accepted
    existing = acceptance_repo.get_acceptance(campaign_id, kol_telegram_id)
    if existing:
        raise AcceptanceError("You've already accepted this campaign.")

    conn = get_conn()
    try:
        cur = conn.cursor()
        p = ph()

        if is_postgres():
            cur.execute("BEGIN")
            # Advisory lock scoped to this campaign
            cur.execute(f"SELECT pg_advisory_xact_lock({p})", (campaign_id,))
        else:
            conn.execute("BEGIN IMMEDIATE")

        # Re-check campaign state under lock
        cur.execute(
            f"SELECT status, accepted_count, kol_count FROM campaigns WHERE id = {p}",
            (campaign_id,),
        )
        row = cur.fetchone()
        if not row:
            raise AcceptanceError("Campaign not found.")

        status, accepted_count, kol_count = row[0], row[1], row[2]
        if status not in ("live", "filled"):
            raise AcceptanceError("This campaign is not currently accepting KOLs.")
        if accepted_count >= kol_count:
            raise AcceptanceError("This campaign is already full.")

        # Insert acceptance
        cur.execute(
            f"""
            INSERT INTO campaign_acceptances (campaign_id, kol_telegram_id, status)
            VALUES ({p}, {p}, 'accepted')
            """,
            (campaign_id, kol_telegram_id),
        )

        # Increment count
        new_count = accepted_count + 1
        cur.execute(
            f"UPDATE campaigns SET accepted_count = {p} WHERE id = {p}",
            (new_count, campaign_id),
        )

        # Fill campaign if all slots taken
        if new_count >= kol_count:
            cur.execute(
                f"UPDATE campaigns SET status = 'filled' WHERE id = {p}",
                (campaign_id,),
            )

        conn.commit()
        logger.info(
            "KOL %s accepted campaign #%d (%d/%d)",
            kol_telegram_id, campaign_id, new_count, kol_count,
        )

        return {
            "campaign_id": campaign_id,
            "kol_telegram_id": kol_telegram_id,
            "accepted_count": new_count,
            "kol_count": kol_count,
            "is_filled": new_count >= kol_count,
        }

    except AcceptanceError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        logger.error("Acceptance error: %s", e)
        raise AcceptanceError("Something went wrong. Please try again.")
    finally:
        conn.close()
