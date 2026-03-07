"""X (Twitter) posting module for Deal Alert Bot.

Auto-posts deal alerts to X when a deal is found. Requires X API
credentials configured in .env (see .env.example for setup).
"""

import logging
import tweepy
from config import (
    X_API_KEY, X_API_SECRET,
    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
    X_POST_ENABLED,
)
from url_safety import sanitize_url

logger = logging.getLogger("DealBot.XPoster")

# Tweet character limit (URLs count as 23 chars via t.co wrapping)
MAX_TWEET_LEN = 280
URL_DISPLAY_LEN = 23


def _get_client():
    """Create an authenticated X API v2 client."""
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        return None
    return tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )


def _truncate(text, max_len):
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _format_price_drop_tweet(product, old_price, new_price, drop_percent):
    """Build a tweet for a price-drop alert."""
    savings = old_price - new_price
    title = product.get("title", "Deal")
    store = product.get("site", "").title()
    url = sanitize_url(product.get("affiliate_url")) or sanitize_url(product.get("url"))
    if not url:
        return None

    is_all_time_low = (
        product.get("lowest_price") and new_price <= product["lowest_price"]
    )

    # Build the tweet body (URL always takes 23 chars)
    lines = []
    if drop_percent >= 50:
        lines.append("HUGE PRICE DROP")
    elif drop_percent >= 30:
        lines.append("PRICE DROP")
    else:
        lines.append("Deal Alert")

    if is_all_time_low:
        lines[0] += " - ALL-TIME LOW"

    lines.append("")
    lines.append(title)
    if store:
        lines.append(f"at {store}")
    lines.append(f"${old_price:.2f} -> ${new_price:.2f} ({drop_percent:.0f}% off, save ${savings:.2f})")
    lines.append("")
    lines.append(url)
    lines.append("")
    lines.append("#deals #savings")

    tweet = "\n".join(lines)

    # Ensure it fits within 280 chars (URL counted as 23)
    non_url = tweet.replace(url, "")
    available = MAX_TWEET_LEN - URL_DISPLAY_LEN
    if len(non_url) > available:
        # Shorten the title to fit
        excess = len(non_url) - available
        short_title = _truncate(title, max(20, len(title) - excess))
        tweet = tweet.replace(title, short_title)

    return tweet


def _format_aggregator_tweet(deal):
    """Build a tweet for an aggregator/lifestyle deal."""
    title = deal.get("title", "Deal")
    price = deal.get("price")
    original_price = deal.get("original_price")
    store = deal.get("store", "")
    url = sanitize_url(deal.get("url"))
    if not url:
        return None

    lines = ["HOT DEAL", ""]
    lines.append(title)
    if store:
        lines.append(f"at {store}")

    if price and original_price and original_price > price:
        pct = ((original_price - price) / original_price) * 100
        lines.append(f"${original_price:.2f} -> ${price:.2f} ({pct:.0f}% off)")
    elif price:
        lines.append(f"${price:.2f}")

    lines.append("")
    lines.append(url)
    lines.append("")
    lines.append("#deals #savings")

    tweet = "\n".join(lines)

    non_url = tweet.replace(url, "")
    available = MAX_TWEET_LEN - URL_DISPLAY_LEN
    if len(non_url) > available:
        excess = len(non_url) - available
        short_title = _truncate(title, max(20, len(title) - excess))
        tweet = tweet.replace(title, short_title)

    return tweet


def post_deal_to_x(product, old_price, new_price, drop_percent):
    """Post a price-drop deal to X. Returns True on success."""
    if not X_POST_ENABLED:
        return False

    client = _get_client()
    if not client:
        logger.warning("X API not configured - skipping X post")
        return False

    tweet = _format_price_drop_tweet(product, old_price, new_price, drop_percent)
    if not tweet:
        logger.warning("Could not format tweet for product: %s", product.get("title"))
        return False

    try:
        client.create_tweet(text=tweet)
        logger.info("Posted deal to X: %s", product.get("title", "")[:50])
        print(f"[X] Posted deal: {product.get('title', '')[:50]}")
        return True
    except tweepy.TweepyException as e:
        logger.error("Failed to post to X: %s", e)
        print(f"[X] Failed to post: {e}")
        return False


def post_aggregator_deal_to_x(deal):
    """Post an aggregator deal to X. Returns True on success."""
    if not X_POST_ENABLED:
        return False

    client = _get_client()
    if not client:
        logger.warning("X API not configured - skipping X post")
        return False

    tweet = _format_aggregator_tweet(deal)
    if not tweet:
        logger.warning("Could not format tweet for deal: %s", deal.get("title"))
        return False

    try:
        client.create_tweet(text=tweet)
        logger.info("Posted aggregator deal to X: %s", deal.get("title", "")[:50])
        print(f"[X] Posted deal: {deal.get('title', '')[:50]}")
        return True
    except tweepy.TweepyException as e:
        logger.error("Failed to post to X: %s", e)
        print(f"[X] Failed to post: {e}")
        return False
