"""Monitor open positions for safety exits."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

import MetaTrader5 as mt5

from claw_claw.state import PositionSnapshot, TradeState
from claw_claw.utils import kill_switch_triggered


class TradeMonitor:
    def __init__(self, config: dict, project_root, logger, audit_db) -> None:
        self.config = config
        self.project_root = project_root
        self.logger = logger
        self.audit_db = audit_db

    def snapshot_position(self, symbol: str, magic: int) -> Optional[PositionSnapshot]:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return None
        for pos in positions:
            if pos.magic != magic:
                continue
            direction = "buy" if pos.type == mt5.POSITION_TYPE_BUY else "sell"
            return PositionSnapshot(
                ticket=pos.ticket,
                symbol=pos.symbol,
                volume=pos.volume,
                price_open=pos.price_open,
                sl=pos.sl,
                tp=pos.tp,
                time_open=datetime.fromtimestamp(pos.time),
                direction=direction,
                risk_amount=0.0,
            )
        return None

    def _close_position(self, snapshot: PositionSnapshot) -> None:
        tick = mt5.symbol_info_tick(snapshot.symbol)
        if tick is None:
            return
        price = tick.bid if snapshot.direction == "buy" else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": snapshot.symbol,
            "volume": snapshot.volume,
            "type": mt5.ORDER_TYPE_SELL if snapshot.direction == "buy" else mt5.ORDER_TYPE_BUY,
            "position": snapshot.ticket,
            "price": price,
            "deviation": self.config["deviation_points"],
            "magic": self.config["magic"],
            "comment": f"{self.config['comment']}_exit",
        }
        mt5.order_send(request)

    def monitor(self, state: TradeState, snapshot: PositionSnapshot) -> None:
        while True:
            if kill_switch_triggered(self.project_root):
                if self.config["flatten_on_kill_switch"]:
                    self.logger.info("Kill switch active: flattening position.")
                    self._close_position(snapshot)
                break

            position = self.snapshot_position(snapshot.symbol, self.config["magic"])
            if position is None:
                break

            open_duration = datetime.now() - position.time_open
            if open_duration > timedelta(minutes=self.config["max_minutes_in_trade"]):
                self.logger.info("Time-based exit triggered.")
                self._close_position(position)
                break

            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                time.sleep(1)
                continue

            price = tick.bid if position.direction == "buy" else tick.ask
            unrealized_points = (price - position.price_open) if position.direction == "buy" else (position.price_open - price)
            loss_points = max(0.0, -unrealized_points)
            risk_points = abs(position.price_open - position.sl)
            if risk_points > 0:
                target = risk_points * self.config["break_even_r_multiple"]
                if unrealized_points >= target:
                    desired_sl = position.price_open
                    if (position.direction == "buy" and position.sl < desired_sl) or (
                        position.direction == "sell" and position.sl > desired_sl
                    ):
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": position.ticket,
                            "sl": desired_sl,
                            "tp": position.tp,
                        }
                        mt5.order_send(request)
            if snapshot.risk_amount > 0:
                info = mt5.symbol_info(position.symbol)
                if info is not None:
                    point_value = info.trade_tick_value / info.trade_tick_size
                    loss_value = (loss_points / info.point) * point_value * position.volume
                    if loss_value >= (snapshot.risk_amount * (self.config["stake_loss_cut_pct"] / 100)):
                        self.logger.info("Loss exceeds stake threshold. Closing position.")
                        self._close_position(position)
                        break

            time.sleep(1)

        state.open_position_ticket = None
