"""Price tracker - monitors products across multiple sites and detects deals."""

from scraper import scrape_product, scrape_deal_aggregators, scrape_all_deals, scrape_lifestyle_deals, scrape_category_deals
from scrapers import get_scraper_for_url, detect_site
import logging
from database import (
    get_active_products, update_price, add_product,
    record_alert, get_product_count, get_site_counts,
    save_aggregator_deal, log_deal_posted,
)
from notifier import send_deal_alert, send_tracking_notification, send_aggregator_deal, send_admin_message
from config import MIN_DROP_PERCENT, MIN_DROP_DOLLARS, TELEGRAM_CHANNEL_HANDLE
from earnings import estimate_commission

logger = logging.getLogger("DealBot.Tracker")


def _log_posted_deal(deal, source, deal_type="aggregator", product_id=None):
    """Log a posted deal for earnings tracking. Returns the deal_posted ID or None."""
    try:
        site_name = deal.get("site", source)
        price_val = deal.get("price") or 0
        category = deal.get("category")
        est, has_tag = estimate_commission(site_name, price_val, category=category)
        return log_deal_posted(
            site=site_name,
            title=(deal.get("title") or "")[:200],
            sale_price=price_val,
            original_price=deal.get("original_price"),
            affiliate_url=deal.get("affiliate_url") or deal.get("url", ""),
            has_affiliate_tag=has_tag,
            estimated_commission=est,
            deal_type=deal_type,
            product_id=product_id,
            category=category,
        )
    except Exception as e:
        logger.warning("Failed to log deal for earnings: %s", e)
        return None


def check_all_prices():
    """Check prices for all tracked products across all sites."""
    products = get_active_products()
    if not products:
        print("[Tracker] No products to track. Add some with: python main.py add <url>")
        send_admin_message("📊 Price check: no products tracked yet.")
        return

    print(f"[Tracker] Checking prices for {len(products)} products...")
    deals_found = 0

    try:
        for product in products:
            pid = product["product_id"]
            site = product.get("site", "amazon")
            print(f"[{site.upper()}] {product['title'][:50]}... ", end="")

            scraped = scrape_product(product["url"])
            if not scraped or scraped.get("price") is None:
                print("price unavailable")
                continue

            new_price = scraped["price"]
            result = update_price(pid, new_price)

            if result is None:
                print("not in database")
                continue

            old_price = result[0]

            if old_price is None or old_price <= 0:
                print(f"${new_price:.2f} (first price recorded)")
                continue

            if new_price >= old_price:
                print(f"${new_price:.2f} (no drop)")
                continue

            drop_dollars = old_price - new_price
            drop_percent = (drop_dollars / old_price) * 100

            if drop_percent >= MIN_DROP_PERCENT and drop_dollars >= MIN_DROP_DOLLARS:
                print(f"${new_price:.2f} DROP {drop_percent:.0f}%!")
                alert_product = {**product, **scraped}
                deal_id = _log_posted_deal(alert_product, site, "price_drop", pid)
                send_deal_alert(alert_product, old_price, new_price, drop_percent, deal_id=deal_id)
                record_alert(pid, old_price, new_price, drop_percent)
                deals_found += 1
            else:
                print(f"${new_price:.2f} (small drop: {drop_percent:.1f}%)")
    except Exception as e:
        send_admin_message(f"⚠️ Price check error: {e}")
        raise

    print(f"\n[Tracker] Done. {deals_found} deal(s) found from {len(products)} products.")
    send_admin_message(
        f"📊 <b>Price check complete</b>\n"
        f"Products checked: {len(products)}\n"
        f"Deals found: {deals_found}"
    )


def scan_deals():
    """Scan deal aggregators (Slickdeals, DealNews) for hot deals and send new ones."""
    print("[Tracker] Scanning deal aggregators for hot deals...")
    try:
        deals = scrape_deal_aggregators()
        new_deals = 0

        for deal in deals:
            title = deal.get("title", "")
            price = deal.get("price")
            original_price = deal.get("original_price")
            store = deal.get("store", "")
            url = deal.get("url", "")
            source = deal.get("site", "unknown")

            category = deal.get("category")
            is_new = save_aggregator_deal(source, title, price, original_price, store, url, category)
            if is_new and price:
                deal_id = _log_posted_deal(deal, source)
                send_aggregator_deal(deal, deal_id=deal_id)
                new_deals += 1
    except Exception as e:
        send_admin_message(f"⚠️ Deal scan error: {e}")
        raise

    print(f"[Tracker] Aggregator scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")
    send_admin_message(
        f"🔍 <b>Deal scan complete</b>\n"
        f"Total found: {len(deals)}\n"
        f"New deals posted: {new_deals}"
    )


def scan_all_deals():
    """Scan ALL sources (retailers + aggregators) for deals."""
    print("[Tracker] Full deal scan across all sites...")
    try:
        deals = scrape_all_deals()
        new_deals = 0

        for deal in deals:
            title = deal.get("title", "")
            price = deal.get("price")
            original_price = deal.get("original_price")
            store = deal.get("store", deal.get("site", ""))
            url = deal.get("url", "")
            source = deal.get("site", "unknown")

            category = deal.get("category")
            is_new = save_aggregator_deal(source, title, price, original_price, store, url, category)
            if is_new and price:
                deal_id = _log_posted_deal(deal, source)
                send_aggregator_deal(deal, deal_id=deal_id)
                new_deals += 1
    except Exception as e:
        send_admin_message(f"⚠️ Full scan error: {e}")
        raise

    print(f"[Tracker] Full scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")
    send_admin_message(
        f"🔍 <b>Full scan complete</b>\n"
        f"Total found: {len(deals)}\n"
        f"New deals posted: {new_deals}"
    )


def scan_lifestyle():
    """Scan lifestyle deal sites (Groupon, Skyscanner, Expedia) for deals."""
    print("[Tracker] Scanning lifestyle deal sites (flights, gifts, events)...")
    try:
        deals = scrape_lifestyle_deals()
        new_deals = 0

        for deal in deals:
            title = deal.get("title", "")
            price = deal.get("price")
            original_price = deal.get("original_price")
            store = deal.get("store", deal.get("site", ""))
            url = deal.get("url", "")
            source = deal.get("site", "unknown")

            category = deal.get("category")
            is_new = save_aggregator_deal(source, title, price, original_price, store, url, category)
            if is_new and (price or title):
                deal_id = _log_posted_deal(deal, source)
                send_aggregator_deal(deal, deal_id=deal_id)
                new_deals += 1
    except Exception as e:
        send_admin_message(f"⚠️ Lifestyle scan error: {e}")
        raise

    print(f"[Tracker] Lifestyle scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")
    send_admin_message(
        f"✈️ <b>Lifestyle scan complete</b>\n"
        f"Total found: {len(deals)}\n"
        f"New deals posted: {new_deals}"
    )


def scan_category(category):
    """Scan deals for a specific category (flights, birthday, wedding, etc.)."""
    from scrapers import DEAL_CATEGORIES
    label = DEAL_CATEGORIES.get(category, category.title())
    print(f"[Tracker] Scanning {label} deals...")
    try:
        deals = scrape_category_deals(category)
        new_deals = 0

        for deal in deals:
            title = deal.get("title", "")
            price = deal.get("price")
            original_price = deal.get("original_price")
            store = deal.get("store", deal.get("site", ""))
            url = deal.get("url", "")
            source = deal.get("site", "unknown")

            category = deal.get("category")
            is_new = save_aggregator_deal(source, title, price, original_price, store, url, category)
            if is_new and (price or title):
                deal_id = _log_posted_deal(deal, source)
                send_aggregator_deal(deal, deal_id=deal_id)
                new_deals += 1
    except Exception as e:
        send_admin_message(f"⚠️ {label} scan error: {e}")
        raise

    print(f"[Tracker] {label} scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")
    send_admin_message(
        f"🏷️ <b>{label} scan complete</b>\n"
        f"Total found: {len(deals)}\n"
        f"New deals posted: {new_deals}"
    )
    return new_deals


def add_new_product(url_or_id):
    """Add a new product to track from any supported site."""
    site = detect_site(url_or_id)
    print(f"[Tracker] Detected site: {site}")
    print(f"[Tracker] Scraping product info...")

    scraped = scrape_product(url_or_id)
    if not scraped:
        print("[Tracker] Failed to scrape product. Check the URL.")
        print("[Tracker] Supported: Amazon, Best Buy, Walmart, Target URLs")
        return False

    add_product(
        product_id=scraped["product_id"],
        title=scraped["title"],
        url=scraped["url"],
        site=scraped.get("site", site),
        affiliate_url=scraped.get("affiliate_url"),
        image_url=scraped.get("image_url"),
        price=scraped.get("price"),
    )

    price_str = f"${scraped['price']:.2f}" if scraped.get("price") else "unavailable"
    print(f"[Tracker] Added: {scraped['title'][:60]}")
    print(f"[Tracker] Site: {scraped.get('site', site)}")
    print(f"[Tracker] ID: {scraped['product_id']}")
    print(f"[Tracker] Price: {price_str}")
    if scraped.get("affiliate_url"):
        print(f"[Tracker] Affiliate URL: {scraped['affiliate_url']}")

    send_tracking_notification(scraped)
    return True


def add_bulk_products(items):
    """Add multiple products at once from any supported sites."""
    added = 0
    for item in items:
        item = item.strip()
        if item and not item.startswith("#"):
            if add_new_product(item):
                added += 1
    print(f"\n[Tracker] Added {added}/{len(items)} products.")


def show_status():
    """Print current tracking status with per-site breakdown."""
    products = get_active_products()
    count = len(products)
    site_counts = get_site_counts()

    print(f"\n{'='*65}")
    print(f"  Deal Alert Bot - Tracking {count} products")
    if site_counts:
        breakdown = ", ".join(f"{s}: {c}" for s, c in site_counts.items())
        print(f"  Sites: {breakdown}")
    print(f"{'='*65}")

    if not products:
        print("  No products tracked yet.")
        print("  Add products from any supported site:")
        print("    python main.py add <amazon-url>")
        print("    python main.py add <bestbuy-url>")
        print("    python main.py add <walmart-url>")
        print("    python main.py add <target-url>")
        print(f"{'='*65}\n")
        return

    current_site = None
    for p in products:
        site = p.get("site", "unknown")
        if site != current_site:
            current_site = site
            print(f"\n  --- {site.upper()} ---")

        price = f"${p['current_price']:.2f}" if p["current_price"] else "N/A"
        lowest = f"${p['lowest_price']:.2f}" if p["lowest_price"] else "N/A"
        highest = f"${p['highest_price']:.2f}" if p["highest_price"] else "N/A"
        checked = p.get("last_checked", "Never")

        print(f"\n  {p['title'][:55]}")
        print(f"  ID: {p['product_id'][:15]}  |  Price: {price}  |  Low: {lowest}  |  High: {highest}")
        print(f"  Last checked: {checked}")

    print(f"\n{'='*65}\n")


def get_status_text():
    """Return tracking status as an HTML-formatted string for Telegram."""
    products = get_active_products()
    count = len(products)
    site_counts = get_site_counts()

    lines = [f"<b>Tracking {count} product(s)</b>"]
    if site_counts:
        breakdown = ", ".join(f"{s.capitalize()}: {c}" for s, c in site_counts.items())
        lines.append(breakdown)

    if not products:
        lines.append("\nNo products tracked yet.")
        lines.append("Use /add &lt;url&gt; to start tracking.")
        return "\n".join(lines)

    current_site = None
    for p in products:
        site = p.get("site", "unknown")
        if site != current_site:
            current_site = site
            lines.append(f"\n<b>--- {site.upper()} ---</b>")

        price = f"${p['current_price']:.2f}" if p["current_price"] else "N/A"
        lowest = f"${p['lowest_price']:.2f}" if p["lowest_price"] else "N/A"

        title = p["title"][:50]
        lines.append(f"\n{title}")
        lines.append(f"Price: {price} | Low: {lowest}")
        lines.append(f"ID: <code>{p['product_id'][:15]}</code>")

    return "\n".join(lines)


def generate_daily_summary():
    """Generate and post a 'Top Deals of the Day' summary to the channel."""
    from notifier import send_custom_message
    from database import get_todays_deals

    deals = get_todays_deals(limit=10)
    if not deals:
        send_admin_message("📋 Daily summary: no deals found today.")
        return

    lines = ["🏆 <b>Top Deals of the Day</b>\n"]
    for i, deal in enumerate(deals, 1):
        title = deal["title"][:60]
        if deal.get("price") and deal.get("original_price") and deal["original_price"] > deal["price"]:
            pct = ((deal["original_price"] - deal["price"]) / deal["original_price"]) * 100
            lines.append(f"{i}. <b>{title}</b>\n   💰 ${deal['price']:.2f} ({pct:.0f}% off)")
        elif deal.get("price"):
            lines.append(f"{i}. <b>{title}</b>\n   💰 ${deal['price']:.2f}")
        else:
            lines.append(f"{i}. <b>{title}</b>")

    lines.append(f"\n📢 Join {TELEGRAM_CHANNEL_HANDLE} for real-time alerts!")
    message = "\n".join(lines)
    send_custom_message(message)
    send_admin_message(f"📋 Daily summary posted: {len(deals)} deals.")
