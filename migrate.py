"""One-time script to migrate local SQLite data to Railway PostgreSQL.

Usage:
    set DATABASE_URL=postgresql://...   (from Railway)
    python migrate.py
"""
import os
import sqlite3
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: Set DATABASE_URL env var first (copy from Railway dashboard)")
    exit(1)

# Read from local SQLite
local = sqlite3.connect("kols.db")
cur = local.cursor()

# Migrate KOLs
cur.execute("SELECT telegram_id, telegram_handle, name, x_account, wallet_address, registered_at FROM kols")
kols = cur.fetchall()

# Migrate Customers
cur.execute("SELECT telegram_id, telegram_handle, name, project_x_account, registered_at FROM customers")
customers = cur.fetchall()
local.close()

# Write to PostgreSQL
pg = psycopg2.connect(DATABASE_URL)
pgc = pg.cursor()

for row in kols:
    pgc.execute(
        """
        INSERT INTO kols (telegram_id, telegram_handle, name, x_account, wallet_address, registered_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(telegram_id) DO NOTHING
        """,
        row,
    )

for row in customers:
    pgc.execute(
        """
        INSERT INTO customers (telegram_id, telegram_handle, name, project_x_account, registered_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(telegram_id) DO NOTHING
        """,
        row,
    )

pg.commit()
pg.close()

print(f"Migrated {len(kols)} KOL(s) and {len(customers)} customer(s) to PostgreSQL.")
