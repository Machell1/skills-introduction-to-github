"""Symbol resolution helpers for Deriv MT5."""
from __future__ import annotations

from typing import Optional

import MetaTrader5 as mt5


def resolve_symbol(preferred: str) -> Optional[str]:
    """Resolve BTCUSD symbol, handling Deriv suffixes."""
    if mt5.symbol_info(preferred) is not None:
        return preferred

    symbols = mt5.symbols_get()
    if symbols is None:
        return None

    candidates = []
    for symbol in symbols:
        name = symbol.name
        if "BTC" in name.upper() and "USD" in name.upper():
            candidates.append(name)

    if not candidates:
        return None

    candidates.sort(key=len)
    return candidates[0]


def ensure_symbol_enabled(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    return mt5.symbol_select(symbol, True)
