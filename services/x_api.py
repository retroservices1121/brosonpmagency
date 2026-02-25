"""Async X (Twitter) API v2 client using httpx.

If X_API_BEARER_TOKEN is not configured, all methods gracefully return None
so the bot can function without X API access.
"""
import logging

import httpx

from config import X_API_BEARER_TOKEN

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twitter.com/2"


def _headers():
    return {"Authorization": f"Bearer {X_API_BEARER_TOKEN}"}


def is_configured() -> bool:
    return bool(X_API_BEARER_TOKEN)


async def get_user_by_username(username: str) -> dict | None:
    """Fetch X user by username. Returns dict with id, name, username, public_metrics."""
    if not is_configured():
        return None
    username = username.lstrip("@")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/users/by/username/{username}",
                headers=_headers(),
                params={"user.fields": "public_metrics"},
            )
            if resp.status_code == 200:
                return resp.json().get("data")
            logger.warning("X API user lookup failed: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("X API error: %s", e)
    return None


async def get_tweet(tweet_id: str) -> dict | None:
    """Fetch a tweet by ID. Returns dict with id, text, author_id, entities."""
    if not is_configured():
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/tweets/{tweet_id}",
                headers=_headers(),
                params={
                    "tweet.fields": "author_id,created_at,entities,referenced_tweets",
                    "expansions": "author_id",
                },
            )
            if resp.status_code == 200:
                return resp.json().get("data")
            logger.warning("X API tweet fetch failed: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("X API error: %s", e)
    return None


async def get_retweeters(tweet_id: str) -> list[str]:
    """Return list of user IDs who retweeted the given tweet."""
    if not is_configured():
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/tweets/{tweet_id}/retweeted_by",
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return [u["id"] for u in data]
            logger.warning("X API retweeters failed: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("X API error: %s", e)
    return []


async def get_liking_users(tweet_id: str) -> list[str]:
    """Return list of user IDs who liked the given tweet."""
    if not is_configured():
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/tweets/{tweet_id}/liking_users",
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return [u["id"] for u in data]
            logger.warning("X API liking_users failed: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("X API error: %s", e)
    return []


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a twitter.com or x.com URL."""
    import re
    match = re.search(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)", url)
    return match.group(1) if match else None


async def verify_user_tweet(x_user_id: str, code: str) -> bool:
    """Check if the user has a recent tweet containing the given code.

    Used for KOL verification during registration.
    """
    if not is_configured():
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/users/{x_user_id}/tweets",
                headers=_headers(),
                params={"max_results": 10, "tweet.fields": "text"},
            )
            if resp.status_code == 200:
                tweets = resp.json().get("data", [])
                for tweet in tweets:
                    if code in tweet.get("text", ""):
                        return True
    except Exception as e:
        logger.error("X API error during verification: %s", e)
    return False
