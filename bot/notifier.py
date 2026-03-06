"""Telegram notification system for deal alerts."""

import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID


def format_deal_message(product, old_price, new_price, drop_percent):
    """Format a deal alert message for Telegram."""
    savings = old_price - new_price

    # Price drop severity emoji
    if drop_percent >= 50:
        fire = "🔥🔥🔥"
    elif drop_percent >= 30:
        fire = "🔥🔥"
    else:
        fire = "🔥"

    message = (
        f"{fire} <b>PRICE DROP ALERT</b> {fire}\n"
        f"\n"
        f"<b>{product['title']}</b>\n"
        f"\n"
        f"💰 <s>${old_price:.2f}</s> → <b>${new_price:.2f}</b>\n"
        f"📉 Save ${savings:.2f} ({drop_percent:.0f}% off)\n"
    )

    if product.get("lowest_price") and new_price <= product["lowest_price"]:
        message += f"⭐ <b>ALL-TIME LOW PRICE!</b>\n"

    message += (
        f"\n"
        f'<a href="{product["affiliate_url"]}">🛒 Buy Now on Amazon</a>\n'
        f"\n"
        f"<i>Prices may change. Act fast!</i>"
    )

    return message


def format_new_product_message(product):
    """Format a message for when a new product is added to tracking."""
    price_str = f"${product['price']:.2f}" if product.get("price") else "Price unavailable"

    message = (
        f"📌 <b>Now Tracking</b>\n"
        f"\n"
        f"<b>{product['title']}</b>\n"
        f"💰 Current price: <b>{price_str}</b>\n"
        f"\n"
        f'<a href="{product["affiliate_url"]}">View on Amazon</a>'
    )

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
    """Send a deal alert to the Telegram channel."""
    message = format_deal_message(product, old_price, new_price, drop_percent)
    return asyncio.run(_send_message(message))


def send_tracking_notification(product):
    """Send a notification that a new product is being tracked."""
    message = format_new_product_message(product)
    return asyncio.run(_send_message(message))


def send_custom_message(text):
    """Send a custom message to the channel."""
    return asyncio.run(_send_message(text))
