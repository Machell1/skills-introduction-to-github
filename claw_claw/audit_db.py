"""SQLite audit database."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict


class AuditDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    bot_name TEXT,
                    direction TEXT,
                    confidence REAL,
                    rationale TEXT,
                    arbiter_decision TEXT,
                    risk_allowed INTEGER,
                    risk_reasons TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    ticket INTEGER,
                    symbol TEXT,
                    direction TEXT,
                    volume REAL,
                    entry_price REAL,
                    sl REAL,
                    tp REAL,
                    spread REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_time TEXT,
                    exit_time TEXT,
                    symbol TEXT,
                    direction TEXT,
                    volume REAL,
                    entry_price REAL,
                    exit_price REAL,
                    sl REAL,
                    tp REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    risk_amount REAL,
                    drawdown_at_entry REAL,
                    spread_at_entry REAL,
                    bot_name TEXT,
                    rationale TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    equity REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    message TEXT
                )
                """
            )
            conn.commit()

    def log_decision(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO decisions (timestamp, symbol, bot_name, direction, confidence, rationale, arbiter_decision, risk_allowed, risk_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("timestamp"),
                    data.get("symbol"),
                    data.get("bot_name"),
                    data.get("direction"),
                    data.get("confidence"),
                    data.get("rationale"),
                    data.get("arbiter_decision"),
                    int(data.get("risk_allowed", 0)),
                    data.get("risk_reasons"),
                ),
            )
            conn.commit()

    def log_order(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orders (timestamp, ticket, symbol, direction, volume, entry_price, sl, tp, spread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("timestamp"),
                    data.get("ticket"),
                    data.get("symbol"),
                    data.get("direction"),
                    data.get("volume"),
                    data.get("entry_price"),
                    data.get("sl"),
                    data.get("tp"),
                    data.get("spread"),
                ),
            )
            conn.commit()

    def log_trade(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (entry_time, exit_time, symbol, direction, volume, entry_price, exit_price, sl, tp, pnl, pnl_pct, risk_amount, drawdown_at_entry, spread_at_entry, bot_name, rationale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("entry_time"),
                    data.get("exit_time"),
                    data.get("symbol"),
                    data.get("direction"),
                    data.get("volume"),
                    data.get("entry_price"),
                    data.get("exit_price"),
                    data.get("sl"),
                    data.get("tp"),
                    data.get("pnl"),
                    data.get("pnl_pct"),
                    data.get("risk_amount"),
                    data.get("drawdown_at_entry"),
                    data.get("spread_at_entry"),
                    data.get("bot_name"),
                    data.get("rationale"),
                ),
            )
            conn.commit()

    def log_equity(self, timestamp: str, equity: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                (timestamp, equity),
            )
            conn.commit()

    def log_error(self, timestamp: str, message: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO errors (timestamp, message) VALUES (?, ?)",
                (timestamp, message),
            )
            conn.commit()

    def daily_summary(self) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(pnl), AVG(pnl) FROM trades")
            count, total_pnl, avg_pnl = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0")
            wins = cursor.fetchone()[0]
            cursor.execute("SELECT AVG(pnl / risk_amount) FROM trades WHERE risk_amount > 0")
            avg_r = cursor.fetchone()[0]
            cursor.execute("SELECT equity FROM equity_snapshots ORDER BY id ASC")
            equity_rows = cursor.fetchall()

        total_pnl = total_pnl or 0.0
        avg_pnl = avg_pnl or 0.0
        avg_r = avg_r or 0.0
        win_rate = (wins / count * 100) if count else 0.0
        max_drawdown = 0.0
        peak = None
        for (equity,) in equity_rows:
            if equity is None:
                continue
            if peak is None or equity > peak:
                peak = equity
            if peak is not None:
                drawdown = (peak - equity) / peak * 100 if peak else 0.0
                max_drawdown = max(max_drawdown, drawdown)
        return (
            f"Daily summary: trades={count}, win_rate={win_rate:.1f}%, "
            f"avg_r={avg_r:.2f}, max_dd={max_drawdown:.2f}%, "
            f"avg_pnl={avg_pnl:.2f}, total_pnl={total_pnl:.2f}"
        )
