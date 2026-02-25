"""Tweet verification pipeline for campaign submissions."""
import json
import logging

from db import acceptance_repo, campaign_repo
from db.kol_repo import get_kol
from services import x_api
from services.campaign_service import complete_campaign

logger = logging.getLogger(__name__)


async def verify_submission(acceptance_id: int, tweet_url: str) -> dict:
    """Verify a KOL's tweet submission against campaign requirements.

    Returns a result dict with:
      - verified: bool
      - reason: str
      - auto: bool (True if auto-verified, False if needs manual review)
    """
    acceptance = acceptance_repo.get_acceptance_by_id(acceptance_id)
    if not acceptance:
        return {"verified": False, "reason": "Acceptance not found.", "auto": False}

    campaign = campaign_repo.get_campaign(acceptance["campaign_id"])
    if not campaign:
        return {"verified": False, "reason": "Campaign not found.", "auto": False}

    kol = get_kol(acceptance["kol_telegram_id"])
    tweet_id = x_api.extract_tweet_id(tweet_url)

    # Update the submission URL
    acceptance_repo.update_acceptance_status(
        acceptance_id, "submitted",
        extra_fields={
            "submission_tweet_url": tweet_url,
            "submitted_at": __import__("datetime").datetime.utcnow().isoformat(),
        },
    )

    # If X API is not configured, go to manual review
    if not x_api.is_configured():
        return {
            "verified": False,
            "reason": "X API not configured — submission queued for manual review.",
            "auto": False,
        }

    if not tweet_id:
        return {
            "verified": False,
            "reason": "Could not extract tweet ID from URL.",
            "auto": False,
        }

    service = campaign["service_type"]
    target_tweet_id = x_api.extract_tweet_id(campaign["target_url"] or "")
    kol_x_user_id = kol.get("x_user_id") if kol else None

    result = {"verified": False, "reason": "", "auto": True}

    if service in ("retweet", "like_rt"):
        # Verify the KOL retweeted the target tweet
        if not target_tweet_id:
            result["reason"] = "Campaign has no target tweet to verify against."
            result["auto"] = False
            return result

        if kol_x_user_id:
            retweeters = await x_api.get_retweeters(target_tweet_id)
            if kol_x_user_id in retweeters:
                result["verified"] = True
                result["reason"] = "Retweet verified."
            else:
                result["reason"] = "Retweet not detected. It may take time to propagate."
                result["auto"] = False

            if service == "like_rt" and result["verified"]:
                likers = await x_api.get_liking_users(target_tweet_id)
                if kol_x_user_id not in likers:
                    result["verified"] = False
                    result["reason"] = "Like not detected on target tweet."
                    result["auto"] = False
        else:
            result["reason"] = "KOL X account not verified — manual review needed."
            result["auto"] = False

    elif service == "quote_tweet":
        tweet = await x_api.get_tweet(tweet_id)
        if tweet:
            refs = tweet.get("referenced_tweets", [])
            is_qt = any(
                r.get("type") == "quoted" and r.get("id") == target_tweet_id
                for r in refs
            )
            if is_qt:
                result["verified"] = True
                result["reason"] = "Quote tweet verified."
            else:
                result["reason"] = "Tweet does not quote the target tweet."
                result["auto"] = False
        else:
            result["reason"] = "Could not fetch tweet data."
            result["auto"] = False

    else:
        # original_post, thread, video_post — verify tweet exists and author matches
        tweet = await x_api.get_tweet(tweet_id)
        if tweet and kol_x_user_id and tweet.get("author_id") == kol_x_user_id:
            result["verified"] = True
            result["reason"] = "Tweet authorship verified."
        else:
            result["reason"] = "Could not auto-verify authorship — manual review needed."
            result["auto"] = False

    # Save verification result
    verification_json = json.dumps(result)
    if result["verified"]:
        acceptance_repo.update_acceptance_status(
            acceptance_id, "verified",
            extra_fields={
                "verification_result": verification_json,
                "verified_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )
        # Check if all KOLs verified → complete campaign
        _check_campaign_completion(campaign["id"])
    else:
        acceptance_repo.update_acceptance_status(
            acceptance_id, "submitted",
            extra_fields={"verification_result": verification_json},
        )

    return result


def manually_verify(acceptance_id: int) -> bool:
    """Admin manually verifies a submission."""
    acceptance = acceptance_repo.get_acceptance_by_id(acceptance_id)
    if not acceptance or acceptance["status"] not in ("submitted",):
        return False

    from datetime import datetime
    result_json = json.dumps({"verified": True, "reason": "Manually verified by admin.", "auto": False})
    acceptance_repo.update_acceptance_status(
        acceptance_id, "verified",
        extra_fields={
            "verification_result": result_json,
            "verified_at": datetime.utcnow().isoformat(),
        },
    )

    _check_campaign_completion(acceptance["campaign_id"])
    return True


def manually_reject(acceptance_id: int) -> bool:
    """Admin manually rejects a submission."""
    acceptance = acceptance_repo.get_acceptance_by_id(acceptance_id)
    if not acceptance or acceptance["status"] not in ("submitted",):
        return False

    result_json = json.dumps({"verified": False, "reason": "Rejected by admin.", "auto": False})
    acceptance_repo.update_acceptance_status(
        acceptance_id, "rejected",
        extra_fields={"verification_result": result_json},
    )
    return True


def _check_campaign_completion(campaign_id: int):
    """If all accepted KOLs are verified, mark campaign complete."""
    campaign = campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign["status"] not in ("live", "filled"):
        return
    verified_count = acceptance_repo.count_verified_for_campaign(campaign_id)
    if verified_count >= campaign["kol_count"]:
        complete_campaign(campaign_id)
