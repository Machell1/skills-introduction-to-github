"""
Main Bot Orchestrator.

Coordinates all components:
- MT5 data retrieval
- SMC analysis
- Signal generation (Reversal + Continuation)
- Risk management
- Trade execution
- Monitoring and logging
"""

import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from .config import BotConfig, TemplateType
from .models import Candle, DailyLevels
from .mt5_manager import MT5Manager
from .risk_manager import RiskManager
from .signals import ContinuationSignalGenerator, ReversalSignalGenerator
from .smc_engine import SMCEngine
from .trade_manager import TradeManager

logger = logging.getLogger(__name__)


class SMCBot:
    """
    Smart Money Concepts Trading Bot.

    Main loop:
    1. Fetch latest 4H candles and daily candles
    2. Run SMC analysis (swings, liquidity, ATR)
    3. Determine daily bias
    4. Generate signals from active templates
    5. Apply risk checks
    6. Place/manage orders
    7. Monitor and log
    8. Sleep until next candle
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self._running = False

        # Core components
        self.mt5 = MT5Manager(config)
        self.engine = SMCEngine(config)
        self.risk = RiskManager(config)
        self.trade_mgr = TradeManager(config, self.mt5, self.risk)

        # Signal generators
        self.reversal_gen = ReversalSignalGenerator(config, self.engine)
        self.continuation_gen = ContinuationSignalGenerator(config, self.engine)

        # State tracking
        self._last_candle_time: Optional[datetime] = None
        self._last_daily_levels: Optional[DailyLevels] = None
        self._candle_count = 0

        # Register shutdown handler
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        """Start the bot: connect to MT5 and enter main loop."""
        logger.info("=" * 60)
        logger.info("SMC Trading Bot v1.0.0 Starting")
        logger.info("Symbol: %s | Timeframe: %s", self.config.mt5.symbol, self.config.mt5.timeframe)
        logger.info("Templates: %s", [t.value for t in self.config.active_templates])
        logger.info("Paper Mode: %s", self.config.execution.paper_trading)
        logger.info("=" * 60)

        # Connect to MT5
        if not self.config.execution.paper_trading:
            if not self.mt5.connect():
                logger.error("Failed to connect to MT5. Exiting.")
                sys.exit(1)

            logger.info(
                "Account: %d | Balance: %.2f %s | Leverage: 1:%d",
                self.mt5.account_login,
                self.mt5.account_balance,
                self.mt5.account_currency,
                self.mt5.account_leverage,
            )
            logger.info(
                "Symbol: %s | Contract: %.1f | Point: %s | Digits: %d",
                self.config.mt5.symbol,
                self.mt5.symbol_contract_size,
                self.mt5.symbol_point,
                self.mt5.symbol_digits,
            )

            # Initialize peak equity
            self.risk.update_equity(self.mt5.account_equity)
        else:
            logger.info("Running in PAPER TRADING mode (no MT5 connection required)")
            # Set paper defaults for symbol info
            self.risk.update_equity(10000.0)

        self._running = True
        self._main_loop()

    def stop(self):
        """Gracefully stop the bot."""
        logger.info("Stopping bot...")
        self._running = False

        # Cancel pending orders
        self.trade_mgr.cancel_all_pending()

        # Log final status
        logger.info(self.risk.get_status_report())
        self._log_trade_summary()

        # Disconnect
        if not self.config.execution.paper_trading:
            self.mt5.disconnect()

        logger.info("Bot stopped.")

    def _shutdown_handler(self, signum, frame):
        """Handle Ctrl+C and SIGTERM gracefully."""
        logger.info("Shutdown signal received (signal %d)", signum)
        self.stop()
        sys.exit(0)

    # ── Main Loop ─────────────────────────────────────────────────

    def _main_loop(self):
        """Main processing loop — runs until stopped."""
        logger.info("Entering main loop. Checking for signals every %d seconds.",
                     self.config.execution.check_interval_seconds)

        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.exception("Error in main loop: %s", e)
                # Continue running unless it's a connection error
                if not self.config.execution.paper_trading and not self.mt5.is_connected():
                    logger.error("MT5 connection lost. Attempting reconnect...")
                    if not self.mt5.connect():
                        logger.error("Reconnect failed. Stopping bot.")
                        self.stop()
                        return

            time.sleep(self.config.execution.check_interval_seconds)

    def _tick(self):
        """Single iteration of the main loop."""
        # ── 1. Fetch data ─────────────────────────────────────────
        if self.config.execution.paper_trading:
            candles = self._get_paper_candles()
            daily_candles = self._get_paper_daily_candles()
        else:
            candles = self.mt5.get_candles(timeframe=self.config.mt5.timeframe, count=500)
            daily_candles = self.mt5.get_daily_candles(count=100)

        if not candles or len(candles) < 50:
            logger.warning("Insufficient candle data: %d candles", len(candles) if candles else 0)
            return

        # Check for new candle
        latest_candle = candles[-1]
        if self._last_candle_time and latest_candle.time <= self._last_candle_time:
            # No new candle yet — still manage existing trades
            if self.trade_mgr.has_open_position or self.trade_mgr.has_pending_order:
                self.trade_mgr.update(candles, len(candles) - 1)
            return

        self._last_candle_time = latest_candle.time
        self._candle_count += 1

        logger.info(
            "── New 1H candle #%d | Time: %s | O: %.2f H: %.2f L: %.2f C: %.2f ──",
            self._candle_count, latest_candle.time,
            latest_candle.open, latest_candle.high, latest_candle.low, latest_candle.close,
        )

        # ── 2. Run SMC analysis ───────────────────────────────────
        current_index = len(candles) - 1
        atr_values = self.engine.compute_atr(candles)
        current_atr = atr_values[-1] if atr_values else 0.0
        swings = self.engine.detect_swings(candles)

        # Daily levels
        if self.config.execution.paper_trading:
            daily_levels = self._compute_paper_daily_levels(candles)
        else:
            daily_levels = self.mt5.get_daily_levels()
        self._last_daily_levels = daily_levels

        # Daily bias
        bias = None
        if daily_candles and len(daily_candles) >= self.config.bias_filter.ema_period:
            bias = self.engine.get_daily_bias(daily_candles)

        logger.info(
            "Analysis: ATR=%.2f | Swings=%d | PDH=%.2f | PDL=%.2f | Bias=%s",
            current_atr, len(swings), daily_levels.pdh, daily_levels.pdl, bias or "none",
        )

        # ── 3. Update equity and risk ─────────────────────────────
        if self.config.execution.paper_trading:
            equity = self.trade_mgr._get_paper_equity()
        else:
            equity = self.mt5.account_equity
        self.risk.update_equity(equity)

        # Reset daily counters if new day
        now = datetime.utcnow()
        if self.risk._daily_date and now.date() != self.risk._daily_date.date():
            self.risk.reset_daily()

        # ── 4. Update existing trades ─────────────────────────────
        self.trade_mgr.update(candles, current_index)

        # ── 5. Run risk pre-checks ────────────────────────────────
        open_count = self.trade_mgr.total_open_count
        spread = self.mt5.current_spread_points if not self.config.execution.paper_trading else 0.0
        atr_history = [v for v in atr_values if v > 0]

        can_trade, reason = self.risk.can_open_trade(
            equity=equity,
            current_open_positions=open_count,
            current_spread_points=spread,
            current_atr=current_atr,
            atr_history=atr_history,
        )

        if not can_trade:
            logger.info("Trade blocked: %s", reason)
            return

        # ── 6. Generate signals ───────────────────────────────────
        new_setups = []

        if TemplateType.REVERSAL in self.config.active_templates:
            reversal_setups = self.reversal_gen.process_candle(
                candles, current_index, swings, daily_levels, atr_values, bias,
            )
            new_setups.extend(reversal_setups)

        if TemplateType.CONTINUATION in self.config.active_templates:
            continuation_setups = self.continuation_gen.process_candle(
                candles, current_index, swings, daily_levels, atr_values, bias,
            )
            new_setups.extend(continuation_setups)

        # ── 7. Place orders for new setups ────────────────────────
        for setup in new_setups:
            # Re-check capacity (may have changed with previous order)
            if self.trade_mgr.total_open_count >= self.config.risk.max_positions:
                logger.info("Max positions reached — skipping setup")
                break

            # Validate minimum R
            if setup.r_multiple < 1.0:
                logger.info("Setup R too low (%.2f) — skipping", setup.r_multiple)
                continue

            success = self.trade_mgr.place_order(setup)
            if success:
                logger.info(
                    "New order placed: %s %s | Entry: %.2f | R: %.2f",
                    setup.template, setup.direction, setup.entry_price, setup.r_multiple,
                )

        # ── 8. Periodic status logging ────────────────────────────
        if self._candle_count % 24 == 0:  # Every ~24 hours (24 × 1H)
            logger.info(self.risk.get_status_report())

    # ── Paper Trading Helpers ─────────────────────────────────────

    def _get_paper_candles(self) -> list[Candle]:
        """In paper mode, try to get candles from MT5 if connected, else return empty."""
        try:
            if self.mt5.is_connected():
                return self.mt5.get_candles(timeframe=self.config.mt5.timeframe, count=500)
        except Exception:
            pass
        logger.warning("Paper mode: no candle data available (connect MT5 for live data)")
        return []

    def _get_paper_daily_candles(self) -> list[Candle]:
        """Get daily candles in paper mode."""
        try:
            if self.mt5.is_connected():
                return self.mt5.get_daily_candles(count=100)
        except Exception:
            pass
        return []

    def _compute_paper_daily_levels(self, candles: list[Candle]) -> DailyLevels:
        """Approximate daily levels from 4H candles when no daily data is available."""
        if not candles:
            return DailyLevels()

        # Group 4H candles by date
        by_date = {}
        for c in candles:
            d = c.time.date()
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(c)

        dates = sorted(by_date.keys())
        if len(dates) < 2:
            return DailyLevels()

        prev_date = dates[-2]
        curr_date = dates[-1]

        prev_candles = by_date[prev_date]
        curr_candles = by_date[curr_date]

        return DailyLevels(
            pdh=max(c.high for c in prev_candles),
            pdl=min(c.low for c in prev_candles),
            current_day_high=max(c.high for c in curr_candles),
            current_day_low=min(c.low for c in curr_candles),
            date=datetime.combine(curr_date, datetime.min.time()),
        )

    # ── Reporting ─────────────────────────────────────────────────

    def _log_trade_summary(self):
        """Log a summary of all trades."""
        closed = self.trade_mgr.closed_trades
        if not closed:
            logger.info("No trades were executed during this session.")
            return

        logger.info("═══ Trade Summary ═══")
        logger.info("Total Trades: %d", len(closed))

        for i, t in enumerate(closed, 1):
            logger.info(
                "  %d. %s %s | Entry: %.2f → Exit: %.2f | R: %+.2f | Result: %s",
                i, t.template.upper(), t.direction.upper(),
                t.fill_price, t.exit_price, t.realized_r,
                t.result.value if t.result else "unknown",
            )
