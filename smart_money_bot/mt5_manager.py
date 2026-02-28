"""
MT5 Connection and Data Manager.
Handles all interaction with the MetaTrader 5 platform via the MetaTrader5 Python package.
Adapts dynamically to any equity account connected through Deriv.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from .config import MT5Config, BotConfig
from .models import Candle, DailyLevels

logger = logging.getLogger(__name__)

# MT5 timeframe mapping
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}

# MT5 fill type mapping
FILL_TYPE_MAP = {
    "FOK": mt5.ORDER_FILLING_FOK,
    "IOC": mt5.ORDER_FILLING_IOC,
    "RETURN": mt5.ORDER_FILLING_RETURN,
}


class MT5Manager:
    """Manages the MT5 connection, data retrieval, and order execution."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.mt5_config = config.mt5
        self._connected = False
        self._symbol_info = None
        self._account_info = None

    # ── Connection ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialize MT5 and log in to the trading account."""
        init_kwargs = {}
        if self.mt5_config.path:
            init_kwargs["path"] = self.mt5_config.path
        if self.mt5_config.login:
            init_kwargs["login"] = self.mt5_config.login
            init_kwargs["password"] = self.mt5_config.password
            init_kwargs["server"] = self.mt5_config.server

        if not mt5.initialize(**init_kwargs):
            logger.error("MT5 initialization failed: %s", mt5.last_error())
            return False

        if self.mt5_config.login and not mt5.login(
            self.mt5_config.login,
            password=self.mt5_config.password,
            server=self.mt5_config.server,
        ):
            logger.error("MT5 login failed: %s", mt5.last_error())
            mt5.shutdown()
            return False

        self._connected = True
        self._refresh_account_info()
        self._refresh_symbol_info()

        logger.info(
            "Connected to MT5 | Account: %d | Server: %s | Balance: %.2f %s",
            self.account_login,
            self.account_server,
            self.account_balance,
            self.account_currency,
        )
        return True

    def disconnect(self):
        """Shutdown MT5 connection."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("Disconnected from MT5")

    def is_connected(self) -> bool:
        """Check if MT5 terminal is still responsive."""
        if not self._connected:
            return False
        info = mt5.terminal_info()
        if info is None:
            self._connected = False
            return False
        return info.connected

    # ── Account Info (Dynamic Adaptation) ─────────────────────────

    def _refresh_account_info(self):
        self._account_info = mt5.account_info()

    def _refresh_symbol_info(self):
        self._symbol_info = mt5.symbol_info(self.mt5_config.symbol)
        if self._symbol_info is None:
            logger.warning("Symbol %s not found, attempting to enable it", self.mt5_config.symbol)
            mt5.symbol_select(self.mt5_config.symbol, True)
            self._symbol_info = mt5.symbol_info(self.mt5_config.symbol)

    @property
    def account_login(self) -> int:
        self._refresh_account_info()
        return self._account_info.login if self._account_info else 0

    @property
    def account_server(self) -> str:
        self._refresh_account_info()
        return self._account_info.server if self._account_info else ""

    @property
    def account_balance(self) -> float:
        self._refresh_account_info()
        return self._account_info.balance if self._account_info else 0.0

    @property
    def account_equity(self) -> float:
        self._refresh_account_info()
        return self._account_info.equity if self._account_info else 0.0

    @property
    def account_currency(self) -> str:
        self._refresh_account_info()
        return self._account_info.currency if self._account_info else "USD"

    @property
    def account_leverage(self) -> int:
        self._refresh_account_info()
        return self._account_info.leverage if self._account_info else 1

    @property
    def account_margin_free(self) -> float:
        self._refresh_account_info()
        return self._account_info.margin_free if self._account_info else 0.0

    # ── Symbol Info ───────────────────────────────────────────────

    @property
    def symbol_point(self) -> float:
        """Smallest price change (point value)."""
        self._refresh_symbol_info()
        return self._symbol_info.point if self._symbol_info else 0.01

    @property
    def symbol_digits(self) -> int:
        self._refresh_symbol_info()
        return self._symbol_info.digits if self._symbol_info else 2

    @property
    def symbol_contract_size(self) -> float:
        """
        Contract size (Q ounces per lot).
        Deriv typically uses 100 oz per lot for XAUUSD, but this reads it dynamically.
        """
        self._refresh_symbol_info()
        return self._symbol_info.trade_contract_size if self._symbol_info else 100.0

    @property
    def symbol_volume_min(self) -> float:
        self._refresh_symbol_info()
        return self._symbol_info.volume_min if self._symbol_info else 0.01

    @property
    def symbol_volume_max(self) -> float:
        self._refresh_symbol_info()
        return self._symbol_info.volume_max if self._symbol_info else 100.0

    @property
    def symbol_volume_step(self) -> float:
        self._refresh_symbol_info()
        return self._symbol_info.volume_step if self._symbol_info else 0.01

    @property
    def current_spread_points(self) -> float:
        """Current spread in points."""
        self._refresh_symbol_info()
        return self._symbol_info.spread if self._symbol_info else 0

    @property
    def current_ask(self) -> float:
        self._refresh_symbol_info()
        return self._symbol_info.ask if self._symbol_info else 0.0

    @property
    def current_bid(self) -> float:
        self._refresh_symbol_info()
        return self._symbol_info.bid if self._symbol_info else 0.0

    # ── Data Retrieval ────────────────────────────────────────────

    def get_candles(
        self,
        timeframe: str = "H1",
        count: int = 500,
        from_date: Optional[datetime] = None,
    ) -> list[Candle]:
        """
        Retrieve OHLC candles from MT5.

        Args:
            timeframe: MT5 timeframe string (e.g., "H1", "D1").
            count: Number of candles to retrieve.
            from_date: If provided, get candles from this date forward.

        Returns:
            List of Candle objects, oldest first.
        """
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            logger.error("Unknown timeframe: %s", timeframe)
            return []

        if from_date:
            rates = mt5.copy_rates_from(self.mt5_config.symbol, tf, from_date, count)
        else:
            rates = mt5.copy_rates_from_pos(self.mt5_config.symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            logger.error("Failed to get candles: %s", mt5.last_error())
            return []

        candles = []
        for i, r in enumerate(rates):
            candles.append(Candle(
                time=datetime.utcfromtimestamp(r["time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["tick_volume"]),
                index=i,
            ))
        return candles

    def get_daily_candles(self, count: int = 10) -> list[Candle]:
        """Retrieve daily candles for PDH/PDL computation."""
        return self.get_candles(timeframe="D1", count=count)

    def get_daily_levels(self) -> DailyLevels:
        """
        Compute Previous Day High/Low and Current Day High/Low from daily candles.
        Uses the last 3 daily candles to handle timezone edge cases.
        """
        daily = self.get_daily_candles(count=3)
        if len(daily) < 2:
            logger.warning("Insufficient daily candles for PDH/PDL")
            return DailyLevels()

        prev_day = daily[-2]
        curr_day = daily[-1]

        return DailyLevels(
            pdh=prev_day.high,
            pdl=prev_day.low,
            current_day_high=curr_day.high,
            current_day_low=curr_day.low,
            date=curr_day.time,
        )

    def get_current_price(self) -> tuple[float, float]:
        """Return (bid, ask) for the symbol."""
        tick = mt5.symbol_info_tick(self.mt5_config.symbol)
        if tick is None:
            logger.error("Failed to get tick: %s", mt5.last_error())
            return 0.0, 0.0
        return tick.bid, tick.ask

    # ── Order Execution ───────────────────────────────────────────

    def _get_fill_type(self) -> int:
        """Determine the appropriate fill type for the broker."""
        return FILL_TYPE_MAP.get(self.mt5_config.fill_type, mt5.ORDER_FILLING_IOC)

    def _normalize_volume(self, volume: float) -> float:
        """Round volume to the nearest valid step."""
        step = self.symbol_volume_step
        vol_min = self.symbol_volume_min
        vol_max = self.symbol_volume_max
        normalized = max(vol_min, min(vol_max, round(volume / step) * step))
        return round(normalized, 8)

    def _normalize_price(self, price: float) -> float:
        """Round price to symbol's digit precision."""
        return round(price, self.symbol_digits)

    def place_buy_limit(
        self, price: float, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """
        Place a buy limit order.

        Returns:
            Order ticket number, or None on failure.
        """
        price = self._normalize_price(price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY_LIMIT,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Buy limit failed: %s", result)
            return None

        logger.info("Buy limit placed: ticket=%d, price=%.2f, vol=%.2f", result.order, price, volume)
        return result.order

    def place_sell_limit(
        self, price: float, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """Place a sell limit order."""
        price = self._normalize_price(price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL_LIMIT,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Sell limit failed: %s", result)
            return None

        logger.info("Sell limit placed: ticket=%d, price=%.2f, vol=%.2f", result.order, price, volume)
        return result.order

    def place_buy_stop(
        self, price: float, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """
        Place a buy stop order (entry ABOVE current ask).
        Triggers when price rises to the stop level — used for breakout entries.
        """
        price = self._normalize_price(price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY_STOP,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Buy stop failed: %s", result)
            return None

        logger.info("Buy stop placed: ticket=%d, price=%.2f, vol=%.2f", result.order, price, volume)
        return result.order

    def place_sell_stop(
        self, price: float, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """
        Place a sell stop order (entry BELOW current bid).
        Triggers when price falls to the stop level — used for breakdown entries.
        """
        price = self._normalize_price(price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL_STOP,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Sell stop failed: %s", result)
            return None

        logger.info("Sell stop placed: ticket=%d, price=%.2f, vol=%.2f", result.order, price, volume)
        return result.order

    def place_buy_stop_limit(
        self, trigger_price: float, limit_price: float, volume: float,
        sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """
        Place a buy stop-limit order.
        When price rises to trigger_price (stoplimit), a buy limit at limit_price is activated.
        Rule: trigger_price > Ask, limit_price < trigger_price.
        """
        trigger_price = self._normalize_price(trigger_price)
        limit_price = self._normalize_price(limit_price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY_STOP_LIMIT,
            "price": limit_price,
            "stoplimit": trigger_price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Buy stop-limit failed: %s", result)
            return None

        logger.info(
            "Buy stop-limit placed: ticket=%d, trigger=%.2f, limit=%.2f, vol=%.2f",
            result.order, trigger_price, limit_price, volume,
        )
        return result.order

    def place_sell_stop_limit(
        self, trigger_price: float, limit_price: float, volume: float,
        sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """
        Place a sell stop-limit order.
        When price falls to trigger_price (stoplimit), a sell limit at limit_price is activated.
        Rule: trigger_price < Bid, limit_price > trigger_price.
        """
        trigger_price = self._normalize_price(trigger_price)
        limit_price = self._normalize_price(limit_price)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)
        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL_STOP_LIMIT,
            "price": limit_price,
            "stoplimit": trigger_price,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Sell stop-limit failed: %s", result)
            return None

        logger.info(
            "Sell stop-limit placed: ticket=%d, trigger=%.2f, limit=%.2f, vol=%.2f",
            result.order, trigger_price, limit_price, volume,
        )
        return result.order

    def place_buy_market(
        self, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """Place an instant buy (market) order."""
        volume = self._normalize_volume(volume)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": self.current_ask,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Buy market failed: %s", result)
            return None

        logger.info("Buy market filled: ticket=%d, vol=%.2f", result.order, volume)
        return result.order

    def place_sell_market(
        self, volume: float, sl: float, tp: float, comment: str = ""
    ) -> Optional[int]:
        """Place an instant sell (market) order."""
        volume = self._normalize_volume(volume)
        sl = self._normalize_price(sl)
        tp = self._normalize_price(tp)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5_config.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL,
            "price": self.current_bid,
            "sl": sl,
            "tp": tp,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": comment,
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Sell market failed: %s", result)
            return None

        logger.info("Sell market filled: ticket=%d, vol=%.2f", result.order, volume)
        return result.order

    def modify_position_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify the stop loss of an open position (for break-even moves)."""
        new_sl = self._normalize_price(new_sl)
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.error("Position %d not found for SL modification", ticket)
            return False

        pos = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.mt5_config.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": pos.tp,
            "magic": self.mt5_config.magic_number,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("SL modification failed for ticket %d: %s", ticket, result)
            return False

        logger.info("SL modified for ticket %d: new SL=%.2f", ticket, new_sl)
        return True

    def cancel_pending_order(self, ticket: int) -> bool:
        """Cancel a pending (limit) order."""
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Cancel order failed for ticket %d: %s", ticket, result)
            return False

        logger.info("Pending order cancelled: ticket=%d", ticket)
        return True

    def partial_close_position(self, ticket: int, close_fraction: float = 0.5) -> bool:
        """Close a fraction of an open position at market (for partial take profit)."""
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.warning("Position %d not found for partial close", ticket)
            return False

        pos = positions[0]
        close_volume = self._normalize_volume(pos.volume * close_fraction)
        if close_volume <= 0:
            logger.warning("Partial close volume too small for ticket %d", ticket)
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_price = self.current_bid if pos.type == mt5.ORDER_TYPE_BUY else self.current_ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5_config.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": "SMC_PARTIAL",
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Partial close failed for ticket %d: %s", ticket, result)
            return False

        logger.info(
            "Partial close: ticket=%d, closed %.4f of %.4f lots (%.0f%%)",
            ticket, close_volume, pos.volume, close_fraction * 100,
        )
        return True

    def close_position(self, ticket: int) -> bool:
        """Close an open position at market."""
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.warning("Position %d not found (may already be closed)", ticket)
            return True

        pos = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_price = self.current_bid if pos.type == mt5.ORDER_TYPE_BUY else self.current_ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5_config.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": self.mt5_config.deviation,
            "magic": self.mt5_config.magic_number,
            "comment": "SMC_CLOSE",
            "type_filling": self._get_fill_type(),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Close position failed for ticket %d: %s", ticket, result)
            return False

        logger.info("Position closed: ticket=%d", ticket)
        return True

    def get_open_positions(self) -> list:
        """Get all open positions for the configured symbol and magic number."""
        positions = mt5.positions_get(symbol=self.mt5_config.symbol)
        if positions is None:
            return []
        return [p for p in positions if p.magic == self.mt5_config.magic_number]

    def get_pending_orders(self) -> list:
        """Get all pending orders for the configured symbol and magic number."""
        orders = mt5.orders_get(symbol=self.mt5_config.symbol)
        if orders is None:
            return []
        return [o for o in orders if o.magic == self.mt5_config.magic_number]

    def is_position_open(self, ticket: int) -> bool:
        """Check if a specific position is still open."""
        positions = mt5.positions_get(ticket=ticket)
        return positions is not None and len(positions) > 0

    def get_position_open_price(self, ticket: int) -> Optional[float]:
        """Get the actual fill/open price for a position."""
        positions = mt5.positions_get(ticket=ticket)
        if positions and len(positions) > 0:
            return positions[0].price_open
        return None

    def is_order_pending(self, ticket: int) -> bool:
        """Check if a specific pending order is still active."""
        orders = mt5.orders_get(ticket=ticket)
        return orders is not None and len(orders) > 0
