from db.connection import get_conn, is_postgres, ph, dict_cursor


def create_acceptance(campaign_id: int, kol_telegram_id: int) -> int | None:
    """Insert an acceptance row. Returns id on success, None if duplicate."""
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    try:
        cur.execute(
            f"""
            INSERT INTO campaign_acceptances (campaign_id, kol_telegram_id, status)
            VALUES ({p}, {p}, 'accepted')
            """,
            (campaign_id, kol_telegram_id),
        )
        if is_postgres():
            cur.execute("SELECT lastval()")
            acceptance_id = cur.fetchone()[0]
        else:
            acceptance_id = cur.lastrowid
        conn.commit()
        return acceptance_id
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_acceptance(campaign_id: int, kol_telegram_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"""
        SELECT * FROM campaign_acceptances
        WHERE campaign_id = {p} AND kol_telegram_id = {p}
        """,
        (campaign_id, kol_telegram_id),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_acceptance_by_id(acceptance_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(f"SELECT * FROM campaign_acceptances WHERE id = {p}", (acceptance_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_acceptances_for_campaign(campaign_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"""
        SELECT ca.*, k.name as kol_name, k.x_account
        FROM campaign_acceptances ca
        JOIN kols k ON k.telegram_id = ca.kol_telegram_id
        WHERE ca.campaign_id = {p}
        ORDER BY ca.accepted_at
        """,
        (campaign_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_acceptances_for_kol(kol_telegram_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"""
        SELECT ca.*, c.project_name, c.service_type, c.deadline, c.status as campaign_status
        FROM campaign_acceptances ca
        JOIN campaigns c ON c.id = ca.campaign_id
        WHERE ca.kol_telegram_id = {p}
        ORDER BY ca.accepted_at DESC
        """,
        (kol_telegram_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_acceptance_status(acceptance_id: int, status: str, extra_fields: dict = None):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()

    sets = [f"status = {p}"]
    vals = [status]

    if extra_fields:
        for k, v in extra_fields.items():
            sets.append(f"{k} = {p}")
            vals.append(v)

    vals.append(acceptance_id)
    cur.execute(
        f"UPDATE campaign_acceptances SET {', '.join(sets)} WHERE id = {p}",
        tuple(vals),
    )
    conn.commit()
    conn.close()


def get_accepted_submission(kol_telegram_id: int, campaign_id: int):
    """Get an acceptance that is in 'accepted' status (ready to submit)."""
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"""
        SELECT * FROM campaign_acceptances
        WHERE kol_telegram_id = {p} AND campaign_id = {p} AND status = 'accepted'
        """,
        (kol_telegram_id, campaign_id),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_verifications():
    """Return submissions awaiting manual review."""
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute(
        """
        SELECT ca.*, k.name as kol_name, k.x_account, c.project_name, c.service_type
        FROM campaign_acceptances ca
        JOIN kols k ON k.telegram_id = ca.kol_telegram_id
        JOIN campaigns c ON c.id = ca.campaign_id
        WHERE ca.status = 'submitted'
        ORDER BY ca.submitted_at
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_verified_for_campaign(campaign_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    cur.execute(
        f"SELECT COUNT(*) FROM campaign_acceptances WHERE campaign_id = {p} AND status = 'verified'",
        (campaign_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_unpaid_verified():
    """Return verified acceptances that haven't been paid yet."""
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute(
        """
        SELECT ca.*, k.name as kol_name, k.x_account, k.wallet_address as kol_wallet,
               c.project_name, c.service_type, c.per_kol_rate
        FROM campaign_acceptances ca
        JOIN kols k ON k.telegram_id = ca.kol_telegram_id
        JOIN campaigns c ON c.id = ca.campaign_id
        WHERE ca.status = 'verified' AND (ca.payout_status IS NULL OR ca.payout_status = 'unpaid')
        ORDER BY ca.verified_at
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_paid(acceptance_id: int):
    """Mark an acceptance as paid."""
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    from datetime import datetime
    cur.execute(
        f"UPDATE campaign_acceptances SET payout_status = 'paid', paid_at = {p} WHERE id = {p}",
        (datetime.utcnow().isoformat(), acceptance_id),
    )
    conn.commit()
    conn.close()
