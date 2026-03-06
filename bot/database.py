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

        # Migrate: add category column if missing
        try:
            cursor.execute("SELECT category FROM aggregator_deals LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE aggregator_deals ADD COLUMN category TEXT")
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
