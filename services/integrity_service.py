"""Tweet integrity check — detect deleted proof-of-work tweets and ban offenders."""
import asyncio
import logging

from db.acceptance_repo import get_recent_verified_with_tweets
from db.kol_repo import ban_kol
from services.x_api import check_tweet_exists, extract_tweet_id

logger = logging.getLogger(__name__)


async def run_integrity_check(progress_callback=None):
    """Check recently verified tweets and ban KOLs who deleted them.

    Args:
        progress_callback: Optional async callable(checked, total) for UI updates.

    Returns a summary dict:
        {
            "total": int,          # unique tweets checked
            "ok": int,             # tweets still live
            "deleted": int,        # confirmed deleted
            "errors": int,         # API errors (skipped)
            "bans": [              # list of ban details
                {
                    "kol_telegram_id": int,
                    "kol_name": str,
                    "x_account": str,
                    "campaign_id": int,
                    "project_name": str,
                    "tweet_url": str,
                    "paid": bool,
                },
            ],
        }
    """
    acceptances = get_recent_verified_with_tweets()

    # Deduplicate by tweet ID — one KOL may have the same tweet across campaigns
    tweet_map = {}  # tweet_id -> list of acceptance dicts
    for acc in acceptances:
        tid = extract_tweet_id(acc["submission_tweet_url"])
        if not tid:
            continue
        tweet_map.setdefault(tid, []).append(acc)

    total = len(tweet_map)
    ok = 0
    deleted = 0
    errors = 0
    bans = []
    banned_kols = set()  # track already-banned KOL IDs in this run

    for i, (tweet_id, accs) in enumerate(tweet_map.items()):
        # Rate limit: ~9 seconds between calls
        if i > 0:
            await asyncio.sleep(9)

        exists = await check_tweet_exists(tweet_id)

        if exists is True:
            ok += 1
        elif exists is False:
            deleted += 1
            # Ban each KOL associated with this deleted tweet
            for acc in accs:
                kol_tid = acc["kol_telegram_id"]
                if kol_tid in banned_kols:
                    continue
                ban_kol(kol_tid)
                banned_kols.add(kol_tid)
                bans.append({
                    "kol_telegram_id": kol_tid,
                    "kol_name": acc["kol_name"],
                    "x_account": acc["x_account"],
                    "campaign_id": acc["campaign_id"],
                    "project_name": acc["project_name"],
                    "tweet_url": acc["submission_tweet_url"],
                    "paid": acc.get("payout_status") == "paid",
                })
                logger.warning(
                    "Banned KOL %s (%s) — deleted tweet %s for campaign #%d",
                    acc["kol_name"], kol_tid, tweet_id, acc["campaign_id"],
                )
        else:
            errors += 1

        if progress_callback and ((i + 1) % 5 == 0 or i == total - 1):
            try:
                await progress_callback(i + 1, total)
            except Exception:
                pass

    return {
        "total": total,
        "ok": ok,
        "deleted": deleted,
        "errors": errors,
        "bans": bans,
    }
