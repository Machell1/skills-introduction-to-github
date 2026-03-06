"""Price tracker - monitors products across multiple sites and detects deals."""

from scraper import scrape_product, scrape_deal_aggregators, scrape_all_deals
from scrapers import get_scraper_for_url, detect_site
from database import (
    get_active_products, update_price, add_product,
    record_alert, get_product_count, get_site_counts,
    save_aggregator_deal,
)
from notifier import send_deal_alert, send_tracking_notification, send_aggregator_deal
from config import MIN_DROP_PERCENT, MIN_DROP_DOLLARS


def check_all_prices():
    """Check prices for all tracked products across all sites."""
    products = get_active_products()
    if not products:
        print("[Tracker] No products to track. Add some with: python main.py add <url>")
        return

    print(f"[Tracker] Checking prices for {len(products)} products...")
    deals_found = 0

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
            send_deal_alert(alert_product, old_price, new_price, drop_percent)
            record_alert(pid, old_price, new_price, drop_percent)
            deals_found += 1
        else:
            print(f"${new_price:.2f} (small drop: {drop_percent:.1f}%)")

    print(f"\n[Tracker] Done. {deals_found} deal(s) found from {len(products)} products.")


def scan_deals():
    """Scan deal aggregators (Slickdeals, DealNews) for hot deals and send new ones."""
    print("[Tracker] Scanning deal aggregators for hot deals...")
    deals = scrape_deal_aggregators()
    new_deals = 0

    for deal in deals:
        title = deal.get("title", "")
        price = deal.get("price")
        original_price = deal.get("original_price")
        store = deal.get("store", "")
        url = deal.get("url", "")
        source = deal.get("site", "unknown")

        is_new = save_aggregator_deal(source, title, price, original_price, store, url)
        if is_new and price:
            send_aggregator_deal(deal)
            new_deals += 1

    print(f"[Tracker] Aggregator scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")


def scan_all_deals():
    """Scan ALL sources (retailers + aggregators) for deals."""
    print("[Tracker] Full deal scan across all sites...")
    deals = scrape_all_deals()
    new_deals = 0

    for deal in deals:
        title = deal.get("title", "")
        price = deal.get("price")
        original_price = deal.get("original_price")
        store = deal.get("store", deal.get("site", ""))
        url = deal.get("url", "")
        source = deal.get("site", "unknown")

        is_new = save_aggregator_deal(source, title, price, original_price, store, url)
        if is_new and price:
            send_aggregator_deal(deal)
            new_deals += 1

    print(f"[Tracker] Full scan done. {new_deals} new deal(s) sent, {len(deals)} total found.")


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
