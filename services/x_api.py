"""Async X (Twitter) API v2 client using Virtuals GAME tweepy SDK.

If GAME_TWITTER_ACCESS_TOKEN is not configured, all methods gracefully return
None so the bot can function without X API access (manual admin review).
"""
import asyncio
import logging
import re
import traceback

from config import GAME_TWITTER_ACCESS_TOKEN

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Return a singleton Virtuals tweepy Client."""
    global _client
    if _client is None:
        from virtuals_tweepy import Client
        logger.info("Initializing Virtuals tweepy Client (token starts with: %s...)",
                     GAME_TWITTER_ACCESS_TOKEN[:8] if len(GAME_TWITTER_ACCESS_TOKEN) > 8 else "???")
        _client = Client(game_twitter_access_token=GAME_TWITTER_ACCESS_TOKEN)
    return _client


def is_configured() -> bool:
    return bool(GAME_TWITTER_ACCESS_TOKEN)


async def get_user_by_username(username: str) -> dict | None:
    """Fetch X user by username. Returns dict with id, name, username, public_metrics.

    Tries multiple GAME proxy approaches since not all endpoints are available.
    """
    if not is_configured():
        return None
    username = username.lstrip("@")

    client = _get_client()

    # Approach 1: get_user by username (standard tweepy)
    for attempt_name, attempt_fn, attempt_kwargs in [
        ("get_user", client.get_user, dict(username=username, user_fields=["public_metrics"])),
        ("get_user(no fields)", client.get_user, dict(username=username)),
        ("get_users", client.get_users, dict(usernames=[username], user_fields=["public_metrics"])),
        ("get_users(no fields)", client.get_users, dict(usernames=[username])),
        ("search_recent_tweets", client.search_recent_tweets, dict(
            query=f"from:{username}", max_results=10,
            expansions=["author_id"], user_fields=["public_metrics"],
        )),
        ("search_recent_tweets(minimal)", client.search_recent_tweets, dict(
            query=f"from:{username}", max_results=10,
        )),
    ]:
        try:
            logger.info("Trying %s for @%s ...", attempt_name, username)
            resp = await asyncio.to_thread(attempt_fn, **attempt_kwargs)
            logger.info("%s succeeded! resp.data=%s, resp.includes=%s",
                        attempt_name, type(resp.data).__name__ if resp.data else None,
                        list(getattr(resp, 'includes', {}).keys()) if getattr(resp, 'includes', None) else None)

            # Handle get_user (singular) — resp.data is a single User
            if attempt_name.startswith("get_user") and resp.data and not isinstance(resp.data, list):
                user = resp.data
                return {
                    "id": str(user.id),
                    "name": user.name,
                    "username": user.username,
                    "public_metrics": getattr(user, "public_metrics", None),
                }

            # Handle get_users (plural) — resp.data is a list
            if attempt_name.startswith("get_users") and resp.data and isinstance(resp.data, list) and len(resp.data) > 0:
                user = resp.data[0]
                return {
                    "id": str(user.id),
                    "name": user.name,
                    "username": user.username,
                    "public_metrics": getattr(user, "public_metrics", None),
                }

            # Handle search — user info is in includes
            if attempt_name.startswith("search") and resp.data:
                includes = getattr(resp, "includes", None) or {}
                users = includes.get("users", [])
                if users:
                    user = users[0]
                    return {
                        "id": str(user.id),
                        "name": user.name,
                        "username": user.username,
                        "public_metrics": getattr(user, "public_metrics", None),
                    }
                # Search found tweets but no user expansion — extract author_id from tweet
                tweet = resp.data[0]
                author_id = getattr(tweet, "author_id", None)
                if author_id:
                    return {
                        "id": str(author_id),
                        "name": username,
                        "username": username,
                        "public_metrics": None,
                    }

        except Exception as e:
            resp_text = ""
            if hasattr(e, "response") and hasattr(e.response, "text"):
                resp_text = e.response.text[:500]
            logger.warning("  %s failed: %s %s", attempt_name, e, resp_text)
            continue

    logger.error("All approaches failed for @%s", username)
    return None


async def get_tweet(tweet_id: str) -> dict | None:
    """Fetch a tweet by ID. Returns dict with id, text, author_id, entities."""
    if not is_configured():
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
        logger.warning("X API tweet fetch returned no data for %s", tweet_id)
    except Exception as e:
        logger.error("X API error: %s", e)
    return None


async def get_retweeters(tweet_id: str) -> list[str]:
    """Return list of user IDs who retweeted the given tweet."""
    if not is_configured():
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
    if not is_configured():
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


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a twitter.com or x.com URL."""
    match = re.search(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)", url)
    return match.group(1) if match else None


async def verify_user_tweet(x_user_id: str, code: str) -> bool:
    """Check if the user has a recent tweet containing the given code.

    Used for KOL verification during registration.
    """
    if not is_configured():
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
