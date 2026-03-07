"""Deal Alert Bot - Telegram Bot Interface

Run this file to start the bot as a Telegram bot with command handlers
and scheduled price checking. Deploy on Railway for 24/7 uptime.

Commands:
    /start, /help    - Show help and tracking stats
    /add <url>       - Track a product from any supported site
    /remove <id>     - Stop tracking a product
    /status          - Show all tracked products
    /check           - Check all prices now
    /deals           - Scan deal aggregators now
    /lifestyle       - Scan flights, gifts, events, packages
    /flights         - Flight deals only
    /birthday        - Birthday gift deals
    /wedding         - Wedding package deals
    /babyshower      - Baby shower deals
    /party           - Party deals
    /holidays        - Holiday/vacation packages
    /sites           - List supported sites
    /earnings [days] - View estimated affiliate revenue
    /revenue [days]  - View actual + estimated revenue
"""

import asyncio
import datetime
import logging
import functools
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    TELEGRAM_CHANNEL_HANDLE, CHECK_INTERVAL_MINUTES, ADMIN_USER_IDS,
)
from database import init_db, remove_product, record_referral, log_click, get_deal_by_id
from notifier import send_admin_message
from tracker import (
    check_all_prices, add_new_product, scan_deals,
    scan_all_deals, scan_lifestyle, scan_category, get_status_text,
    generate_daily_summary,
)
from earnings import format_earnings_report, format_revenue_report
from url_safety import is_trusted_url

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
        user = update.effective_user
        if not user or not update.message:
            return
        if ADMIN_USER_IDS and user.id not in ADMIN_USER_IDS:
            await update.message.reply_text("Not authorized.")
            return
        return await func(update, context)
    return wrapper


# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — public for all users, with referral tracking."""
    user = update.effective_user
    if not user or not update.message:
        return

    # Record referral if deep link parameter provided (e.g. ?start=ref_12345)
    if context.args:
        ref_code = context.args[0]
        record_referral(user.id, ref_code)

    is_admin = not ADMIN_USER_IDS or user.id in ADMIN_USER_IDS

    text = (
        "<b>Deal Alert Bot</b>\n\n"
        "I find the best deals across Amazon, Best Buy, Walmart, Target, "
        "eBay, and more — and send instant alerts when prices drop!\n\n"
        f"Join our channel {TELEGRAM_CHANNEL_HANDLE} for real-time deal alerts.\n"
    )

    if is_admin:
        text += (
            "\n<b>Admin Commands:</b>\n"
            "/add &lt;url&gt; - Track a product\n"
            "/remove &lt;id&gt; - Stop tracking\n"
            "/status - View tracked products\n"
            "/check - Check prices now\n"
            "/deals - Scan deal aggregators\n"
            "/lifestyle - Flights, gifts, events, packages\n"
            "/flights - Flight deals\n"
            "/birthday - Birthday gift deals\n"
            "/wedding - Wedding package deals\n"
            "/babyshower - Baby shower deals\n"
            "/party - Party deals\n"
            "/holidays - Holiday packages\n"
            "/sites - Supported sites\n"
            "/earnings - Estimated revenue\n"
            "/revenue - Actual + estimated revenue\n"
            "/help - Show this message\n\n"
            f"Price checks run every {CHECK_INTERVAL_MINUTES} minutes automatically."
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


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

    if not is_trusted_url(url):
        await update.message.reply_text(
            "That URL is not from a supported site.\n"
            "Only trusted stores are allowed (no shortened or unknown links).\n"
            "Use /sites to see supported stores."
        )
        return

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
async def lifestyle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lifestyle - scan all lifestyle deal sites."""
    await update.message.reply_text(
        "Scanning lifestyle deals (flights, gifts, events, packages)..."
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_lifestyle)
    await update.message.reply_text("Lifestyle deal scan complete.")


@admin_only
async def flights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /flights - scan flight deals."""
    await update.message.reply_text("Scanning flight deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "flights")
    await update.message.reply_text("Flight deal scan complete.")


@admin_only
async def birthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /birthday - scan birthday gift deals."""
    await update.message.reply_text("Scanning birthday gift deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "birthday")
    await update.message.reply_text("Birthday deal scan complete.")


@admin_only
async def wedding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wedding - scan wedding package deals."""
    await update.message.reply_text("Scanning wedding package deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "wedding")
    await update.message.reply_text("Wedding deal scan complete.")


@admin_only
async def babyshower_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /babyshower - scan baby shower deals."""
    await update.message.reply_text("Scanning baby shower deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "baby_shower")
    await update.message.reply_text("Baby shower deal scan complete.")


@admin_only
async def party_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /party - scan party deals."""
    await update.message.reply_text("Scanning party deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "party")
    await update.message.reply_text("Party deal scan complete.")


@admin_only
async def holidays_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /holidays - scan holiday/vacation packages."""
    await update.message.reply_text("Scanning holiday package deals...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_category, "holiday_packages")
    await update.message.reply_text("Holiday package scan complete.")


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
        "- DealNews (dealnews.com)\n\n"
        "<b>Lifestyle &amp; Travel:</b>\n"
        "- Groupon (gifts, parties, events)\n"
        "- Skyscanner (flights)\n"
        "- Expedia (holiday packages)"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def earnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /earnings [days] - show estimated affiliate revenue."""
    days = 1
    if context.args:
        try:
            days = max(1, int(context.args[0]))
        except ValueError:
            pass

    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, format_earnings_report, days)
    await update.message.reply_text(report, parse_mode=ParseMode.HTML)


@admin_only
async def revenue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /revenue [days] - show actual + estimated revenue combined."""
    days = 7
    if context.args:
        try:
            days = max(1, int(context.args[0]))
        except ValueError:
            pass

    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, format_revenue_report, days)
    await update.message.reply_text(report, parse_mode=ParseMode.HTML)


async def buy_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Get This Deal' button clicks — log the click and send the affiliate URL."""
    query = update.callback_query
    await query.answer()

    try:
        deal_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        return

    log_click(deal_id, query.from_user.id)

    deal = get_deal_by_id(deal_id)
    if deal and deal.get("affiliate_url"):
        from url_safety import sanitize_url
        safe_url = sanitize_url(deal["affiliate_url"])
        if safe_url:
            await query.message.reply_text(
                f'<a href="{safe_url}">Click here to buy</a>',
                parse_mode=ParseMode.HTML,
            )


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


async def scheduled_lifestyle_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: scan lifestyle deal sites (flights, gifts, events)."""
    logger.info("Scheduled lifestyle scan starting...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scan_lifestyle)
    logger.info("Scheduled lifestyle scan complete.")


async def scheduled_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: post top deals of the day to the channel."""
    logger.info("Generating daily summary...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, generate_daily_summary)
    logger.info("Daily summary complete.")


async def scheduled_earnings_report(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: send daily earnings estimate to admin."""
    logger.info("Generating daily earnings report...")
    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, format_earnings_report, 1)
    send_admin_message(report)
    logger.info("Daily earnings report sent.")


async def scheduled_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: send weekly earnings summary to admin (Mondays)."""
    logger.info("Generating weekly earnings report...")
    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, format_earnings_report, 7)
    send_admin_message(report)
    logger.info("Weekly earnings report sent.")


async def scheduled_api_poll(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: poll affiliate network APIs for real revenue data."""
    logger.info("Polling affiliate network APIs...")
    try:
        from affiliate_api import poll_all_networks
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, poll_all_networks, 2)
        logger.info("Affiliate API polling complete.")
    except Exception as e:
        logger.warning("Affiliate API polling failed: %s", e)


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
    app.add_handler(CommandHandler("lifestyle", lifestyle_command))
    app.add_handler(CommandHandler("flights", flights_command))
    app.add_handler(CommandHandler("birthday", birthday_command))
    app.add_handler(CommandHandler("wedding", wedding_command))
    app.add_handler(CommandHandler("babyshower", babyshower_command))
    app.add_handler(CommandHandler("party", party_command))
    app.add_handler(CommandHandler("holidays", holidays_command))
    app.add_handler(CommandHandler("sites", sites_command))
    app.add_handler(CommandHandler("earnings", earnings_command))
    app.add_handler(CommandHandler("revenue", revenue_command))
    app.add_handler(CallbackQueryHandler(buy_button_callback, pattern=r"^buy:"))

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
    job_queue.run_repeating(
        scheduled_lifestyle_scan,
        interval=CHECK_INTERVAL_MINUTES * 3 * 60,
        first=60,
    )
    job_queue.run_daily(
        scheduled_daily_summary,
        time=datetime.time(hour=18, minute=0),
    )
    job_queue.run_daily(
        scheduled_earnings_report,
        time=datetime.time(hour=21, minute=0),
    )
    job_queue.run_daily(
        scheduled_weekly_report,
        time=datetime.time(hour=10, minute=0),
        days=(0,),  # Monday only
    )
    job_queue.run_daily(
        scheduled_api_poll,
        time=datetime.time(hour=8, minute=0),
    )

    logger.info(
        "Bot started. Prices every %d min, deals every %d min, lifestyle every %d min.",
        CHECK_INTERVAL_MINUTES,
        CHECK_INTERVAL_MINUTES * 2,
        CHECK_INTERVAL_MINUTES * 3,
    )

    send_admin_message(
        f"🤖 <b>Deal Bot started</b>\n"
        f"📊 Price checks: every {CHECK_INTERVAL_MINUTES} min\n"
        f"🔍 Deal scans: every {CHECK_INTERVAL_MINUTES * 2} min\n"
        f"✈️ Lifestyle scans: every {CHECK_INTERVAL_MINUTES * 3} min\n"
        f"🏆 Daily summary: 6:00 PM UTC\n"
        f"💰 Earnings report: 9:00 PM UTC\n"
        f"📋 Weekly report: Mondays 10:00 AM UTC"
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
