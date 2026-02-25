import os

from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ANNOUNCEMENT_CHANNEL_ID = os.getenv("ANNOUNCEMENT_CHANNEL_ID", "")
ADMIN_TELEGRAM_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if x.strip().isdigit()
]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Game4Charity")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- X API ---
X_API_BEARER_TOKEN = os.getenv("X_API_BEARER_TOKEN", "")

# --- App constants ---
CHANNEL_LINK = "https://t.me/+UV2UD42DM5gwZjFh"
POSTER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poster.png")

PLATFORM_FEE_PERCENT = 15  # 15%

# Service tiers: (display_name, per_kol_rate_cents, min_kols, max_kols)
SERVICE_TIERS = {
    "retweet":       ("Retweet",       1000,  5, 50),
    "like_rt":       ("Like + RT",     1500,  5, 50),
    "quote_tweet":   ("Quote Tweet",   3000,  3, 30),
    "original_post": ("Original Post", 5000,  3, 25),
    "thread":        ("Thread",        10000, 2, 15),
    "video_post":    ("Video Post",    15000, 1, 10),
}

# Services that require a target tweet URL (the tweet to RT/QT)
SERVICES_REQUIRING_TARGET = {"retweet", "like_rt", "quote_tweet"}

# Services that require talking points
SERVICES_REQUIRING_TALKING_POINTS = {"quote_tweet", "original_post", "thread", "video_post"}

CAMPAIGN_STATUSES = [
    "pending_payment",
    "live",
    "filled",
    "completed",
    "expired",
    "cancelled",
]
