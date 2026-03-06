"""Deal Alert Bot - Telegram Bot Interface

Run this file to start the bot as a Telegram bot with command handlers
and scheduled price checking. Deploy on Railway for 24/7 uptime.

Commands:
    /start, /help   - Show help and tracking stats
    /add <url>       - Track a product from any supported site
    /remove <id>     - Stop tracking a product
    /status          - Show all tracked products
    /check           - Check all prices now
    /deals           - Scan deal aggregators now
    /sites           - List supported sites
"""

import asyncio
import logging
import functools
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    CHECK_INTERVAL_MINUTES, ADMIN_USER_IDS,
)
from database import init_db, remove_product
from tracker import (
    check_all_prices, add_new_product, scan_deals,
    scan_all_deals, get_status_text,
)

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("DealBot")


# --- Admin-only decorator ---

def admin_only(func):
    """Restrict command to authorized admin users."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ADMIN_USER_IDS and update.effective_user.id not in ADMIN_USER_IDS:
            await update.message.reply_text("Not authorized.")
            return
        return await func(update, context)
    return wrapper


# --- Command Handlers ---

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and show welcome message."""
    text = (
        "<b>Deal Alert Bot</b>\n\n"
        "I monitor product prices across multiple stores and send alerts "
        "when prices drop.\n\n"
        "<b>Commands:</b>\n"
        "/add &lt;url&gt; - Track a product\n"
        "/remove &lt;id&gt; - Stop tracking\n"
        "/status - View tracked products\n"
        "/check - Check prices now\n"
        "/deals - Scan deal aggregators\n"
        "/sites - Supported sites\n"
        "/help - Show this message\n\n"
        f"Price checks run every {CHECK_INTERVAL_MINUTES} minutes automatically."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    await start_command(update, context)


@admin_only
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add <url> - add a product to track."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /add <url>\n\n"
            "Example:\n/add https://www.amazon.com/dp/B09V3KXJPB"
        )
        return

    url = context.args[0]
    await update.message.reply_text(f"Adding product from: {url}\nScraping...")

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, add_new_product, url)

    if success:
        await update.message.reply_text("Product added and tracking started.")
    else:
        await update.message.reply_text(
            "Failed to add product. Check the URL.\n"
            "Use /sites to see supported stores."
        )


@admin_only
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove <product_id> - stop tracking a product."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /remove <product_id>\n\n"
            "Use /status to see product IDs."
        )
        return

    product_id = context.args[0]
    remove_product(product_id)
    await update.message.reply_text(f"Stopped tracking: {product_id}")


@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status - show tracked products."""
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, get_status_text)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check - check all prices immediately."""
    await update.message.reply_text("Checking prices for all tracked products...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, check_all_prices)
    await update.message.reply_text("Price check complete.")


@admin_only
async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deals - scan deal aggregators."""
    await update.message.reply_text("Scanning Slickdeals & DealNews...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_deals)
    await update.message.reply_text("Deal scan complete.")


@admin_only
async def sites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sites - list supported sites."""
    text = (
        "<b>Supported Sites</b>\n\n"
        "<b>Product Tracking:</b>\n"
        "- Amazon (amazon.com)\n"
        "- Best Buy (bestbuy.com)\n"
        "- Walmart (walmart.com)\n"
        "- Target (target.com)\n"
        "- eBay (ebay.com)\n\n"
        "<b>Deal Aggregators:</b>\n"
        "- Slickdeals (slickdeals.net)\n"
        "- DealNews (dealnews.com)"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# --- Scheduled Jobs ---

async def scheduled_price_check(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: check all tracked product prices."""
    logger.info("Scheduled price check starting...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, check_all_prices)
    logger.info("Scheduled price check complete.")


async def scheduled_deal_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: scan deal aggregators."""
    logger.info("Scheduled deal scan starting...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_deals)
    logger.info("Scheduled deal scan complete.")


# --- Main ---

def run_bot():
    """Initialize and run the Telegram bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set. Check your .env file.")
        return

    init_db()
    logger.info("Database initialized.")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("deals", deals_command))
    app.add_handler(CommandHandler("sites", sites_command))

    # Register scheduled jobs
    job_queue = app.job_queue
    job_queue.run_repeating(
        scheduled_price_check,
        interval=CHECK_INTERVAL_MINUTES * 60,
        first=10,
    )
    job_queue.run_repeating(
        scheduled_deal_scan,
        interval=CHECK_INTERVAL_MINUTES * 2 * 60,
        first=30,
    )

    logger.info(
        "Bot started. Price checks every %d min, deal scans every %d min.",
        CHECK_INTERVAL_MINUTES,
        CHECK_INTERVAL_MINUTES * 2,
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
