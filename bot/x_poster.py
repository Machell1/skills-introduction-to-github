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

STORE_HASHTAGS = {
    "amazon": "#AmazonDeals",
    "bestbuy": "#BestBuy",
    "walmart": "#Walmart",
    "target": "#Target",
    "ebay": "#eBay",
    "slickdeals": "#Slickdeals",
    "dealnews": "#DealNews",
    "groupon": "#Groupon",
    "skyscanner": "#flights",
    "expedia": "#travel",
}

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
    store_tag = STORE_HASHTAGS.get(product.get("site", "").lower(), "")
    lines.append("")
    lines.append(url)
    lines.append("")
    lines.append(f"#deals #savings {store_tag}".strip())

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

    store_tag = STORE_HASHTAGS.get(deal.get("site", "").lower(), "")
    lines.append("")
    lines.append(url)
    lines.append("")
    lines.append(f"#deals #savings {store_tag}".strip())

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


# ===== Daily Tool Spotlight =====

# AI tools data for daily spotlight rotation
SPOTLIGHT_TOOLS = [
    {"name": "ChatGPT", "tagline": "The most popular AI chatbot by OpenAI", "rating": 4.8, "pricing": "Free / $20 mo", "slug": "chatgpt"},
    {"name": "Claude", "tagline": "Thoughtful AI assistant by Anthropic", "rating": 4.7, "pricing": "Free / $20 mo", "slug": "claude"},
    {"name": "Midjourney", "tagline": "Create stunning AI-generated artwork", "rating": 4.9, "pricing": "From $10/mo", "slug": "midjourney"},
    {"name": "GitHub Copilot", "tagline": "AI pair programmer for your IDE", "rating": 4.7, "pricing": "From $10/mo", "slug": "github-copilot"},
    {"name": "Cursor", "tagline": "The AI-first code editor", "rating": 4.8, "pricing": "Free / $20 mo", "slug": "cursor"},
    {"name": "Jasper", "tagline": "AI marketing content platform", "rating": 4.5, "pricing": "From $49/mo", "slug": "jasper"},
    {"name": "Copy.ai", "tagline": "AI-powered copywriting made easy", "rating": 4.4, "pricing": "Free / $36 mo", "slug": "copy-ai"},
    {"name": "Runway", "tagline": "AI-powered video creation and editing", "rating": 4.6, "pricing": "Free / $12 mo", "slug": "runway"},
    {"name": "Synthesia", "tagline": "Create AI videos with digital avatars", "rating": 4.5, "pricing": "From $22/mo", "slug": "synthesia"},
    {"name": "Notion AI", "tagline": "AI writing assistant built into Notion", "rating": 4.4, "pricing": "$10/member/mo", "slug": "notion-ai"},
    {"name": "Otter.ai", "tagline": "AI meeting transcription and notes", "rating": 4.3, "pricing": "Free / $17 mo", "slug": "otter-ai"},
    {"name": "Canva AI", "tagline": "AI-powered design for everyone", "rating": 4.6, "pricing": "Free / $13 mo", "slug": "canva-ai"},
    {"name": "Grammarly", "tagline": "AI writing assistant for error-free content", "rating": 4.6, "pricing": "Free / $12 mo", "slug": "grammarly"},
    {"name": "DALL-E 3", "tagline": "OpenAI's text-to-image AI model", "rating": 4.5, "pricing": "Free (Bing) / $20 mo", "slug": "dall-e"},
    {"name": "Perplexity AI", "tagline": "AI-powered search and research assistant", "rating": 4.6, "pricing": "Free / $20 mo", "slug": "perplexity"},
    {"name": "ElevenLabs", "tagline": "Realistic AI voice generation and cloning", "rating": 4.7, "pricing": "Free / $5 mo", "slug": "elevenlabs"},
    {"name": "Leonardo.ai", "tagline": "AI image generation with fine control", "rating": 4.5, "pricing": "Free / $12 mo", "slug": "leonardo-ai"},
    {"name": "Surfer SEO", "tagline": "AI-powered SEO content optimization", "rating": 4.5, "pricing": "From $89/mo", "slug": "surfer-seo"},
]

SITE_BASE_URL = "https://machell1.github.io/skills-introduction-to-github"


def _get_spotlight_index():
    """Get today's tool index based on the day of year (rotates through all tools)."""
    import datetime
    day_of_year = datetime.datetime.utcnow().timetuple().tm_yday
    return day_of_year % len(SPOTLIGHT_TOOLS)


def post_daily_tool_spotlight():
    """Post a daily AI tool spotlight to X. Returns True on success."""
    if not X_POST_ENABLED:
        return False

    client = _get_client()
    if not client:
        logger.warning("X API not configured - skipping spotlight")
        return False

    tool = SPOTLIGHT_TOOLS[_get_spotlight_index()]
    review_url = f"{SITE_BASE_URL}/tools/{tool['slug']}.html"

    tweet = (
        f"AI Tool of the Day: {tool['name']}\n\n"
        f"{tool['tagline']}\n\n"
        f"Rating: {tool['rating']}/5\n"
        f"Pricing: {tool['pricing']}\n\n"
        f"Full review: {review_url}\n\n"
        f"#AI #AITools #TechReview"
    )

    # Truncate if needed
    non_url = tweet.replace(review_url, "")
    if len(non_url) + URL_DISPLAY_LEN > MAX_TWEET_LEN:
        excess = len(non_url) + URL_DISPLAY_LEN - MAX_TWEET_LEN
        short_tagline = _truncate(tool["tagline"], max(15, len(tool["tagline"]) - excess))
        tweet = tweet.replace(tool["tagline"], short_tagline)

    try:
        client.create_tweet(text=tweet)
        logger.info("Posted daily spotlight to X: %s", tool["name"])
        print(f"[X] Posted spotlight: {tool['name']}")
        return True
    except tweepy.TweepyException as e:
        logger.error("Failed to post spotlight to X: %s", e)
        print(f"[X] Failed to post spotlight: {e}")
        return False


def get_daily_spotlight_telegram():
    """Get the daily spotlight formatted for Telegram. Returns HTML string."""
    tool = SPOTLIGHT_TOOLS[_get_spotlight_index()]
    review_url = f"{SITE_BASE_URL}/tools/{tool['slug']}.html"

    return (
        f"🌟 <b>AI Tool of the Day</b> 🌟\n\n"
        f"<b>{tool['name']}</b>\n"
        f"{tool['tagline']}\n\n"
        f"⭐ Rating: {tool['rating']}/5\n"
        f"💰 Pricing: {tool['pricing']}\n\n"
        f'<a href="{review_url}">📖 Read Full Review</a>\n\n'
        f"Know someone who'd find this useful? Forward this message!\n\n"
        f"📢 Follow @dailydeals for daily AI tool spotlights and deals!"
    )


def post_weekly_roundup_to_x(deals):
    """Post a weekly roundup of top deals to X. deals = list of dicts with title, savings_pct, store."""
    if not X_POST_ENABLED:
        return False

    client = _get_client()
    if not client:
        return False

    if not deals:
        return False

    lines = ["This Week's Best Deals\n"]
    for i, d in enumerate(deals[:5], 1):
        title = _truncate(d.get("title", "Deal"), 40)
        pct = d.get("savings_pct", 0)
        store = d.get("store", "")
        line = f"{i}. {title}"
        if store:
            line += f" ({store})"
        if pct:
            line += f" - {pct:.0f}% off"
        lines.append(line)

    lines.append("")
    lines.append(f"More deals daily: {SITE_BASE_URL}")
    lines.append("")
    lines.append("#deals #savings #WeeklyRoundup")

    tweet = "\n".join(lines)

    # Truncate if too long
    non_url = tweet.replace(SITE_BASE_URL, "")
    if len(non_url) + URL_DISPLAY_LEN > MAX_TWEET_LEN:
        # Reduce to top 3
        lines = ["This Week's Top 3 Deals\n"]
        for i, d in enumerate(deals[:3], 1):
            title = _truncate(d.get("title", "Deal"), 35)
            pct = d.get("savings_pct", 0)
            line = f"{i}. {title}"
            if pct:
                line += f" - {pct:.0f}% off"
            lines.append(line)
        lines.append(f"\n{SITE_BASE_URL}\n#deals #savings")
        tweet = "\n".join(lines)

    try:
        client.create_tweet(text=tweet)
        logger.info("Posted weekly roundup to X")
        print("[X] Posted weekly roundup")
        return True
    except tweepy.TweepyException as e:
        logger.error("Failed to post weekly roundup to X: %s", e)
        return False
