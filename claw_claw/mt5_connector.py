"""MetaTrader 5 connection utilities."""
from __future__ import annotations

import os
from typing import Optional

import MetaTrader5 as mt5


def initialize(auto_login: bool = False) -> bool:
    """Initialize MT5. Optionally log in via environment variables (disabled by default)."""
    if not auto_login:
        return mt5.initialize()

    # WARNING: auto login reads credentials from environment variables only.
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if not login or not password or not server:
        return False
    return mt5.initialize(login=int(login), password=password, server=server)


def shutdown() -> None:
    mt5.shutdown()


def is_connected() -> bool:
    terminal_info = mt5.terminal_info()
    return terminal_info is not None and terminal_info.connected


def account_equity() -> Optional[float]:
    info = mt5.account_info()
    if info is None:
        return None
    return float(info.equity)
