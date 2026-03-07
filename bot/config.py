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

# Revenue estimation defaults
DEFAULT_CONVERSION_RATE = float(os.getenv("DEFAULT_CONVERSION_RATE", "0.02"))  # 2% of clicks buy
DEFAULT_CTR = float(os.getenv("DEFAULT_CTR", "0.05"))  # 5% of viewers click (fallback)

# Affiliate network API credentials
IMPACT_ACCOUNT_SID = os.getenv("IMPACT_ACCOUNT_SID", "")
IMPACT_AUTH_TOKEN = os.getenv("IMPACT_AUTH_TOKEN", "")
CJ_DEVELOPER_KEY = os.getenv("CJ_DEVELOPER_KEY", "")
CJ_WEBSITE_ID = os.getenv("CJ_WEBSITE_ID", "")
EBAY_PARTNER_KEY = os.getenv("EBAY_PARTNER_KEY", "")

# X (Twitter)
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_POST_ENABLED = os.getenv("X_POST_ENABLED", "false").lower() == "true"

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
