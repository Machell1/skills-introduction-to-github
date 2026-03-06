"""SQLite database for tracking products and price history."""

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
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            asin TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
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
            asin TEXT NOT NULL,
            price REAL NOT NULL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asin) REFERENCES products(asin)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT NOT NULL,
            old_price REAL,
            new_price REAL,
            drop_percent REAL,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asin) REFERENCES products(asin)
        )
    """)

    conn.commit()
    conn.close()


def add_product(asin, title, url, image_url=None, price=None):
    """Add a product to track."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO products
        (asin, title, url, image_url, current_price, lowest_price, highest_price, last_checked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (asin, title, url, image_url, price, price, price, now))

    if price is not None:
        cursor.execute("""
            INSERT INTO price_history (asin, price, recorded_at)
            VALUES (?, ?, ?)
        """, (asin, price, now))

    conn.commit()
    conn.close()


def update_price(asin, new_price):
    """Update price for a product and record history. Returns (old_price, new_price) or None."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    cursor.execute("SELECT current_price, lowest_price, highest_price FROM products WHERE asin = ?", (asin,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    old_price = row["current_price"]
    lowest = row["lowest_price"]
    highest = row["highest_price"]

    new_lowest = min(lowest, new_price) if lowest else new_price
    new_highest = max(highest, new_price) if highest else new_price

    cursor.execute("""
        UPDATE products
        SET current_price = ?, lowest_price = ?, highest_price = ?, last_checked = ?
        WHERE asin = ?
    """, (new_price, new_lowest, new_highest, now, asin))

    cursor.execute("""
        INSERT INTO price_history (asin, price, recorded_at)
        VALUES (?, ?, ?)
    """, (asin, new_price, now))

    conn.commit()
    conn.close()

    return (old_price, new_price)


def get_active_products():
    """Get all actively tracked products."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_alert(asin, old_price, new_price, drop_percent):
    """Record that an alert was sent."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts_sent (asin, old_price, new_price, drop_percent)
        VALUES (?, ?, ?, ?)
    """, (asin, old_price, new_price, drop_percent))
    conn.commit()
    conn.close()


def get_product_count():
    """Get number of tracked products."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM products WHERE active = 1")
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def get_price_history(asin, limit=30):
    """Get recent price history for a product."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price, recorded_at FROM price_history
        WHERE asin = ? ORDER BY recorded_at DESC LIMIT ?
    """, (asin, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_product(asin):
    """Deactivate a product from tracking."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET active = 0 WHERE asin = ?", (asin,))
    conn.commit()
    conn.close()
