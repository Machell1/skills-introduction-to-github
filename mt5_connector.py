"""
MetaTrader 5 Connector for Deriv
---------------------------------
Handles:
  - Auto-connection to the Deriv MT5 terminal
  - Historical OHLCV data retrieval
  - Live order execution (market orders with SL/TP)
  - Position management (query, modify, close)

Requires: MetaTrader5 package (Windows only, Python 3.9+)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


# ── Common Deriv MT5 server names ──────────────────────────────────
DERIV_SERVERS = [
    "Deriv-Demo",
    "Deriv-Server",
    "Deriv-Real",
    "Deriv-Server-02",
]

# MT5 timeframe mapping
TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1  if mt5 else 1,
    "M5":  mt5.TIMEFRAME_M5  if mt5 else 5,
    "M15": mt5.TIMEFRAME_M15 if mt5 else 15,
    "M30": mt5.TIMEFRAME_M30 if mt5 else 30,
    "H1":  mt5.TIMEFRAME_H1  if mt5 else 16385,
    "H4":  mt5.TIMEFRAME_H4  if mt5 else 16388,
    "D1":  mt5.TIMEFRAME_D1  if mt5 else 16408,
}


def check_mt5_available() -> bool:
    """Check if MetaTrader5 package is installed and we are on Windows."""
    if mt5 is None:
        print("  ERROR: MetaTrader5 package not installed.")
        print("         Run: pip install MetaTrader5")
        return False
    if sys.platform != "win32":
        print("  ERROR: MetaTrader5 only works on Windows.")
        return False
    return True


def connect(
    login: Optional[int] = None,
    password: Optional[str] = None,
    server: Optional[str] = None,
    path: Optional[str] = None,
    timeout: int = 30000,
) -> bool:
    """
    Connect to the Deriv MT5 terminal.

    If login/password/server are provided, performs full authentication.
    Otherwise, connects to whichever MT5 terminal is already running.

    Parameters
    ----------
    login : int, optional
        MT5 account number
    password : str, optional
        Account password
    server : str, optional
        Server name (e.g. "Deriv-Demo"). If None, tries common Deriv servers.
    path : str, optional
        Full path to terminal64.exe if MT5 is not in the default location.
    timeout : int
        Connection timeout in ms (default 30s)

    Returns
    -------
    bool
        True if connected successfully
    """
    if not check_mt5_available():
        return False

    init_kwargs = {"login": login, "timeout": timeout}
    if path:
        init_kwargs["path"] = path
    if password:
        init_kwargs["password"] = password

    # If server is specified, try it directly
    if server:
        init_kwargs["server"] = server
        if mt5.initialize(**{k: v for k, v in init_kwargs.items() if v is not None}):
            _print_connection_info()
            return True
        print(f"  Failed to connect to {server}: {mt5.last_error()}")
        return False

    # Try connecting without credentials first (uses running terminal)
    if mt5.initialize(timeout=timeout):
        _print_connection_info()
        return True

    # If login provided, try each Deriv server
    if login and password:
        for srv in DERIV_SERVERS:
            init_kwargs["server"] = srv
            print(f"  Trying server: {srv} ...")
            if mt5.initialize(**{k: v for k, v in init_kwargs.items() if v is not None}):
                _print_connection_info()
                return True

    print(f"  ERROR: Could not connect to MT5: {mt5.last_error()}")
    print("  Make sure your Deriv MT5 terminal is running.")
    return False


def disconnect() -> None:
    """Shut down the MT5 connection."""
    if mt5 is not None:
        mt5.shutdown()
        print("  MT5 disconnected.")


def _print_connection_info() -> None:
    """Print terminal and account info after connecting."""
    info = mt5.terminal_info()
    account = mt5.account_info()
    if info and account:
        print(f"  Connected to MT5:")
        print(f"    Terminal:  {info.name}")
        print(f"    Company:   {info.company}")
        print(f"    Account:   {account.login}")
        print(f"    Server:    {account.server}")
        print(f"    Balance:   ${account.balance:,.2f}")
        print(f"    Leverage:  1:{account.leverage}")
        print(f"    Currency:  {account.currency}")


def get_account_balance() -> float:
    """Return the current account balance."""
    account = mt5.account_info()
    if account is None:
        return 0.0
    return float(account.balance)


def get_account_info() -> dict:
    """Return full account info as a dict."""
    account = mt5.account_info()
    if account is None:
        return {}
    return {
        "login": account.login,
        "server": account.server,
        "balance": account.balance,
        "equity": account.equity,
        "margin": account.margin,
        "free_margin": account.margin_free,
        "leverage": account.leverage,
        "currency": account.currency,
        "profit": account.profit,
    }


def fetch_historical_data(
    symbol: str,
    timeframe: str = "H1",
    bars: int = 8000,
) -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV data from MT5.

    Parameters
    ----------
    symbol : str
        Trading symbol (e.g. "Volatility 75 Index", "EURUSD")
    timeframe : str
        Timeframe string: M1, M5, M15, M30, H1, H4, D1
    bars : int
        Number of bars to fetch

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns: open, high, low, close, volume
    """
    tf = TIMEFRAME_MAP.get(timeframe.upper())
    if tf is None:
        print(f"  ERROR: Unknown timeframe '{timeframe}'")
        print(f"  Valid: {', '.join(TIMEFRAME_MAP.keys())}")
        return None

    # Make sure the symbol is available
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"  ERROR: Symbol '{symbol}' not found in MT5.")
        print("  Available symbols with 'Volatility':")
        _list_symbols("Volatility")
        return None

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"  ERROR: Could not select symbol '{symbol}'")
            return None

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) == 0:
        print(f"  ERROR: No data returned for {symbol} {timeframe}")
        print(f"  MT5 error: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    df = df.rename(columns={
        "tick_volume": "volume",
    })
    # Keep only OHLCV columns
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df.astype(float)

    print(f"  Fetched {len(df)} bars of {symbol} ({timeframe})")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Price range: ${df['close'].min():.5f} - ${df['close'].max():.5f}")

    return df


def _list_symbols(filter_text: str = "") -> None:
    """List available symbols matching filter."""
    symbols = mt5.symbols_get()
    if symbols is None:
        return
    matches = [s.name for s in symbols if filter_text.lower() in s.name.lower()]
    for name in matches[:20]:
        print(f"    - {name}")
    if len(matches) > 20:
        print(f"    ... and {len(matches) - 20} more")


def get_symbol_info(symbol: str) -> Optional[dict]:
    """Get symbol trading specifications."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    return {
        "name": info.name,
        "point": info.point,
        "digits": info.digits,
        "spread": info.spread,
        "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
    }


def get_current_price(symbol: str) -> Optional[dict]:
    """Get current bid/ask for a symbol."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "time": datetime.fromtimestamp(tick.time),
    }


def place_market_order(
    symbol: str,
    direction: int,
    volume: float,
    sl: float = 0.0,
    tp: float = 0.0,
    comment: str = "TradingBot",
    deviation: int = 20,
) -> Optional[dict]:
    """
    Place a market order.

    Parameters
    ----------
    symbol : str
        Trading symbol
    direction : int
        +1 for BUY, -1 for SELL
    volume : float
        Lot size (will be rounded to symbol's volume_step)
    sl : float
        Stop loss price (0 = no SL)
    tp : float
        Take profit price (0 = no TP)
    comment : str
        Order comment
    deviation : int
        Max price deviation in points

    Returns
    -------
    dict or None
        Order result with ticket number, or None on failure
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"  ERROR: Symbol '{symbol}' not found")
        return None

    # Round volume to symbol's step
    vol_step = info.volume_step
    volume = max(info.volume_min, round(round(volume / vol_step) * vol_step, 8))
    volume = min(volume, info.volume_max)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"  ERROR: Cannot get price for '{symbol}'")
        return None

    if direction == 1:  # BUY
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:  # SELL
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 202602,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"  ERROR: Order send failed: {mt5.last_error()}")
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  ERROR: Order rejected: {result.comment} (code {result.retcode})")
        return None

    print(f"  ORDER FILLED: {'BUY' if direction == 1 else 'SELL'} "
          f"{volume} {symbol} @ {result.price}")
    if sl > 0:
        print(f"    SL: {sl:.5f}")
    if tp > 0:
        print(f"    TP: {tp:.5f}")
    print(f"    Ticket: {result.order}")

    return {
        "ticket": result.order,
        "price": result.price,
        "volume": result.volume,
        "symbol": symbol,
        "direction": direction,
    }


def modify_position(
    ticket: int,
    sl: float = 0.0,
    tp: float = 0.0,
) -> bool:
    """Modify SL/TP of an open position."""
    position = None
    positions = mt5.positions_get(ticket=ticket)
    if positions and len(positions) > 0:
        position = positions[0]

    if position is None:
        print(f"  ERROR: Position {ticket} not found")
        return False

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": position.symbol,
        "sl": sl if sl > 0 else position.sl,
        "tp": tp if tp > 0 else position.tp,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error = result.comment if result else mt5.last_error()
        print(f"  ERROR: Modify failed: {error}")
        return False

    print(f"  Position {ticket} modified: SL={sl:.5f} TP={tp:.5f}")
    return True


def close_position(ticket: int) -> bool:
    """Close an open position by ticket number."""
    position = None
    positions = mt5.positions_get(ticket=ticket)
    if positions and len(positions) > 0:
        position = positions[0]

    if position is None:
        print(f"  ERROR: Position {ticket} not found")
        return False

    symbol = position.symbol
    volume = position.volume
    # Reverse direction to close
    if position.type == mt5.ORDER_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if tick else 0
    else:
        order_type = mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if tick else 0

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 202602,
        "comment": "TradingBot close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error = result.comment if result else mt5.last_error()
        print(f"  ERROR: Close failed: {error}")
        return False

    print(f"  Position {ticket} closed @ {result.price}")
    return True


def get_open_positions(symbol: Optional[str] = None) -> list:
    """Get all open positions, optionally filtered by symbol."""
    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return []

    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "direction": 1 if p.type == mt5.ORDER_TYPE_BUY else -1,
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "time": datetime.fromtimestamp(p.time),
        }
        for p in positions
    ]
