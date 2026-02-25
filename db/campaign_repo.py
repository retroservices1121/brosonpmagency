from db.connection import get_conn, ph, dict_cursor


def create_campaign(data: dict) -> int:
    """Insert a new campaign and return its id."""
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    cur.execute(
        f"""
        INSERT INTO campaigns (
            customer_telegram_id, project_name, service_type,
            target_url, talking_points, hashtags, mentions,
            reference_tweet_url, media_file_id,
            kol_count, per_kol_rate, platform_fee, total_cost,
            deadline, status
        ) VALUES (
            {p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p}
        )
        """,
        (
            data["customer_telegram_id"],
            data["project_name"],
            data["service_type"],
            data.get("target_url"),
            data.get("talking_points"),
            data.get("hashtags"),
            data.get("mentions"),
            data.get("reference_tweet_url"),
            data.get("media_file_id"),
            data["kol_count"],
            data["per_kol_rate"],
            data["platform_fee"],
            data["total_cost"],
            data["deadline"],
            "pending_payment",
        ),
    )

    # Get the inserted id
    from db.connection import is_postgres
    if is_postgres():
        cur.execute("SELECT lastval()")
        campaign_id = cur.fetchone()[0]
    else:
        campaign_id = cur.lastrowid

    conn.commit()
    conn.close()
    return campaign_id


def get_campaign(campaign_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(f"SELECT * FROM campaigns WHERE id = {p}", (campaign_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_campaigns_by_status(status: str):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"SELECT * FROM campaigns WHERE status = {p} ORDER BY created_at DESC",
        (status,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campaigns_by_customer(telegram_id: int):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"SELECT * FROM campaigns WHERE customer_telegram_id = {p} ORDER BY created_at DESC",
        (telegram_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_live_campaigns():
    """Return campaigns that are live and not yet filled."""
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute(
        "SELECT * FROM campaigns WHERE status IN ('live', 'filled') ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_campaign_status(campaign_id: int, status: str, extra_fields: dict = None):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()

    sets = [f"status = {p}"]
    vals = [status]

    if extra_fields:
        for k, v in extra_fields.items():
            sets.append(f"{k} = {p}")
            vals.append(v)

    vals.append(campaign_id)
    cur.execute(
        f"UPDATE campaigns SET {', '.join(sets)} WHERE id = {p}",
        tuple(vals),
    )
    conn.commit()
    conn.close()


def increment_accepted_count(campaign_id: int) -> int:
    """Increment accepted_count and return the new value."""
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    cur.execute(
        f"UPDATE campaigns SET accepted_count = accepted_count + 1 WHERE id = {p}",
        (campaign_id,),
    )
    cur.execute(f"SELECT accepted_count, kol_count FROM campaigns WHERE id = {p}", (campaign_id,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return row[0], row[1]  # accepted_count, kol_count


def set_announcement_message_id(campaign_id: int, message_id: str):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    cur.execute(
        f"UPDATE campaigns SET announcement_message_id = {p} WHERE id = {p}",
        (message_id, campaign_id),
    )
    conn.commit()
    conn.close()


def get_expired_campaigns(now_ts: str):
    """Return live/filled campaigns past their deadline."""
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(
        f"SELECT * FROM campaigns WHERE status IN ('live', 'filled') AND deadline < {p}",
        (now_ts,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_campaigns():
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute("SELECT * FROM campaigns ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
