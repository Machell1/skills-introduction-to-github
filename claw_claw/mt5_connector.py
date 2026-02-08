"""MetaTrader 5 connection utilities."""
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import MetaTrader5 as mt5


def initialize(auto_login: bool = False) -> bool:
    """Initialize MT5. Optionally log in via environment variables (disabled by default)."""
    if not auto_login:
        return mt5.initialize()

    # Prefer attaching to the already logged-in terminal first to avoid forced reconnects.
    if mt5.initialize():
        terminal_info = mt5.terminal_info()
        if terminal_info is not None and terminal_info.connected:
            return True

    # WARNING: auto login reads credentials from environment variables only.
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if not login or not password or not server:
        return False
    return mt5.initialize(login=int(login), password=password, server=server)


def connect(
    auto_login: bool = False, retries: int = 3, delay_seconds: float = 2.0
) -> Tuple[bool, str]:
    """Attempt to connect to MT5 with retries, returning a status message."""
    last_error = None
    for attempt in range(1, retries + 1):
        if initialize(auto_login=auto_login) and is_connected():
            return True, "Connected to MT5."
        last_error = mt5.last_error()
        time.sleep(delay_seconds)
    return False, f"MT5 connection failed after {retries} attempts. Last error: {last_error}"


def shutdown() -> None:
    mt5.shutdown()


def is_connected() -> bool:
    terminal_info = mt5.terminal_info()
    return terminal_info is not None and terminal_info.connected


def is_ready() -> bool:
    terminal_info = mt5.terminal_info()
    if terminal_info is None or not terminal_info.connected:
        return False
    account = mt5.account_info()
    return account is not None


def account_equity() -> Optional[float]:
    info = mt5.account_info()
    if info is None:
        return None
    return float(info.equity)
