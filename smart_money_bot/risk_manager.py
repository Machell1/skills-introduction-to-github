"""
Risk Management and Position Sizing Engine.

Implements:
- Fractional risk-based position sizing (equity * r / (D * Q))
- Dynamic adaptation to any equity account
- Exposure limits (single-position, daily loss cap, weekly drawdown brake)
- Spread/volatility filters
- Rolling performance tracking for drawdown brakes
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from .config import BotConfig
from .models import PerformanceMetrics, TradeResult, TradeSetup

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages position sizing, exposure limits, and drawdown controls.
    Adapts dynamically to any equity account.
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.metrics = PerformanceMetrics()

        # Trade history for rolling calculations
        self._trade_history: deque[TradeSetup] = deque(maxlen=1000)
        self._recent_trades: deque[TradeSetup] = deque(maxlen=config.risk.rolling_trade_window)

        # Daily tracking
        self._daily_pnl: float = 0.0
        self._daily_date: Optional[datetime] = None

        # Peak equity tracking
        self._peak_equity: float = 0.0

        # Drawdown brake state
        self._risk_reduced: bool = False

        # Hard drawdown halt state (circuit breaker)
        self._hard_halt_active: bool = False

    # ── Position Sizing ───────────────────────────────────────────

    def calculate_lot_size(
        self,
        equity: float,
        stop_distance: float,
        contract_size: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> float:
        """
        Calculate position size using fractional risk formula:

            Units (lots) = (Equity × r) / (D × Q)

        Where:
            r = risk per trade as fraction of equity
            D = |entry - stop| in price units (USD per ounce)
            Q = contract size (ounces per lot)

        This formulation:
        - Automatically adjusts to gold volatility (D scales with ATR)
        - Works for any equity size and leverage
        - Keeps risk constant in equity terms regardless of price level

        Args:
            equity: Current account equity
            stop_distance: |entry - stop| in price units
            contract_size: Ounces per lot (e.g., 100 for standard XAUUSD)
            volume_min: Broker minimum lot size
            volume_max: Broker maximum lot size
            volume_step: Broker lot step size

        Returns:
            Lot size rounded to broker volume step.
        """
        if stop_distance <= 0 or contract_size <= 0 or equity <= 0:
            logger.error(
                "Invalid sizing inputs: equity=%.2f, stop_dist=%.4f, contract=%.1f",
                equity, stop_distance, contract_size,
            )
            return 0.0

        r = self._get_effective_risk_fraction()
        risk_amount = equity * r  # Dollar amount at risk

        # Position size in lots
        lots = risk_amount / (stop_distance * contract_size)

        # Normalize to broker constraints: round to step first, then clamp
        lots = round(lots / volume_step) * volume_step
        lots = max(volume_min, min(volume_max, lots))
        lots = round(lots, 8)

        logger.info(
            "Position sizing: equity=%.2f, r=%.4f, risk_amt=%.2f, "
            "stop_dist=%.2f, contract=%.1f, lots=%.4f",
            equity, r, risk_amount, stop_distance, contract_size, lots,
        )

        return lots

    def _get_effective_risk_fraction(self) -> float:
        """
        Get the effective risk-per-trade fraction, accounting for:
        1. Kelly criterion (when enough history exists)
        2. Drawdown brakes
        """
        base_r = self.config.risk.risk_per_trade_pct / 100.0

        # Kelly criterion: after 50+ trades, use data-driven sizing
        kelly_r = self._compute_kelly_fraction()
        if kelly_r is not None:
            base_r = kelly_r

        if self._risk_reduced:
            effective_r = base_r * self.config.risk.risk_reduction_factor
            logger.info(
                "Risk REDUCED: base=%.4f, effective=%.4f (drawdown brake active)",
                base_r, effective_r,
            )
            return effective_r

        return base_r

    def _compute_kelly_fraction(self) -> Optional[float]:
        """
        Compute fractional Kelly criterion position sizing.

        Kelly formula: f* = (p*b - q) / b
        Where: p = win rate, q = 1-p, b = avg_win / avg_loss

        Uses 25% Kelly (quarter-Kelly) for safety.
        Requires 50+ trade history to activate.
        Capped at 2% max, floored at 0.1%.

        Returns:
            Kelly-optimal risk fraction, or None if insufficient history.
        """
        min_trades = 50
        if len(self._trade_history) < min_trades:
            return None

        trades = list(self._trade_history)
        wins = [t for t in trades if t.result and t.result.value == "win"]
        losses = [t for t in trades if t.result and t.result.value == "loss"]

        if not wins or not losses:
            return None

        p = len(wins) / len(trades)  # Win probability
        q = 1.0 - p
        avg_win = sum(t.realized_r for t in wins) / len(wins)
        avg_loss = sum(abs(t.realized_r) for t in losses) / len(losses)

        if avg_loss <= 0:
            return None

        b = avg_win / avg_loss  # Win/loss ratio

        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            # Negative Kelly = no edge, use minimum
            logger.info("Kelly criterion negative (%.4f) — no statistical edge detected", kelly_full)
            return 0.001  # 0.1% floor

        # Quarter-Kelly for safety
        kelly_fraction = 0.25 * kelly_full

        # Clamp to [0.1%, 2.0%]
        kelly_fraction = max(0.001, min(0.02, kelly_fraction))

        logger.info(
            "Kelly sizing: p=%.2f, b=%.2f, full_kelly=%.4f, quarter_kelly=%.4f (%d trades)",
            p, b, kelly_full, kelly_fraction, len(trades),
        )
        return kelly_fraction

    # ── Exposure Checks ───────────────────────────────────────────

    def can_open_trade(
        self,
        equity: float,
        current_open_positions: int,
        current_spread_points: float,
        current_atr: float,
        atr_history: list[float],
    ) -> tuple[bool, str]:
        """
        Run all pre-trade risk checks.

        Returns:
            (allowed, reason) — True if trade is allowed, else False with reason.
        """
        # 0. HARD DRAWDOWN CIRCUIT BREAKER — highest priority check
        if self._hard_halt_active:
            return False, (
                f"HARD DRAWDOWN HALT ACTIVE: drawdown {self.metrics.current_drawdown_pct:.2f}% "
                f"exceeded {self.config.risk.max_drawdown_halt_pct}% — "
                f"resumes at {self.config.risk.hard_drawdown_resume_pct}%"
            )

        # 1. Maximum positions check
        if current_open_positions >= self.config.risk.max_positions:
            return False, f"Max positions reached ({self.config.risk.max_positions})"

        # 1b. Total open risk check
        total_open_risk = current_open_positions * self.config.risk.risk_per_trade_pct
        if total_open_risk >= self.config.risk.max_total_open_risk_pct:
            return False, f"Total open risk {total_open_risk:.2f}% >= cap {self.config.risk.max_total_open_risk_pct}%"

        # 2. Daily loss limit check
        if self._daily_pnl < 0:
            daily_loss_pct = abs(self._daily_pnl) / equity * 100.0 if equity > 0 else 0
            if daily_loss_pct >= self.config.risk.daily_loss_limit_pct:
                return False, f"Daily loss limit hit: {daily_loss_pct:.2f}% >= {self.config.risk.daily_loss_limit_pct}%"

        # 3. Spread filter
        if self.config.execution.max_spread_points > 0:
            if current_spread_points > self.config.execution.max_spread_points:
                return False, f"Spread too wide: {current_spread_points} > {self.config.execution.max_spread_points}"

        # 4. Volatility filter (ATR percentile)
        if self.config.execution.volatility_filter_enabled and atr_history:
            sorted_atr = sorted(atr_history)
            percentile_idx = int(len(sorted_atr) * self.config.execution.volatility_filter_atr_percentile / 100.0)
            percentile_idx = min(percentile_idx, len(sorted_atr) - 1)
            threshold = sorted_atr[percentile_idx]
            if current_atr > threshold:
                return False, f"ATR too high: {current_atr:.2f} > {threshold:.2f} ({self.config.execution.volatility_filter_atr_percentile}th percentile)"

        # 5. Equity sanity check
        if equity <= 0:
            return False, "Zero or negative equity"

        return True, "OK"

    # ── Drawdown Monitoring ───────────────────────────────────────

    def update_equity(self, equity: float):
        """Track peak equity and current drawdown."""
        if equity > self._peak_equity:
            self._peak_equity = equity
            self.metrics.peak_equity = equity

        self.metrics.current_equity = equity

        if self._peak_equity > 0:
            dd = (self._peak_equity - equity) / self._peak_equity * 100.0
            self.metrics.current_drawdown_pct = dd
            if dd > self.metrics.max_drawdown_pct:
                self.metrics.max_drawdown_pct = dd

            # Hard drawdown circuit breaker (halt at threshold, resume at recovery)
            if dd >= self.config.risk.max_drawdown_halt_pct:
                if not self._hard_halt_active:
                    self._hard_halt_active = True
                    logger.critical(
                        "HARD DRAWDOWN HALT ENGAGED: drawdown %.2f%% >= %.2f%% threshold. "
                        "All trading suspended until drawdown recovers to %.2f%%.",
                        dd, self.config.risk.max_drawdown_halt_pct,
                        self.config.risk.hard_drawdown_resume_pct,
                    )
            elif self._hard_halt_active and dd <= self.config.risk.hard_drawdown_resume_pct:
                self._hard_halt_active = False
                logger.warning(
                    "HARD DRAWDOWN HALT RELEASED: drawdown recovered to %.2f%% (<= %.2f%%). "
                    "Trading can resume.",
                    dd, self.config.risk.hard_drawdown_resume_pct,
                )

        # Check rolling drawdown brake
        self._check_drawdown_brake()

    def _check_drawdown_brake(self):
        """
        Reduce risk by half after rolling N-trade drawdown exceeds threshold.
        Reset when drawdown recovers.
        """
        if len(self._recent_trades) < self.config.risk.rolling_trade_window:
            return

        rolling_r_sum = sum(t.realized_r for t in self._recent_trades)
        if rolling_r_sum < 0:
            rolling_loss_pct = abs(rolling_r_sum) * (self.config.risk.risk_per_trade_pct / 100.0) * 100.0
            if rolling_loss_pct >= self.config.risk.weekly_drawdown_brake_pct:
                if not self._risk_reduced:
                    self._risk_reduced = True
                    logger.warning(
                        "DRAWDOWN BRAKE ENGAGED: Rolling %d-trade loss = %.2f R (%.2f%%)",
                        self.config.risk.rolling_trade_window, rolling_r_sum, rolling_loss_pct,
                    )
            else:
                if self._risk_reduced:
                    self._risk_reduced = False
                    logger.info("Drawdown brake released: rolling loss recovered")
        else:
            if self._risk_reduced:
                self._risk_reduced = False
                logger.info("Drawdown brake released: rolling trades positive")

    # ── Trade Recording ───────────────────────────────────────────

    def record_trade(self, setup: TradeSetup):
        """Record a completed trade and update metrics."""
        self._trade_history.append(setup)
        self._recent_trades.append(setup)

        # Update daily PnL
        now = datetime.utcnow()
        if self._daily_date is None or now.date() != self._daily_date.date():
            self._daily_pnl = 0.0
            self._daily_date = now
        self._daily_pnl += setup.pnl

        # Update aggregate metrics
        self.metrics.total_trades += 1
        self.metrics.total_r += setup.realized_r
        self.metrics.daily_pnl = self._daily_pnl

        if setup.result == TradeResult.WIN:
            self.metrics.wins += 1
        elif setup.result == TradeResult.LOSS:
            self.metrics.losses += 1
        elif setup.result == TradeResult.BREAKEVEN:
            self.metrics.breakevens += 1
        elif setup.result == TradeResult.TIME_STOP:
            self.metrics.time_stops += 1

        self._recalculate_metrics()

    def _recalculate_metrics(self):
        """Recalculate derived metrics from trade history."""
        trades = list(self._trade_history)
        if not trades:
            return

        wins = [t for t in trades if t.result == TradeResult.WIN]
        losses = [t for t in trades if t.result == TradeResult.LOSS]

        self.metrics.win_rate = len(wins) / len(trades) * 100.0 if trades else 0.0
        self.metrics.avg_win_r = (
            sum(t.realized_r for t in wins) / len(wins) if wins else 0.0
        )
        self.metrics.avg_loss_r = (
            sum(abs(t.realized_r) for t in losses) / len(losses) if losses else 0.0
        )

        gross_profit = sum(t.realized_r for t in wins)
        gross_loss = sum(abs(t.realized_r) for t in losses)
        self.metrics.profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )
        self.metrics.expectancy_r = (
            sum(t.realized_r for t in trades) / len(trades)
        )

        # Rolling metrics from recent trades
        recent = list(self._recent_trades)
        if recent:
            recent_wins = [t for t in recent if t.result == TradeResult.WIN]
            self.metrics.rolling_win_rate = len(recent_wins) / len(recent) * 100.0
            self.metrics.rolling_expectancy = sum(t.realized_r for t in recent) / len(recent)

    def reset_daily(self):
        """Reset daily counters (call at start of each trading day)."""
        logger.info("Daily PnL reset (previous: $%.2f)", self._daily_pnl)
        self._daily_pnl = 0.0
        self._daily_date = datetime.utcnow()

    # ── Reporting ─────────────────────────────────────────────────

    def get_status_report(self) -> str:
        """Generate a human-readable risk status report."""
        m = self.metrics
        lines = [
            "═══ Risk Manager Status ═══",
            f"Total Trades: {m.total_trades}",
            f"Win Rate: {m.win_rate:.1f}%  (Rolling: {m.rolling_win_rate:.1f}%)",
            f"Avg Win: {m.avg_win_r:.2f}R  |  Avg Loss: {m.avg_loss_r:.2f}R",
            f"Profit Factor: {m.profit_factor:.2f}",
            f"Expectancy: {m.expectancy_r:.3f}R  (Rolling: {m.rolling_expectancy:.3f}R)",
            f"Total R: {m.total_r:.2f}",
            f"Current Drawdown: {m.current_drawdown_pct:.2f}%",
            f"Max Drawdown: {m.max_drawdown_pct:.2f}%",
            f"Daily PnL: ${m.daily_pnl:.2f}",
            f"Risk Reduced: {'YES' if self._risk_reduced else 'NO'}",
            f"Effective Risk/Trade: {self._get_effective_risk_fraction() * 100:.3f}%",
        ]
        return "\n".join(lines)
