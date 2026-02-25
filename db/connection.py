import sqlite3

import psycopg2
import psycopg2.extras

from config import DATABASE_URL


def get_conn():
    """Return a database connection (PostgreSQL if DATABASE_URL is set, else SQLite)."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect("kols.db")


def is_postgres():
    return DATABASE_URL is not None


def ph():
    """SQL parameter placeholder: %s for Postgres, ? for SQLite."""
    return "%s" if is_postgres() else "?"


def dict_cursor(conn):
    """Return a cursor that yields dict-like rows."""
    if is_postgres():
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    conn.row_factory = sqlite3.Row
    return conn.cursor()
