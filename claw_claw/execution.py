"""Order execution engine."""
from __future__ import annotations

import time
from typing import Optional

import MetaTrader5 as mt5

from claw_claw.state import Proposal


class ExecutionEngine:
    def __init__(self, config: dict, logger) -> None:
        self.config = config
        self.logger = logger

    def _filling_mode(self, symbol: str) -> int:
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_IOC
        if info.filling_mode == mt5.SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        if info.filling_mode == mt5.SYMBOL_FILLING_RETURN:
            return mt5.ORDER_FILLING_RETURN
        return mt5.ORDER_FILLING_IOC

    def _normalize_price(self, symbol: str, price: float) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return price
        return round(price, int(info.digits))

    def send_order(self, proposal: Proposal, volume: float) -> Optional[int]:
        tick = mt5.symbol_info_tick(proposal.symbol)
        if tick is None:
            self.logger.info("Execution aborted: tick unavailable.")
            return None

        price = tick.ask if proposal.direction == "buy" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": proposal.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if proposal.direction == "buy" else mt5.ORDER_TYPE_SELL,
            "price": self._normalize_price(proposal.symbol, price),
            "sl": self._normalize_price(proposal.symbol, proposal.suggested_sl),
            "tp": self._normalize_price(proposal.symbol, proposal.suggested_tp),
            "deviation": self.config["deviation_points"],
            "magic": self.config["magic"],
            "comment": self.config["comment"],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(proposal.symbol),
        }

        check = mt5.order_check(request)
        if check is None:
            self.logger.info("Order check failed: no result.")
            return None
        if check.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.info("Order check failed retcode=%s", check.retcode)
            return None

        result = mt5.order_send(request)
        if result is None:
            self.logger.info("Order send failed: no result.")
            return None

        if result.retcode in (mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_PRICE_CHANGED):
            time.sleep(0.5)
            tick = mt5.symbol_info_tick(proposal.symbol)
            if tick is None:
                self.logger.info("Retry aborted: tick unavailable.")
                return None
            request["price"] = self._normalize_price(
                proposal.symbol,
                tick.ask if proposal.direction == "buy" else tick.bid,
            )
            result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.info("Order failed retcode=%s", result.retcode)
            return None

        self.logger.info("Order executed ticket=%s", result.order)
        return int(result.order)
