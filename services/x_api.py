"""Async X (Twitter) API v2 client using Virtuals GAME tweepy SDK.

If GAME_TWITTER_ACCESS_TOKEN is not configured (or the GAME proxy does not
support read operations), all methods gracefully return None / [] / False
so the bot falls back to manual admin review.
"""
import asyncio
import logging
import re

from config import GAME_TWITTER_ACCESS_TOKEN

logger = logging.getLogger(__name__)

_client = None
_read_available = None  # None = untested, True/False = cached result


def _get_client():
    """Return a singleton Virtuals tweepy Client."""
    global _client
    if _client is None:
        from virtuals_tweepy import Client
        _client = Client(game_twitter_access_token=GAME_TWITTER_ACCESS_TOKEN)
    return _client


def is_configured() -> bool:
    return bool(GAME_TWITTER_ACCESS_TOKEN)


async def _check_read_access() -> bool:
    """One-time probe: try a minimal read call to see if the GAME proxy supports it."""
    global _read_available
    if _read_available is not None:
        return _read_available
    try:
        await asyncio.to_thread(
            _get_client().get_user, username="x",
        )
        _read_available = True
    except Exception:
        logger.warning("GAME proxy does not support read operations — "
                       "X verification will use manual admin review.")
        _read_available = False
    return _read_available


async def is_read_available() -> bool:
    """Public wrapper — True if the GAME proxy supports read endpoints."""
    if not is_configured():
        return False
    return await _check_read_access()


async def get_user_by_username(username: str) -> dict | None:
    """Fetch X user by username. Returns dict with id, name, username, public_metrics."""
    if not is_configured() or not await _check_read_access():
        return None
    username = username.lstrip("@")
    try:
        resp = await asyncio.to_thread(
            _get_client().get_user,
            username=username,
            user_fields=["public_metrics"],
        )
        if resp.data:
            user = resp.data
            return {
                "id": str(user.id),
                "name": user.name,
                "username": user.username,
                "public_metrics": user.public_metrics,
            }
    except Exception as e:
        logger.error("X API error: %s", e)
    return None


async def get_tweet(tweet_id: str) -> dict | None:
    """Fetch a tweet by ID. Returns dict with id, text, author_id, entities."""
    if not is_configured() or not await _check_read_access():
        return None
    try:
        resp = await asyncio.to_thread(
            _get_client().get_tweet,
            id=tweet_id,
            tweet_fields=["author_id", "created_at", "entities", "referenced_tweets"],
            expansions=["author_id"],
        )
        if resp.data:
            tweet = resp.data
            return {
                "id": str(tweet.id),
                "text": tweet.text,
                "author_id": str(tweet.author_id) if tweet.author_id else None,
                "entities": tweet.entities,
                "referenced_tweets": (
                    [{"type": rt.type, "id": str(rt.id)} for rt in tweet.referenced_tweets]
                    if tweet.referenced_tweets else None
                ),
                "created_at": str(tweet.created_at) if tweet.created_at else None,
            }
    except Exception as e:
        logger.error("X API error: %s", e)
    return None


async def get_retweeters(tweet_id: str) -> list[str]:
    """Return list of user IDs who retweeted the given tweet."""
    if not is_configured() or not await _check_read_access():
        return []
    try:
        resp = await asyncio.to_thread(
            _get_client().get_retweeters,
            id=tweet_id,
        )
        if resp.data:
            return [str(u.id) for u in resp.data]
        return []
    except Exception as e:
        logger.error("X API error: %s", e)
    return []


async def get_liking_users(tweet_id: str) -> list[str]:
    """Return list of user IDs who liked the given tweet."""
    if not is_configured() or not await _check_read_access():
        return []
    try:
        resp = await asyncio.to_thread(
            _get_client().get_liking_users,
            id=tweet_id,
        )
        if resp.data:
            return [str(u.id) for u in resp.data]
        return []
    except Exception as e:
        logger.error("X API error: %s", e)
    return []


async def check_tweet_exists(tweet_id: str) -> bool | None:
    """Check whether a tweet still exists.

    Returns True if it exists, False if confirmed deleted/not found,
    None if the API call failed (inconclusive — skip to avoid false bans).
    """
    if not is_configured() or not await _check_read_access():
        return None
    try:
        resp = await asyncio.to_thread(
            _get_client().get_tweet,
            id=tweet_id,
            tweet_fields=["id"],
        )
        return resp.data is not None
    except Exception as e:
        err = str(e).lower()
        # Twitter API returns specific errors for deleted/not-found tweets
        if "not found" in err or "no data" in err:
            return False
        logger.error("X API error checking tweet %s: %s", tweet_id, e)
        return None


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a twitter.com or x.com URL."""
    match = re.search(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)", url)
    return match.group(1) if match else None


async def verify_user_tweet(x_user_id: str, code: str) -> bool:
    """Check if the user has a recent tweet containing the given code.

    Used for KOL verification during registration.
    """
    if not is_configured() or not await _check_read_access():
        return False
    try:
        resp = await asyncio.to_thread(
            _get_client().get_users_tweets,
            id=x_user_id,
            max_results=10,
        )
        if resp.data:
            for tweet in resp.data:
                if code in tweet.text:
                    return True
    except Exception as e:
        logger.error("X API error during verification: %s", e)
    return False
