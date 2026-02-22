"""Risk gate enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import List, Optional, Tuple

import MetaTrader5 as mt5

from claw_claw.state import Proposal, TradeState


@dataclass
class RiskDecision:
    allowed: bool
    reasons: List[str]
    volume: float


class RiskManager:
    def __init__(self, config: dict) -> None:
        self.config = config

    def _positions_for_symbol(self, symbol: str, magic: int) -> List:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [p for p in positions if p.magic == magic]

    def _current_spread_points(self, symbol: str) -> Optional[float]:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return None
        return (tick.ask - tick.bid) / info.point

    def _daily_drawdown_pct(self, state: TradeState, equity: float) -> float:
        if state.day_start_equity is None:
            state.day_start_equity = equity
            return 0.0
        drawdown = max(0.0, (state.day_start_equity - equity) / state.day_start_equity * 100)
        state.daily_drawdown_pct = drawdown
        return drawdown

    def _cooldown_active(self, state: TradeState) -> bool:
        if not state.last_trade_time:
            return False
        cooldown = timedelta(minutes=self.config["cooldown_minutes"])
        return datetime.now() - state.last_trade_time < cooldown

    def _normalize_volume(self, raw_volume: float, info) -> Optional[float]:
        step = info.volume_step
        if step <= 0:
            return None
        clamped = max(info.volume_min, min(raw_volume, info.volume_max, self.config["max_volume"]))
        stepped = math.floor(clamped / step) * step
        digits = max(0, len(str(step).split(".")[-1].rstrip("0"))) if "." in str(step) else 0
        normalized = round(stepped, digits)
        if normalized < info.volume_min:
            normalized = info.volume_min
        if normalized > self.config["max_volume"] or normalized > info.volume_max:
            normalized = min(self.config["max_volume"], info.volume_max)
        return float(normalized)

    def compute_volume(
        self,
        symbol: str,
        equity: float,
        sl_price: float,
        entry_price: float,
    ) -> Optional[float]:
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0:
            return None

        if info.trade_tick_size <= 0 or info.point <= 0:
            return None
        point_value = info.trade_tick_value / info.trade_tick_size
        if point_value <= 0:
            return None
        risk_amount = equity * (self.config["risk_per_trade_pct"] / 100)
        volume = risk_amount / (sl_distance / info.point * point_value)

        if volume <= 0:
            return None

        return self._normalize_volume(volume, info)


    def pyramid_allowed(
        self,
        proposal: Proposal,
        state: TradeState,
        equity: float,
    ) -> RiskDecision:
        reasons: List[str] = []
        if not self.config.get("pyramiding_enabled", False):
            return RiskDecision(False, ["Pyramiding disabled."], 0.0)

        positions = self._positions_for_symbol(proposal.symbol, self.config["magic"])
        if not positions:
            return RiskDecision(False, ["No base position to pyramid."], 0.0)
        base = positions[0]
        base_direction = "buy" if base.type == mt5.POSITION_TYPE_BUY else "sell"
        if proposal.direction != base_direction:
            return RiskDecision(False, ["Pyramid direction mismatch."], 0.0)

        if state.pyramid_entries_today >= int(self.config.get("max_pyramid_entries", 1)):
            return RiskDecision(False, ["Max pyramid entries reached."], 0.0)

        if proposal.confidence < float(self.config.get("pyramid_confidence_min", 0.75)):
            return RiskDecision(False, ["Pyramid confidence too low."], 0.0)

        spread_points = self._current_spread_points(proposal.symbol)
        if spread_points is None or spread_points > self.config["max_spread_points"]:
            return RiskDecision(False, ["Spread too high or unavailable."], 0.0)

        tick = mt5.symbol_info_tick(proposal.symbol)
        symbol_info = mt5.symbol_info(proposal.symbol)
        if tick is None or symbol_info is None or symbol_info.point <= 0:
            return RiskDecision(False, ["Tick/symbol info unavailable."], 0.0)

        entry_price = tick.ask if proposal.direction == "buy" else tick.bid
        risk_per_unit = abs(base.price_open - base.sl)
        if risk_per_unit <= 0:
            return RiskDecision(False, ["Base position has invalid SL risk."], 0.0)

        favorable_move = (entry_price - base.price_open) if proposal.direction == "buy" else (base.price_open - entry_price)
        trigger = risk_per_unit * float(self.config.get("pyramid_r_multiple_trigger", 1.0))
        if favorable_move < trigger:
            return RiskDecision(False, ["Pyramid trigger not reached."], 0.0)

        volume = self.compute_volume(proposal.symbol, equity, proposal.suggested_sl, entry_price)
        if volume is None:
            return RiskDecision(False, ["Volume computation failed."], 0.0)
        volume = volume * float(self.config.get("pyramid_volume_multiplier", 0.5))
        volume = self._normalize_volume(volume, symbol_info)
        if volume is None or volume <= 0:
            return RiskDecision(False, ["Pyramid volume invalid."], 0.0)

        if state.total_volume + volume > self.config["max_total_volume"]:
            return RiskDecision(False, ["Exposure cap reached."], 0.0)

        return RiskDecision(True, reasons, volume)

    def evaluate(
        self,
        proposal: Proposal,
        state: TradeState,
        equity: float,
    ) -> RiskDecision:
        reasons: List[str] = []
        allowed = True

        if proposal.symbol != self.config["resolved_symbol"]:
            allowed = False
            reasons.append("Symbol mismatch.")

        positions = self._positions_for_symbol(proposal.symbol, self.config["magic"])
        if self.config["one_trade_at_a_time"] and positions:
            allowed = False
            reasons.append("Existing position open.")

        if state.trades_today >= self.config["max_trades_per_day"]:
            allowed = False
            reasons.append("Max trades per day reached.")

        if self._cooldown_active(state):
            allowed = False
            reasons.append("Cooldown active.")

        spread_points = self._current_spread_points(proposal.symbol)
        if spread_points is None or spread_points > self.config["max_spread_points"]:
            allowed = False
            reasons.append("Spread too high or unavailable.")

        drawdown = self._daily_drawdown_pct(state, equity)
        if drawdown >= self.config["max_daily_loss_pct"]:
            allowed = False
            reasons.append("Daily loss limit breached.")

        if state.consecutive_losses >= self.config["max_consecutive_losses"]:
            allowed = False
            reasons.append("Consecutive loss circuit breaker.")

        symbol_info = mt5.symbol_info(proposal.symbol)
        if symbol_info is None:
            allowed = False
            reasons.append("Symbol info unavailable.")
            return RiskDecision(allowed, reasons, 0.0)

        if proposal.suggested_sl <= 0 or proposal.suggested_tp <= 0:
            allowed = False
            reasons.append("Invalid SL/TP.")

        min_sl = self.config["min_sl_points"] * symbol_info.point
        max_sl = self.config["max_sl_points"] * symbol_info.point
        tick = mt5.symbol_info_tick(proposal.symbol)
        if tick is None:
            allowed = False
            reasons.append("Tick unavailable.")
            return RiskDecision(allowed, reasons, 0.0)
        entry_price = tick.ask if proposal.direction == "buy" else tick.bid
        sl_distance = abs(entry_price - proposal.suggested_sl)
        if sl_distance < min_sl or sl_distance > max_sl:
            allowed = False
            reasons.append("SL distance out of bounds.")

        volume = self.compute_volume(proposal.symbol, equity, proposal.suggested_sl, entry_price)
        if volume is None:
            allowed = False
            reasons.append("Volume computation failed.")
            volume = 0.0

        if state.total_volume + volume > self.config["max_total_volume"]:
            allowed = False
            reasons.append("Exposure cap reached.")

        return RiskDecision(allowed, reasons, volume)
