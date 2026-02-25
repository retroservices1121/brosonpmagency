"""Service tier CRUD — pricing stored in DB, editable by admins at runtime."""
from db.connection import get_conn, ph, dict_cursor, is_postgres


def get_all_tiers() -> dict:
    """Return service tiers as a dict matching the old SERVICE_TIERS format.

    Returns: {key: (display_name, per_kol_rate, min_kols, max_kols), ...}
    """
    conn = get_conn()
    cur = dict_cursor(conn)
    cur.execute("SELECT * FROM service_tiers WHERE is_active = TRUE ORDER BY per_kol_rate")
    rows = cur.fetchall()
    conn.close()
    result = {}
    for r in rows:
        d = dict(r)
        result[d["key"]] = (d["display_name"], d["per_kol_rate"], d["min_kols"], d["max_kols"])
    return result


def get_tier(key: str):
    """Return a single tier as a raw dict, or None."""
    conn = get_conn()
    cur = dict_cursor(conn)
    p = ph()
    cur.execute(f"SELECT * FROM service_tiers WHERE key = {p}", (key,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_tier(key: str, per_kol_rate: int = None, min_kols: int = None, max_kols: int = None):
    """Update pricing/limits for a service tier."""
    conn = get_conn()
    cur = conn.cursor()
    p = ph()
    sets = []
    vals = []
    if per_kol_rate is not None:
        sets.append(f"per_kol_rate = {p}")
        vals.append(per_kol_rate)
    if min_kols is not None:
        sets.append(f"min_kols = {p}")
        vals.append(min_kols)
    if max_kols is not None:
        sets.append(f"max_kols = {p}")
        vals.append(max_kols)
    if not sets:
        conn.close()
        return
    vals.append(key)
    cur.execute(f"UPDATE service_tiers SET {', '.join(sets)} WHERE key = {p}", tuple(vals))
    conn.commit()
    conn.close()
