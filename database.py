import csv
import io
import sqlite3

DB_FILE = "kols.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    # Add wallet_address column if missing (migration for existing DBs)
    cursor.execute("PRAGMA table_info(kols)")
    columns = [row[1] for row in cursor.fetchall()]
    if "wallet_address" not in columns:
        cursor.execute("ALTER TABLE kols ADD COLUMN wallet_address TEXT")

    conn.commit()
    conn.close()


def save_kol(telegram_id, telegram_handle, name, x_account, wallet_address):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kols WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_customer(telegram_id, telegram_handle, name, project_x_account):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if table == "customers":
        cursor.execute(
            "SELECT name, project_x_account, telegram_handle, telegram_id, registered_at FROM customers"
        )
    else:
        cursor.execute(
            "SELECT name, x_account, wallet_address, telegram_handle, telegram_id, registered_at FROM kols"
        )
    rows = cursor.fetchall()
    columns = [d[0] for d in cursor.description]
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()
