"""SQLite database for tracking products and price history across multiple sites."""

import sqlite3
from datetime import datetime
from config import DB_PATH


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                site TEXT NOT NULL DEFAULT 'amazon',
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                affiliate_url TEXT,
                image_url TEXT,
                current_price REAL,
                lowest_price REAL,
                highest_price REAL,
                last_checked TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                old_price REAL,
                new_price REAL,
                drop_percent REAL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aggregator_deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                price REAL,
                original_price REAL,
                store TEXT,
                category TEXT,
                url TEXT NOT NULL,
                found_at TEXT DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                referrer_code TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deals_posted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT NOT NULL,
                title TEXT NOT NULL,
                sale_price REAL,
                original_price REAL,
                affiliate_url TEXT,
                has_affiliate_tag INTEGER DEFAULT 0,
                estimated_commission REAL DEFAULT 0,
                deal_type TEXT DEFAULT 'aggregator',
                product_id TEXT,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commission_rates (
                site TEXT PRIMARY KEY,
                rate_low REAL NOT NULL,
                rate_high REAL NOT NULL,
                rate_used REAL NOT NULL,
                model TEXT DEFAULT 'percentage',
                cpa_amount REAL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed commission rates if table is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM commission_rates")
        if cursor.fetchone()["cnt"] == 0:
            rates = [
                ("amazon", 0.01, 0.04, 0.025, "percentage", 0),
                ("walmart", 0.01, 0.04, 0.025, "percentage", 0),
                ("target", 0.01, 0.08, 0.04, "percentage", 0),
                ("bestbuy", 0.005, 0.01, 0.0075, "percentage", 0),
                ("ebay", 0.01, 0.04, 0.025, "percentage", 0),
                ("groupon", 0.03, 0.06, 0.045, "percentage", 0),
                ("skyscanner", 0.0, 0.0, 0.0, "cpa", 0.50),
                ("expedia", 0.02, 0.06, 0.04, "percentage", 0),
                ("slickdeals", 0.0, 0.0, 0.0, "percentage", 0),
                ("dealnews", 0.0, 0.0, 0.0, "percentage", 0),
            ]
            cursor.executemany(
                "INSERT INTO commission_rates (site, rate_low, rate_high, rate_used, model, cpa_amount) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rates,
            )

        # Migrate: add category column if missing
        try:
            cursor.execute("SELECT category FROM aggregator_deals LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE aggregator_deals ADD COLUMN category TEXT")
            except sqlite3.OperationalError:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS click_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_posted_id INTEGER,
                user_id INTEGER,
                clicked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (deal_posted_id) REFERENCES deals_posted(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_actuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network TEXT NOT NULL,
                site TEXT NOT NULL,
                action_date TEXT NOT NULL,
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                revenue REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(network, site, action_date)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS amazon_category_rates (
                category TEXT PRIMARY KEY,
                rate REAL NOT NULL
            )
        """)

        # Seed Amazon category rates if empty
        cursor.execute("SELECT COUNT(*) as cnt FROM amazon_category_rates")
        if cursor.fetchone()["cnt"] == 0:
            cat_rates = [
                ("Electronics", 0.01),
                ("Computers", 0.025),
                ("Books", 0.045),
                ("Kitchen", 0.045),
                ("Automotive", 0.045),
                ("Toys", 0.03),
                ("Luxury Beauty", 0.10),
                ("Beauty", 0.06),
                ("Apparel", 0.04),
                ("Shoes", 0.04),
                ("Furniture", 0.03),
                ("Home", 0.04),
                ("Grocery", 0.01),
                ("Health", 0.01),
                ("Software", 0.05),
                ("Video Games", 0.01),
                ("default", 0.025),
            ]
            cursor.executemany(
                "INSERT INTO amazon_category_rates (category, rate) VALUES (?, ?)",
                cat_rates,
            )

        # Migrate: add category and message_id columns to deals_posted if missing
        try:
            cursor.execute("SELECT category FROM deals_posted LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE deals_posted ADD COLUMN category TEXT")
            except sqlite3.OperationalError:
                pass

        try:
            cursor.execute("SELECT message_id FROM deals_posted LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE deals_posted ADD COLUMN message_id TEXT")
            except sqlite3.OperationalError:
                pass

        # Migrate old 'asin' column if upgrading from v1
        try:
            cursor.execute("SELECT product_id FROM products LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE products RENAME COLUMN asin TO product_id")
                cursor.execute("ALTER TABLE products ADD COLUMN site TEXT NOT NULL DEFAULT 'amazon'")
                cursor.execute("ALTER TABLE products ADD COLUMN affiliate_url TEXT")
                cursor.execute("ALTER TABLE price_history RENAME COLUMN asin TO product_id")
                cursor.execute("ALTER TABLE alerts_sent RENAME COLUMN asin TO product_id")
                print("[DB] Migrated database to multi-site schema.")
            except sqlite3.OperationalError:
                pass

        conn.commit()
    finally:
        conn.close()


def add_product(product_id, title, url, site="amazon", affiliate_url=None,
                image_url=None, price=None):
    """Add a product to track."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO products
            (product_id, site, title, url, affiliate_url, image_url,
             current_price, lowest_price, highest_price, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (product_id, site, title, url, affiliate_url, image_url,
              price, price, price, now))

        if price is not None:
            cursor.execute("""
                INSERT INTO price_history (product_id, price, recorded_at)
                VALUES (?, ?, ?)
            """, (product_id, price, now))

        conn.commit()
    finally:
        conn.close()


def update_price(product_id, new_price):
    """Update price for a product and record history. Returns (old_price, new_price) or None."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "SELECT current_price, lowest_price, highest_price FROM products WHERE product_id = ?",
            (product_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        old_price = row["current_price"]
        lowest = row["lowest_price"]
        highest = row["highest_price"]

        new_lowest = min(lowest, new_price) if lowest else new_price
        new_highest = max(highest, new_price) if highest else new_price

        cursor.execute("""
            UPDATE products
            SET current_price = ?, lowest_price = ?, highest_price = ?, last_checked = ?
            WHERE product_id = ?
        """, (new_price, new_lowest, new_highest, now, product_id))

        cursor.execute("""
            INSERT INTO price_history (product_id, price, recorded_at)
            VALUES (?, ?, ?)
        """, (product_id, new_price, now))

        conn.commit()
        return (old_price, new_price)
    finally:
        conn.close()


def get_active_products():
    """Get all actively tracked products."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE active = 1 ORDER BY site, title")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_products_by_site(site):
    """Get tracked products for a specific site."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE active = 1 AND site = ?", (site,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def record_alert(product_id, old_price, new_price, drop_percent):
    """Record that an alert was sent."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts_sent (product_id, old_price, new_price, drop_percent)
            VALUES (?, ?, ?, ?)
        """, (product_id, old_price, new_price, drop_percent))
        conn.commit()
    finally:
        conn.close()


def save_aggregator_deal(source, title, price, original_price, store, url, category=None):
    """Save a deal found by an aggregator or lifestyle scraper."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Check if we already have this deal (by URL)
        cursor.execute("SELECT id FROM aggregator_deals WHERE url = ?", (url,))
        if cursor.fetchone():
            return False  # Already exists

        cursor.execute("""
            INSERT INTO aggregator_deals (source, title, price, original_price, store, url, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source, title, price, original_price, store, url, category))
        conn.commit()
        return True  # New deal
    finally:
        conn.close()


def mark_deal_notified(deal_id):
    """Mark an aggregator deal as notified."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE aggregator_deals SET notified = 1 WHERE id = ?", (deal_id,))
        conn.commit()
    finally:
        conn.close()


def get_product_count():
    """Get number of tracked products."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM products WHERE active = 1")
        return cursor.fetchone()["cnt"]
    finally:
        conn.close()


def get_site_counts():
    """Get product counts per site."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT site, COUNT(*) as cnt FROM products
            WHERE active = 1 GROUP BY site ORDER BY cnt DESC
        """)
        rows = cursor.fetchall()
        return {r["site"]: r["cnt"] for r in rows}
    finally:
        conn.close()


def get_price_history(product_id, limit=30):
    """Get recent price history for a product."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT price, recorded_at FROM price_history
            WHERE product_id = ? ORDER BY recorded_at DESC LIMIT ?
        """, (product_id, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_product(product_id):
    """Deactivate a product from tracking."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET active = 0 WHERE product_id = ?", (product_id,))
        conn.commit()
    finally:
        conn.close()


def record_referral(user_id, referrer_code):
    """Record a referral when a user starts the bot via a deep link."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Don't record duplicate referrals from the same user
        cursor.execute("SELECT id FROM referrals WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return False
        cursor.execute(
            "INSERT INTO referrals (user_id, referrer_code) VALUES (?, ?)",
            (user_id, referrer_code),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def log_deal_posted(site, title, sale_price, original_price, affiliate_url,
                    has_affiliate_tag, estimated_commission, deal_type="aggregator",
                    product_id=None, category=None):
    """Log a deal that was posted to the channel for earnings tracking. Returns the row ID."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO deals_posted
            (site, title, sale_price, original_price, affiliate_url,
             has_affiliate_tag, estimated_commission, deal_type, product_id, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (site, title, sale_price, original_price, affiliate_url,
              1 if has_affiliate_tag else 0, estimated_commission, deal_type,
              product_id, category))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_commission_rate(site):
    """Get commission rate info for a site."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM commission_rates WHERE site = ?", (site,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_earnings_summary(days=1):
    """Get earnings summary grouped by site for the last N days."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT site,
                   COUNT(*) as deal_count,
                   SUM(estimated_commission) as total_commission,
                   SUM(CASE WHEN has_affiliate_tag = 1 THEN 1 ELSE 0 END) as with_tag,
                   SUM(CASE WHEN has_affiliate_tag = 0 THEN 1 ELSE 0 END) as without_tag,
                   SUM(sale_price) as total_sale_value
            FROM deals_posted
            WHERE posted_at >= datetime('now', ? || ' days')
            GROUP BY site
            ORDER BY total_commission DESC
        """, (f"-{days}",))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_earnings_total(days=None):
    """Get total estimated commission, optionally limited to last N days."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if days:
            cursor.execute("""
                SELECT COUNT(*) as deal_count,
                       COALESCE(SUM(estimated_commission), 0) as total
                FROM deals_posted
                WHERE posted_at >= datetime('now', ? || ' days')
            """, (f"-{days}",))
        else:
            cursor.execute("""
                SELECT COUNT(*) as deal_count,
                       COALESCE(SUM(estimated_commission), 0) as total
                FROM deals_posted
            """)
        row = cursor.fetchone()
        return dict(row)
    finally:
        conn.close()


def log_click(deal_posted_id, user_id):
    """Log a click event when a user clicks a deal button."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO click_events (deal_posted_id, user_id) VALUES (?, ?)",
            (deal_posted_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_deal_by_id(deal_id):
    """Look up a deals_posted row by ID."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deals_posted WHERE id = ?", (deal_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_click_counts(days=1):
    """Get click counts grouped by site for the last N days."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.site, COUNT(ce.id) as click_count
            FROM click_events ce
            JOIN deals_posted dp ON ce.deal_posted_id = dp.id
            WHERE ce.clicked_at >= datetime('now', ? || ' days')
            GROUP BY dp.site
            ORDER BY click_count DESC
        """, (f"-{days}",))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_deals_by_clicks(days=1, limit=5):
    """Get the deals with the most clicks in the given period."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.title, dp.site, dp.sale_price, COUNT(ce.id) as click_count
            FROM click_events ce
            JOIN deals_posted dp ON ce.deal_posted_id = dp.id
            WHERE ce.clicked_at >= datetime('now', ? || ' days')
            GROUP BY ce.deal_posted_id
            ORDER BY click_count DESC
            LIMIT ?
        """, (f"-{days}", limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_earnings_comparison(days=1):
    """Compare earnings between current period and previous period for trends."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Current period
        cursor.execute("""
            SELECT COALESCE(SUM(estimated_commission), 0) as current_total
            FROM deals_posted
            WHERE posted_at >= datetime('now', ? || ' days')
        """, (f"-{days}",))
        current = cursor.fetchone()["current_total"]

        # Previous period (same length, immediately before)
        cursor.execute("""
            SELECT COALESCE(SUM(estimated_commission), 0) as previous_total
            FROM deals_posted
            WHERE posted_at >= datetime('now', ? || ' days')
            AND posted_at < datetime('now', ? || ' days')
        """, (f"-{days * 2}", f"-{days}"))
        previous = cursor.fetchone()["previous_total"]

        return {"current_total": current, "previous_total": previous}
    finally:
        conn.close()


def get_amazon_category_rate(category):
    """Get Amazon commission rate for a specific product category."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rate FROM amazon_category_rates WHERE category = ?",
            (category,),
        )
        row = cursor.fetchone()
        if row:
            return row["rate"]
        # Try case-insensitive partial match
        cursor.execute(
            "SELECT rate FROM amazon_category_rates WHERE ? LIKE '%' || category || '%' ORDER BY LENGTH(category) DESC LIMIT 1",
            (category,),
        )
        row = cursor.fetchone()
        if row:
            return row["rate"]
        # Fall back to default
        cursor.execute(
            "SELECT rate FROM amazon_category_rates WHERE category = 'default'",
        )
        row = cursor.fetchone()
        return row["rate"] if row else None
    finally:
        conn.close()


def upsert_affiliate_actual(network, site, action_date, clicks=0,
                            conversions=0, revenue=0.0, commission=0.0):
    """Insert or update actual affiliate data from network APIs."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO affiliate_actuals
            (network, site, action_date, clicks, conversions, revenue, commission)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(network, site, action_date) DO UPDATE SET
                clicks = excluded.clicks,
                conversions = excluded.conversions,
                revenue = excluded.revenue,
                commission = excluded.commission,
                fetched_at = CURRENT_TIMESTAMP
        """, (network, site, action_date, clicks, conversions, revenue, commission))
        conn.commit()
    finally:
        conn.close()


def get_actuals_summary(days=1):
    """Get actual affiliate revenue grouped by site for the last N days."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT site,
                   SUM(clicks) as clicks,
                   SUM(conversions) as conversions,
                   SUM(revenue) as revenue,
                   SUM(commission) as commission
            FROM affiliate_actuals
            WHERE action_date >= date('now', ? || ' days')
            GROUP BY site
            ORDER BY commission DESC
        """, (f"-{days}",))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_todays_deals(limit=10):
    """Get the best deals from the last 24 hours for the daily summary."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT title, price, original_price, store, url, category
            FROM aggregator_deals
            WHERE found_at >= datetime('now', '-24 hours')
            AND price IS NOT NULL
            ORDER BY
                CASE WHEN original_price > 0
                     THEN (original_price - price) / original_price
                     ELSE 0 END DESC,
                price ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
