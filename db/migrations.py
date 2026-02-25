"""Idempotent schema creation and migration.

Call run_migrations() at startup to ensure all tables exist and
new columns are added to legacy tables.
"""
import logging

from db.connection import get_conn, is_postgres

logger = logging.getLogger(__name__)


def _add_column_if_missing(cursor, table, column, col_type, pg=True):
    """Add a column to *table* if it does not already exist."""
    if pg:
        cursor.execute(
            f"SELECT 1 FROM information_schema.columns "
            f"WHERE table_name=%s AND column_name=%s",
            (table, column),
        )
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info("Added column %s.%s", table, column)
    else:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info("Added column %s.%s", table, column)


def run_migrations():
    conn = get_conn()
    cur = conn.cursor()
    pg = is_postgres()

    # ---- core tables (from original schema) ----
    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kols (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                x_account TEXT,
                wallet_address TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                project_x_account TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kols (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                x_account TEXT,
                wallet_address TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                telegram_handle TEXT,
                name TEXT,
                project_x_account TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # ---- new columns on existing tables ----
    _add_column_if_missing(cur, "kols", "x_user_id", "TEXT", pg)
    _add_column_if_missing(cur, "kols", "follower_count", "INTEGER DEFAULT 0", pg)
    _add_column_if_missing(cur, "kols", "is_verified", "BOOLEAN DEFAULT FALSE", pg)
    _add_column_if_missing(cur, "kols", "is_active", "BOOLEAN DEFAULT TRUE", pg)
    _add_column_if_missing(cur, "kols", "reputation_score", "REAL DEFAULT 100.0", pg)
    _add_column_if_missing(cur, "customers", "wallet_address", "TEXT", pg)

    # ---- campaigns table ----
    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id SERIAL PRIMARY KEY,
                customer_telegram_id BIGINT REFERENCES customers(telegram_id),
                project_name TEXT NOT NULL,
                service_type TEXT NOT NULL,
                target_url TEXT,
                talking_points TEXT,
                hashtags TEXT,
                mentions TEXT,
                reference_tweet_url TEXT,
                media_file_id TEXT,
                kol_count INTEGER NOT NULL,
                per_kol_rate INTEGER NOT NULL,
                platform_fee INTEGER NOT NULL,
                total_cost INTEGER NOT NULL,
                deadline TIMESTAMP NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_payment',
                accepted_count INTEGER DEFAULT 0,
                announcement_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY,
                customer_telegram_id INTEGER REFERENCES customers(telegram_id),
                project_name TEXT NOT NULL,
                service_type TEXT NOT NULL,
                target_url TEXT,
                talking_points TEXT,
                hashtags TEXT,
                mentions TEXT,
                reference_tweet_url TEXT,
                media_file_id TEXT,
                kol_count INTEGER NOT NULL,
                per_kol_rate INTEGER NOT NULL,
                platform_fee INTEGER NOT NULL,
                total_cost INTEGER NOT NULL,
                deadline TIMESTAMP NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_payment',
                accepted_count INTEGER DEFAULT 0,
                announcement_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

    # ---- campaign_acceptances table ----
    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS campaign_acceptances (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER REFERENCES campaigns(id),
                kol_telegram_id BIGINT REFERENCES kols(telegram_id),
                status TEXT NOT NULL DEFAULT 'accepted',
                submission_tweet_url TEXT,
                verification_result TEXT,
                accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                submitted_at TIMESTAMP,
                verified_at TIMESTAMP,
                UNIQUE(campaign_id, kol_telegram_id)
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS campaign_acceptances (
                id INTEGER PRIMARY KEY,
                campaign_id INTEGER REFERENCES campaigns(id),
                kol_telegram_id INTEGER REFERENCES kols(telegram_id),
                status TEXT NOT NULL DEFAULT 'accepted',
                submission_tweet_url TEXT,
                verification_result TEXT,
                accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                submitted_at TIMESTAMP,
                verified_at TIMESTAMP,
                UNIQUE(campaign_id, kol_telegram_id)
            )
        """)

    conn.commit()
    conn.close()
    logger.info("Database migrations complete.")
