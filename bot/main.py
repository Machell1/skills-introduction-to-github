"""
Deal Alert Bot - Amazon Price Drop Monitor with Telegram Notifications

Usage:
    python main.py run              Start the bot (checks prices on schedule)
    python main.py check            Check all prices once
    python main.py add <url>        Add a product to track
    python main.py add-bulk <file>  Add products from a file (one URL/ASIN per line)
    python main.py status           Show all tracked products
    python main.py remove <asin>    Stop tracking a product

Run from PyCharm:
    1. Copy .env.example to .env and fill in your credentials
    2. pip install -r requirements.txt
    3. Run this file with argument "run" for continuous monitoring
"""

import sys
import time
import schedule
from database import init_db
from tracker import check_all_prices, add_new_product, add_bulk_products, show_status
from database import remove_product, get_product_count
from config import CHECK_INTERVAL_MINUTES


def run_scheduler():
    """Run the price checker on a schedule."""
    print(f"\n{'='*60}")
    print(f"  Deal Alert Bot - Starting")
    print(f"  Checking every {CHECK_INTERVAL_MINUTES} minutes")
    print(f"  Tracking {get_product_count()} products")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    # Run immediately on start
    check_all_prices()

    # Schedule recurring checks
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_all_prices)

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n[Bot] Stopped.")


def main():
    # Initialize database
    init_db()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "run":
        run_scheduler()

    elif command == "check":
        check_all_prices()

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python main.py add <amazon-url-or-asin>")
            return
        add_new_product(sys.argv[2])

    elif command == "add-bulk":
        if len(sys.argv) < 3:
            print("Usage: python main.py add-bulk <file>")
            print("File should contain one Amazon URL or ASIN per line.")
            return
        filepath = sys.argv[2]
        try:
            with open(filepath, "r") as f:
                items = [line.strip() for line in f if line.strip()]
            add_bulk_products(items)
        except FileNotFoundError:
            print(f"File not found: {filepath}")

    elif command == "status":
        show_status()

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python main.py remove <asin>")
            return
        remove_product(sys.argv[2])
        print(f"[Bot] Removed {sys.argv[2]} from tracking.")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
