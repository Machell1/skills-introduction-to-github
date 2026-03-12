"""MetaTrader 5 connection utilities."""
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import MetaTrader5 as mt5


def initialize(
    auto_login: bool = False,
    terminal_path: Optional[str] = None,
    data_path: Optional[str] = None,
    portable: bool = False,
) -> bool:
    """Initialize MT5. Optionally log in via environment variables (disabled by default)."""
    init_kwargs = {}
    if terminal_path:
        init_kwargs["path"] = terminal_path
    if data_path:
        init_kwargs["data_path"] = data_path
    if portable:
        init_kwargs["portable"] = True

    if not auto_login:
        return mt5.initialize(**init_kwargs)

    # Prefer attaching to the already logged-in terminal first to avoid forced reconnects.
    if mt5.initialize(**init_kwargs):
        terminal_info = mt5.terminal_info()
        if terminal_info is not None and terminal_info.connected:
            return True

    # WARNING: auto login reads credentials from environment variables only.
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if not login or not password or not server:
        return False
    return mt5.initialize(
        login=int(login), password=password, server=server, **init_kwargs
    )


def connect(
    auto_login: bool = False,
    retries: int = 3,
    delay_seconds: float = 2.0,
    terminal_path: Optional[str] = None,
    data_path: Optional[str] = None,
    portable: bool = False,
) -> Tuple[bool, str]:
    """Attempt to connect to MT5 with retries, returning a status message."""
    last_error = None
    for attempt in range(1, retries + 1):
        if initialize(
            auto_login=auto_login,
            terminal_path=terminal_path,
            data_path=data_path,
            portable=portable,
        ) and is_connected():
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


def trading_permissions() -> Tuple[bool, str]:
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        return False, "MT5 terminal info unavailable."
    if not terminal_info.connected:
        return False, "MT5 terminal is not connected."
    if not terminal_info.trade_allowed:
        return False, "Terminal trading is disabled."
    if hasattr(terminal_info, "trade_expert") and not terminal_info.trade_expert:
        return False, "Algo trading is disabled in MT5 terminal settings."
    account = mt5.account_info()
    if account is None:
        return False, "MT5 account info unavailable."
    if not account.trade_allowed:
        return False, "Trading is disabled for the account."
    return True, "Trading permissions confirmed."


def account_equity() -> Optional[float]:
    info = mt5.account_info()
    if info is None:
        return None
    return float(info.equity)
