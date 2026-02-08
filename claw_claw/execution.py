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
            "price": price,
            "sl": proposal.suggested_sl,
            "tp": proposal.suggested_tp,
            "deviation": self.config["deviation_points"],
            "magic": self.config["magic"],
            "comment": self.config["comment"],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result is None:
            self.logger.info("Order send failed: no result.")
            return None

        if result.retcode == mt5.TRADE_RETCODE_REQUOTE:
            time.sleep(0.5)
            result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.info("Order failed retcode=%s", result.retcode)
            return None

        self.logger.info("Order executed ticket=%s", result.order)
        return int(result.order)
