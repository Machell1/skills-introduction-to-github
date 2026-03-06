"""Price tracker - monitors products and detects deals."""

from datetime import datetime
from scraper import scrape_product, build_affiliate_url
from database import (
    get_active_products, update_price, add_product,
    record_alert, get_product_count
)
from notifier import send_deal_alert, send_tracking_notification
from config import MIN_DROP_PERCENT, MIN_DROP_DOLLARS


def check_all_prices():
    """Check prices for all tracked products and send alerts for drops."""
    products = get_active_products()
    if not products:
        print("[Tracker] No products to track. Add some with: python main.py add <url>")
        return

    print(f"[Tracker] Checking prices for {len(products)} products...")
    deals_found = 0

    for product in products:
        asin = product["asin"]
        print(f"[Tracker] Checking {product['title'][:50]}... ", end="")

        scraped = scrape_product(asin)
        if not scraped or scraped["price"] is None:
            print("price unavailable")
            continue

        new_price = scraped["price"]
        result = update_price(asin, new_price)

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

        # Calculate drop
        drop_dollars = old_price - new_price
        drop_percent = (drop_dollars / old_price) * 100

        if drop_percent >= MIN_DROP_PERCENT and drop_dollars >= MIN_DROP_DOLLARS:
            print(f"${new_price:.2f} ⬇️ {drop_percent:.0f}% DROP!")

            # Enrich product data for the alert
            alert_product = {**product, **scraped}

            send_deal_alert(alert_product, old_price, new_price, drop_percent)
            record_alert(asin, old_price, new_price, drop_percent)
            deals_found += 1
        else:
            print(f"${new_price:.2f} (small drop: {drop_percent:.1f}%)")

    print(f"\n[Tracker] Done. {deals_found} deal(s) found out of {len(products)} products checked.")


def add_new_product(url_or_asin):
    """Add a new product to track."""
    print(f"[Tracker] Scraping product info...")
    scraped = scrape_product(url_or_asin)

    if not scraped:
        print("[Tracker] Failed to scrape product. Check the URL/ASIN.")
        return False

    add_product(
        asin=scraped["asin"],
        title=scraped["title"],
        url=scraped["url"],
        image_url=scraped.get("image_url"),
        price=scraped["price"],
    )

    price_str = f"${scraped['price']:.2f}" if scraped["price"] else "unavailable"
    print(f"[Tracker] Added: {scraped['title'][:60]}")
    print(f"[Tracker] ASIN: {scraped['asin']}")
    print(f"[Tracker] Price: {price_str}")
    print(f"[Tracker] Affiliate URL: {scraped['affiliate_url']}")

    send_tracking_notification(scraped)
    return True


def add_bulk_products(asins_or_urls):
    """Add multiple products at once."""
    added = 0
    for item in asins_or_urls:
        item = item.strip()
        if item:
            if add_new_product(item):
                added += 1
    print(f"\n[Tracker] Added {added}/{len(asins_or_urls)} products.")


def show_status():
    """Print current tracking status."""
    products = get_active_products()
    count = len(products)

    print(f"\n{'='*60}")
    print(f"  Deal Alert Bot - Tracking {count} products")
    print(f"{'='*60}")

    if not products:
        print("  No products tracked yet.")
        print("  Add products: python main.py add <amazon-url>")
        print(f"{'='*60}\n")
        return

    for p in products:
        price = f"${p['current_price']:.2f}" if p["current_price"] else "N/A"
        lowest = f"${p['lowest_price']:.2f}" if p["lowest_price"] else "N/A"
        highest = f"${p['highest_price']:.2f}" if p["highest_price"] else "N/A"
        checked = p.get("last_checked", "Never")

        print(f"\n  {p['title'][:55]}")
        print(f"  ASIN: {p['asin']}  |  Current: {price}  |  Low: {lowest}  |  High: {highest}")
        print(f"  Last checked: {checked}")

    print(f"\n{'='*60}\n")
