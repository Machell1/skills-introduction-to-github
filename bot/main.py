"""
Deal Alert Bot - Multi-Site Price Monitor with Telegram Alerts

Monitors prices across Amazon, Best Buy, Walmart, Target, and eBay.
Also scans deal aggregators (Slickdeals, DealNews) for hot deals.

Usage:
    python main.py run              Start the bot (checks on schedule)
    python main.py check            Check all tracked product prices once
    python main.py scan-deals       Scan Slickdeals & DealNews for hot deals
    python main.py scan-all         Scan ALL sites (retailers + aggregators)
    python main.py add <url>        Add a product to track (any supported site)
    python main.py add-bulk <file>  Add products from a file (one URL per line)
    python main.py status           Show all tracked products by site
    python main.py remove <id>      Stop tracking a product

Supported sites:
    Amazon, Best Buy, Walmart, Target, eBay (product tracking)
    Slickdeals, DealNews (deal scanning)

Run from PyCharm:
    1. Copy .env.example to .env and fill in your credentials
    2. pip install -r requirements.txt
    3. Run this file with argument "run" for continuous monitoring
"""

import sys
import time
import schedule
from database import init_db, remove_product, get_product_count, get_site_counts
from tracker import (
    check_all_prices, add_new_product, add_bulk_products,
    show_status, scan_deals, scan_all_deals
)
from config import CHECK_INTERVAL_MINUTES


def run_scheduler():
    """Run the price checker and deal scanner on a schedule."""
    site_counts = get_site_counts()
    breakdown = ", ".join(f"{s}: {c}" for s, c in site_counts.items()) if site_counts else "none"

    print(f"\n{'='*65}")
    print(f"  Deal Alert Bot - Multi-Site Monitor")
    print(f"  Price checks every {CHECK_INTERVAL_MINUTES} minutes")
    print(f"  Deal scans every {CHECK_INTERVAL_MINUTES * 2} minutes")
    print(f"  Tracking {get_product_count()} products ({breakdown})")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*65}\n")

    # Run immediately on start
    check_all_prices()
    scan_deals()

    # Schedule recurring tasks
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_all_prices)
    schedule.every(CHECK_INTERVAL_MINUTES * 2).minutes.do(scan_deals)

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n[Bot] Stopped.")


def main():
    init_db()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower().replace("_", "-")

    if command == "run":
        run_scheduler()

    elif command == "check":
        check_all_prices()

    elif command == "scan-deals":
        scan_deals()

    elif command == "scan-all":
        scan_all_deals()

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python main.py add <product-url>")
            print("Supported: Amazon, Best Buy, Walmart, Target URLs")
            return
        add_new_product(sys.argv[2])

    elif command == "add-bulk":
        if len(sys.argv) < 3:
            print("Usage: python main.py add-bulk <file>")
            print("File should contain one URL per line (any supported site).")
            return
        filepath = sys.argv[2]
        try:
            with open(filepath, "r") as f:
                items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            add_bulk_products(items)
        except FileNotFoundError:
            print(f"File not found: {filepath}")

    elif command == "status":
        show_status()

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python main.py remove <product-id>")
            return
        remove_product(sys.argv[2])
        print(f"[Bot] Removed {sys.argv[2]} from tracking.")

    elif command == "sites":
        print("\nSupported sites for product tracking:")
        print("  - Amazon    (amazon.com)")
        print("  - Best Buy  (bestbuy.com)")
        print("  - Walmart   (walmart.com)")
        print("  - Target    (target.com)")
        print("  - eBay      (ebay.com)")
        print("\nDeal aggregators (scanned for hot deals):")
        print("  - Slickdeals (slickdeals.net)")
        print("  - DealNews   (dealnews.com)\n")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
