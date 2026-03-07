"""Telegram notification system for deal alerts across multiple sites."""

import asyncio
import logging
from urllib.parse import quote
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    TELEGRAM_CHANNEL_HANDLE, ADMIN_USER_IDS,
)
from url_safety import validate_deal, validate_product, sanitize_url
from x_poster import post_deal_to_x, post_aggregator_deal_to_x

logger = logging.getLogger("DealBot.Notifier")

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
    """Format a price drop alert message. Returns None if product fails safety checks."""
    is_valid, reason = validate_product(product)
    if not is_valid:
        logger.warning("Blocked unsafe product alert: %s", reason)
        return None

    savings = old_price - new_price
    site = _site_label(product.get("site", ""))

    if drop_percent >= 50:
        fire = "🔥🔥🔥"
    elif drop_percent >= 30:
        fire = "🔥🔥"
    else:
        fire = "🔥"

    buy_url = sanitize_url(product.get("affiliate_url")) or sanitize_url(product.get("url")) or None
    if not buy_url:
        logger.warning("Blocked untrusted URL in price alert: %s", product.get("url"))
        return None

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
        f"<i>Prices may change. Act fast!</i>\n"
        f"\n"
        f"📢 Join {TELEGRAM_CHANNEL_HANDLE} for more deals!"
    )

    return message


def format_new_product_message(product):
    """Format a message for when a new product is added to tracking. Returns None if unsafe."""
    is_valid, reason = validate_product(product)
    if not is_valid:
        logger.warning("Blocked unsafe product tracking message: %s", reason)
        return None

    price_str = f"${product['price']:.2f}" if product.get("price") else "Price unavailable"
    site = _site_label(product.get("site", ""))
    buy_url = sanitize_url(product.get("affiliate_url")) or sanitize_url(product.get("url")) or None
    if not buy_url:
        logger.warning("Blocked untrusted URL in tracking message: %s", product.get("url"))
        return None

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
    """Format a deal found by an aggregator or lifestyle scraper. Returns None if unsafe."""
    is_valid, reason = validate_deal(deal)
    if not is_valid:
        logger.warning("Blocked unsafe aggregator deal: %s", reason)
        return None

    title = deal.get("title", "Deal")
    price = deal.get("price")
    original_price = deal.get("original_price")
    store = deal.get("store", "")
    source = _site_label(deal.get("site", ""))
    url = sanitize_url(deal.get("url")) or None
    if not url:
        logger.warning("Blocked untrusted URL in aggregator deal: %s", deal.get("url"))
        return None
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
    message += f"\n<i>via {source}</i>\n"
    message += f"\n📢 Join {TELEGRAM_CHANNEL_HANDLE} for more deals!"

    return message


def _deal_keyboard(url, deal_id=None):
    """Create an inline keyboard with Buy and Share buttons for a deal."""
    buttons = []
    if deal_id is not None:
        buttons.append([InlineKeyboardButton("🛒 Get This Deal", callback_data=f"buy:{deal_id}")])
    share_url = f"https://t.me/share/url?url={quote(url, safe='')}"
    buttons.append([InlineKeyboardButton("📤 Share This Deal", url=share_url)])
    return InlineKeyboardMarkup(buttons)


async def _send_message(text, reply_markup=None):
    """Internal async send to channel."""
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
            reply_markup=reply_markup,
        )
        print(f"[Notifier] Alert sent to {TELEGRAM_CHANNEL_ID}")
        return True
    except Exception as e:
        print(f"[Notifier] Failed to send: {e}")
        return False


async def _send_admin_message(text):
    """Send a status message to all admin users via DM."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_USER_IDS:
        print(f"[Notifier] Admin message (no admins configured): {text}")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    for uid in ADMIN_USER_IDS:
        try:
            await bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to DM admin %s: %s", uid, e)


def send_admin_message(text):
    """Send a status message to all admins (sync wrapper)."""
    try:
        asyncio.run(_send_admin_message(text))
    except RuntimeError:
        # Event loop already running (called from async context)
        pass


def send_deal_alert(product, old_price, new_price, drop_percent, deal_id=None):
    """Send a price drop alert to Telegram and X. Blocks unsafe links."""
    message = format_deal_message(product, old_price, new_price, drop_percent)
    if not message:
        return False
    url = product.get("affiliate_url") or product.get("url", "")
    keyboard = _deal_keyboard(url, deal_id) if url else None
    tg_ok = asyncio.run(_send_message(message, reply_markup=keyboard))
    # Cross-post to X
    post_deal_to_x(product, old_price, new_price, drop_percent)
    return tg_ok


def send_tracking_notification(product):
    """Send a notification that a new product is being tracked. Blocks unsafe links."""
    message = format_new_product_message(product)
    if not message:
        return False
    return asyncio.run(_send_message(message))


def send_aggregator_deal(deal, deal_id=None):
    """Send a deal found by an aggregator to Telegram and X. Blocks unsafe links."""
    message = format_aggregator_deal(deal)
    if not message:
        return False
    url = deal.get("url", "")
    keyboard = _deal_keyboard(url, deal_id) if url else None
    tg_ok = asyncio.run(_send_message(message, reply_markup=keyboard))
    # Cross-post to X
    post_aggregator_deal_to_x(deal)
    return tg_ok


def send_custom_message(text):
    """Send a custom message to the channel."""
    return asyncio.run(_send_message(text))
