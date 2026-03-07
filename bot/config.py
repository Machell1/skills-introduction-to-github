"""Configuration loader for Deal Alert Bot."""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHANNEL_HANDLE = os.getenv("TELEGRAM_CHANNEL_HANDLE", "@dailydeals")

# Admin user IDs (comma-separated Telegram user IDs allowed to control the bot)
ADMIN_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]

# Affiliate Tags
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "yourtag-20")
WALMART_AFFILIATE_TAG = os.getenv("WALMART_AFFILIATE_TAG", "")
TARGET_AFFILIATE_TAG = os.getenv("TARGET_AFFILIATE_TAG", "")
BESTBUY_AFFILIATE_TAG = os.getenv("BESTBUY_AFFILIATE_TAG", "")
EBAY_AFFILIATE_CAMPAIGN_ID = os.getenv("EBAY_AFFILIATE_CAMPAIGN_ID", "")

# Lifestyle/Travel Affiliate Tags
GROUPON_AFFILIATE_TAG = os.getenv("GROUPON_AFFILIATE_TAG", "")
SKYSCANNER_AFFILIATE_TAG = os.getenv("SKYSCANNER_AFFILIATE_TAG", "")
EXPEDIA_AFFILIATE_TAG = os.getenv("EXPEDIA_AFFILIATE_TAG", "")

# Scheduling
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

# Deal thresholds
MIN_DROP_PERCENT = float(os.getenv("MIN_DROP_PERCENT", "15"))
MIN_DROP_DOLLARS = float(os.getenv("MIN_DROP_DOLLARS", "5"))

# Database
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "deals.db"))

# Scraper settings
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
