import csv
import io
import os
import sqlite3

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")


def _get_conn():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect("kols.db")


def _is_postgres():
    return DATABASE_URL is not None


def init_db():
    conn = _get_conn()
    cursor = conn.cursor()

    if _is_postgres():
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS kols (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                x_account TEXT,
                wallet_address TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                project_x_account TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS kols (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                x_account TEXT,
                wallet_address TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                project_x_account TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    conn.commit()
    conn.close()


def save_kol(telegram_id, telegram_handle, name, x_account, wallet_address):
    conn = _get_conn()
    cursor = conn.cursor()

    if _is_postgres():
        cursor.execute(
            """
            INSERT INTO kols (telegram_id, telegram_handle, name, x_account, wallet_address)
            VALUES (%s, %s, %s, %s, %s)
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
        cursor.execute(
            """
            INSERT INTO kols (telegram_id, telegram_handle, name, x_account, wallet_address)
            VALUES (?, ?, ?, ?, ?)
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
    conn = _get_conn()
    cursor = conn.cursor()

    if _is_postgres():
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM kols WHERE telegram_id = %s", (telegram_id,))
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM kols WHERE telegram_id = ?", (telegram_id,))

    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def save_customer(telegram_id, telegram_handle, name, project_x_account):
    conn = _get_conn()
    cursor = conn.cursor()

    if _is_postgres():
        cursor.execute(
            """
            INSERT INTO customers (telegram_id, telegram_handle, name, project_x_account)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_handle = EXCLUDED.telegram_handle,
                name = EXCLUDED.name,
                project_x_account = EXCLUDED.project_x_account,
                registered_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, telegram_handle, name, project_x_account),
        )
    else:
        cursor.execute(
            """
            INSERT INTO customers (telegram_id, telegram_handle, name, project_x_account)
            VALUES (?, ?, ?, ?)
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


def export_csv(table="kols"):
    conn = _get_conn()
    cursor = conn.cursor()

    if table == "customers":
        q = "SELECT name, project_x_account, telegram_handle, telegram_id, registered_at FROM customers"
    else:
        q = "SELECT name, x_account, wallet_address, telegram_handle, telegram_id, registered_at FROM kols"

    cursor.execute(q)
    rows = cursor.fetchall()
    columns = [d[0] for d in cursor.description]
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()
