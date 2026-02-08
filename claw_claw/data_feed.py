"""Market data fetching."""
from __future__ import annotations

from datetime import datetime
from typing import List

import MetaTrader5 as mt5


def fetch_candles(symbol: str, timeframe: int, count: int = 200) -> List[dict]:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        return []
    return [
        {
            "time": datetime.fromtimestamp(rate["time"]),
            "open": rate["open"],
            "high": rate["high"],
            "low": rate["low"],
            "close": rate["close"],
            "tick_volume": rate["tick_volume"],
        }
        for rate in rates
    ]
