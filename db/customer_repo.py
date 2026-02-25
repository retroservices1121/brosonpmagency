from db.connection import get_conn, is_postgres, ph, dict_cursor


def save_customer(telegram_id, telegram_handle, name, project_x_account):
    conn = get_conn()
    cur = conn.cursor()
    p = ph()

    if is_postgres():
        cur.execute(
            f"""
            INSERT INTO customers (telegram_id, telegram_handle, name, project_x_account)
            VALUES ({p}, {p}, {p}, {p})
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_handle = EXCLUDED.telegram_handle,
                name = EXCLUDED.name,
                project_x_account = EXCLUDED.project_x_account,
                registered_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, telegram_handle, name, project_x_account),
        )
    else:
        cur.execute(
            f"""
            INSERT INTO customers (telegram_id, telegram_handle, name, project_x_account)
            VALUES ({p}, {p}, {p}, {p})
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_handle = excluded.telegram_handle,
                name = excluded.name,
                project_x_account = excluded.project_x_account,
                registered_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, telegram_handle, name, project_x_account),
        )

    conn.commit()
    conn.close()


def get_customer(telegram_id):
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(f"SELECT * FROM customers WHERE telegram_id = {p}", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_customers():
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute("SELECT * FROM customers ORDER BY registered_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
