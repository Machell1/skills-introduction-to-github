"""Telegram notification system for deal alerts across multiple sites."""

import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

SITE_LABELS = {
    "amazon": "Amazon",
    "bestbuy": "Best Buy",
    "walmart": "Walmart",
    "target": "Target",
    "slickdeals": "Slickdeals",
    "dealnews": "DealNews",
    "ebay": "eBay",
    "groupon": "Groupon",
    "skyscanner": "Skyscanner",
    "expedia": "Expedia",
}

CATEGORY_EMOJI = {
    "flights": "✈️",
    "holiday_packages": "🏖️",
    "birthday": "🎂",
    "party": "🎉",
    "wedding": "💍",
    "baby_shower": "👶",
    "gifts": "🎁",
}


def _site_label(site):
    return SITE_LABELS.get(site, site.title() if site else "Store")


def format_deal_message(product, old_price, new_price, drop_percent):
    """Format a price drop alert message."""
    savings = old_price - new_price
    site = _site_label(product.get("site", ""))

    if drop_percent >= 50:
        fire = "🔥🔥🔥"
    elif drop_percent >= 30:
        fire = "🔥🔥"
    else:
        fire = "🔥"

    buy_url = product.get("affiliate_url") or product.get("url", "#")

    message = (
        f"{fire} <b>PRICE DROP ALERT</b> {fire}\n"
        f"\n"
        f"<b>{product['title']}</b>\n"
        f"🏪 {site}\n"
        f"\n"
        f"💰 <s>${old_price:.2f}</s> → <b>${new_price:.2f}</b>\n"
        f"📉 Save ${savings:.2f} ({drop_percent:.0f}% off)\n"
    )

    if product.get("lowest_price") and new_price <= product["lowest_price"]:
        message += f"⭐ <b>ALL-TIME LOW PRICE!</b>\n"

    message += (
        f"\n"
        f'<a href="{buy_url}">🛒 Buy Now on {site}</a>\n'
        f"\n"
        f"<i>Prices may change. Act fast!</i>"
    )

    return message


def format_new_product_message(product):
    """Format a message for when a new product is added to tracking."""
    price_str = f"${product['price']:.2f}" if product.get("price") else "Price unavailable"
    site = _site_label(product.get("site", ""))
    buy_url = product.get("affiliate_url") or product.get("url", "#")

    message = (
        f"📌 <b>Now Tracking</b>\n"
        f"\n"
        f"<b>{product['title']}</b>\n"
        f"🏪 {site}\n"
        f"💰 Current price: <b>{price_str}</b>\n"
        f"\n"
        f'<a href="{buy_url}">View on {site}</a>'
    )

    return message


def format_aggregator_deal(deal):
    """Format a deal found by an aggregator or lifestyle scraper."""
    title = deal.get("title", "Deal")
    price = deal.get("price")
    original_price = deal.get("original_price")
    store = deal.get("store", "")
    source = _site_label(deal.get("site", ""))
    url = deal.get("url", "#")
    category = deal.get("category", "")

    cat_emoji = CATEGORY_EMOJI.get(category, "🏷️")
    message = f"{cat_emoji} <b>HOT DEAL</b>\n\n"
    message += f"<b>{title}</b>\n"

    if store:
        message += f"🏪 {store}\n"

    if price and original_price and original_price > price:
        savings = original_price - price
        pct = (savings / original_price) * 100
        message += f"💰 <s>${original_price:.2f}</s> → <b>${price:.2f}</b> ({pct:.0f}% off)\n"
    elif price:
        message += f"💰 <b>${price:.2f}</b>\n"

    if deal.get("score"):
        message += f"👍 Score: {deal['score']}\n"

    message += f"\n<a href=\"{url}\">🛒 Get This Deal</a>\n"
    message += f"\n<i>via {source}</i>"

    return message


async def _send_message(text):
    """Internal async send."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print(f"[Notifier] Telegram not configured. Message:\n{text}\n")
        return False

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
        print(f"[Notifier] Alert sent to {TELEGRAM_CHANNEL_ID}")
        return True
    except Exception as e:
        print(f"[Notifier] Failed to send: {e}")
        return False


def send_deal_alert(product, old_price, new_price, drop_percent):
    """Send a price drop alert to the Telegram channel."""
    message = format_deal_message(product, old_price, new_price, drop_percent)
    return asyncio.run(_send_message(message))


def send_tracking_notification(product):
    """Send a notification that a new product is being tracked."""
    message = format_new_product_message(product)
    return asyncio.run(_send_message(message))


def send_aggregator_deal(deal):
    """Send a deal found by an aggregator."""
    message = format_aggregator_deal(deal)
    return asyncio.run(_send_message(message))


def send_custom_message(text):
    """Send a custom message to the channel."""
    return asyncio.run(_send_message(text))
