from db.connection import get_conn, is_postgres, ph, dict_cursor


def save_kol(telegram_id, telegram_handle, name, x_account, wallet_address):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()

    if is_postgres():
        cur.execute(
            f"""
            INSERT INTO kols (telegram_id, telegram_handle, name, x_account, wallet_address)
            VALUES ({p}, {p}, {p}, {p}, {p})
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_handle = EXCLUDED.telegram_handle,
                name = EXCLUDED.name,
                x_account = EXCLUDED.x_account,
                wallet_address = EXCLUDED.wallet_address,
                registered_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, telegram_handle, name, x_account, wallet_address),
        )
    else:
        cur.execute(
            f"""
            INSERT INTO kols (telegram_id, telegram_handle, name, x_account, wallet_address)
            VALUES ({p}, {p}, {p}, {p}, {p})
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_handle = excluded.telegram_handle,
                name = excluded.name,
                x_account = excluded.x_account,
                wallet_address = excluded.wallet_address,
                registered_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, telegram_handle, name, x_account, wallet_address),
        )

    conn.commit()
    conn.close()


def get_kol(telegram_id):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(f"SELECT * FROM kols WHERE telegram_id = {p}", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_kol_verification(telegram_id, x_user_id, follower_count, is_verified):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    cur.execute(
        f"""
        UPDATE kols
        SET x_user_id = {p}, follower_count = {p}, is_verified = {p}
        WHERE telegram_id = {p}
        """,
        (x_user_id, follower_count, is_verified, telegram_id),
    )
    conn.commit()
    conn.close()


def get_all_kols():
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute("SELECT * FROM kols ORDER BY registered_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
