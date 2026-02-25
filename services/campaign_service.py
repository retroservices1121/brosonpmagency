"""Campaign lifecycle management."""
import logging
from datetime import datetime

from config import PLATFORM_FEE_PERCENT
from db.tier_repo import get_all_tiers
from db import campaign_repo

logger = logging.getLogger(__name__)


def calculate_pricing(service_type: str, kol_count: int) -> dict:
    """Calculate campaign cost. Returns dict with per_kol_rate, platform_fee, total_cost (all in cents)."""
    tiers = get_all_tiers()
    tier = tiers[service_type]
    per_kol_rate = tier[1]
    subtotal = per_kol_rate * kol_count
    platform_fee = int(subtotal * PLATFORM_FEE_PERCENT / 100)
    total_cost = subtotal + platform_fee
    return {
        "per_kol_rate": per_kol_rate,
        "platform_fee": platform_fee,
        "total_cost": total_cost,
    }


def create_campaign(data: dict) -> int:
    """Create a new campaign in pending_payment status. Returns campaign id."""
    pricing = calculate_pricing(data["service_type"], data["kol_count"])
    data.update(pricing)
    campaign_id = campaign_repo.create_campaign(data)
    logger.info("Campaign #%d created by user %s", campaign_id, data["customer_telegram_id"])
    return campaign_id


def activate_campaign(campaign_id: int) -> dict | None:
    """Transition campaign from pending_payment → live."""
    campaign = campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign["status"] != "pending_payment":
        return None
    campaign_repo.update_campaign_status(
        campaign_id, "live",
        extra_fields={"activated_at": datetime.utcnow().isoformat()},
    )
    logger.info("Campaign #%d activated", campaign_id)
    return campaign_repo.get_campaign(campaign_id)


def fill_campaign(campaign_id: int):
    """Transition campaign to filled status when all KOL slots are taken."""
    campaign_repo.update_campaign_status(campaign_id, "filled")
    logger.info("Campaign #%d filled", campaign_id)


def complete_campaign(campaign_id: int):
    """Mark campaign as completed when all KOLs verified."""
    campaign_repo.update_campaign_status(
        campaign_id, "completed",
        extra_fields={"completed_at": datetime.utcnow().isoformat()},
    )
    logger.info("Campaign #%d completed", campaign_id)


def expire_campaigns():
    """Expire all live/filled campaigns past their deadline. Returns count."""
    now = datetime.utcnow().isoformat()
    expired = campaign_repo.get_expired_campaigns(now)
    for c in expired:
        campaign_repo.update_campaign_status(c["id"], "expired")
        logger.info("Campaign #%d expired", c["id"])
    return len(expired)


def cancel_campaign(campaign_id: int) -> bool:
    campaign = campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign["status"] not in ("pending_payment", "live"):
        return False
    campaign_repo.update_campaign_status(campaign_id, "cancelled")
    logger.info("Campaign #%d cancelled", campaign_id)
    return True
