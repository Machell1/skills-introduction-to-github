"""Simple trend-following bot."""
from __future__ import annotations

from typing import Optional

from claw_claw.bots.base import BaseBot
from claw_claw.state import MarketContext, Proposal


class TrendBot(BaseBot):
    @property
    def name(self) -> str:
        return "TrendBot"

    def propose(self, market: MarketContext) -> Optional[Proposal]:
        candles = market.candles
        if len(candles) < 20:
            return None

        closes = [c["close"] for c in candles[-20:]]
        short = sum(closes[-5:]) / 5
        long = sum(closes) / 20
        direction = None
        if short > long * 1.001:
            direction = "buy"
        elif short < long * 0.999:
            direction = "sell"

        if direction is None:
            return None

        last_close = candles[-1]["close"]
        sl = last_close * (0.995 if direction == "buy" else 1.005)
        tp = last_close * (1.008 if direction == "buy" else 0.992)
        return Proposal(
            bot_name=self.name,
            symbol=market.symbol,
            direction=direction,
            entry_type="market",
            suggested_sl=sl,
            suggested_tp=tp,
            confidence=0.55,
            rationale="TrendBot: short vs long moving average bias.",
        )
