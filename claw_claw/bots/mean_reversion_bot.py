"""Simple mean-reversion bot."""
from __future__ import annotations

from typing import Optional

from claw_claw.bots.base import BaseBot
from claw_claw.state import MarketContext, Proposal


class MeanReversionBot(BaseBot):
    @property
    def name(self) -> str:
        return "MeanReversionBot"

    def propose(self, market: MarketContext) -> Optional[Proposal]:
        candles = market.candles
        if len(candles) < 30:
            return None

        closes = [c["close"] for c in candles[-30:]]
        mean = sum(closes) / 30
        last_close = closes[-1]
        distance = (last_close - mean) / mean

        if distance > 0.002:
            direction = "sell"
        elif distance < -0.002:
            direction = "buy"
        else:
            return None

        sl = last_close * (1.004 if direction == "sell" else 0.996)
        tp = last_close * (0.996 if direction == "sell" else 1.004)
        return Proposal(
            bot_name=self.name,
            symbol=market.symbol,
            direction=direction,
            entry_type="market",
            suggested_sl=sl,
            suggested_tp=tp,
            confidence=0.52,
            rationale="MeanReversionBot: price deviation from 30-period mean.",
        )
