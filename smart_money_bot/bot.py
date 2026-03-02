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
from datetime import datetime, timezone
from typing import Optional

from .config import BotConfig, TemplateType
from .models import Candle, DailyLevels
from .mt5_manager import MT5Manager
from .risk_manager import RiskManager
from .sentiment_engine import SentimentEngine
from .signals import ContinuationSignalGenerator, LowerTFSignalGenerator, ReversalSignalGenerator
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

        # Sentiment engine (optional — disabled by default)
        self.sentiment_engine: Optional[SentimentEngine] = None
        if config.sentiment.enabled:
            self.sentiment_engine = SentimentEngine(config.sentiment)

        # Lower-timeframe entry scanners
        self.ltf_generators: list[LowerTFSignalGenerator] = []
        for tf in config.mt5.entry_timeframes:
            self.ltf_generators.append(LowerTFSignalGenerator(config, self.engine, tf))

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
        logger.info("SMC Trading Bot v1.1.0 Starting")
        logger.info("Symbol: %s | Structure TF: %s | Entry TFs: %s",
                     self.config.mt5.symbol, self.config.mt5.timeframe,
                     self.config.mt5.entry_timeframes)
        logger.info("Templates: %s", [t.value for t in self.config.active_templates])
        logger.info("Paper Mode: %s", self.config.execution.paper_trading)
        if self.sentiment_engine:
            logger.info("Sentiment Engine: ENABLED (mode=%s, %d adapters)",
                         self.config.sentiment.mode, self.sentiment_engine.adapter_count)
        else:
            logger.info("Sentiment Engine: DISABLED")
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

        # Optionally close active positions
        if self.config.execution.close_positions_on_shutdown:
            logger.info("Closing all active positions on shutdown...")
            self.trade_mgr.close_all_positions()

        # Cancel pending orders
        self.trade_mgr.cancel_all_pending()

        # Export trade journal
        self._export_journal()

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
                    logger.error("MT5 connection lost. Attempting reconnect with backoff...")
                    reconnected = False
                    max_attempts = self.config.execution.reconnect_attempts
                    for attempt in range(1, max_attempts + 1):
                        delay = 5 * (3 ** (attempt - 1))  # 5s, 15s, 45s
                        logger.info("Reconnect attempt %d/%d in %ds...", attempt, max_attempts, delay)
                        time.sleep(delay)
                        if self.mt5.connect():
                            logger.info("Reconnected on attempt %d", attempt)
                            reconnected = True
                            break
                    if not reconnected:
                        logger.error("All reconnect attempts failed. Stopping bot.")
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

        # Daily bias (EMA + optional sentiment aggregation)
        ema_bias = None
        if daily_candles and len(daily_candles) >= self.config.bias_filter.ema_period:
            ema_bias = self.engine.get_daily_bias(daily_candles)

        sentiment_bias = None
        if self.sentiment_engine:
            sentiment_bias = self.sentiment_engine.get_bias_string()

        bias = self._combine_bias(ema_bias, sentiment_bias)

        logger.info(
            "Analysis: ATR=%.2f | Swings=%d | PDH=%.2f | PDL=%.2f | EMA_Bias=%s | Sentiment=%s | Bias=%s",
            current_atr, len(swings), daily_levels.pdh, daily_levels.pdl,
            ema_bias or "none", sentiment_bias or "none", bias or "none",
        )

        # ── 3. Update equity and risk ─────────────────────────────
        if self.config.execution.paper_trading:
            equity = self.trade_mgr._get_paper_equity(latest_candle)
        else:
            equity = self.mt5.account_equity
        self.risk.update_equity(equity)

        # Reset daily counters if new day
        now = datetime.now(timezone.utc)
        if self.risk._daily_date and now.date() != self.risk._daily_date.date():
            self.risk.reset_daily()

        # ── 4. Update existing trades ─────────────────────────────
        self.trade_mgr.update(candles, current_index)

        # Periodic position reconciliation (every 8 candles)
        if self._candle_count % 8 == 0 and not self.config.execution.paper_trading:
            self.trade_mgr.reconcile_positions()

        # ── 5. Run risk pre-checks ────────────────────────────────
        # Session/kill zone filter (quality matrix replaces binary on/off)
        current_hour = datetime.now(timezone.utc).hour
        session_quality = 0.0

        if self.config.kill_zone.enabled:
            session_quality = self.config.kill_zone.hourly_quality.get(current_hour, 0.0)
            if session_quality < self.config.kill_zone.min_quality:
                logger.info(
                    "Kill zone: hour %02d quality %.2f < min %.2f — skipping signals",
                    current_hour, session_quality, self.config.kill_zone.min_quality,
                )
                return
        elif self.config.execution.session_filter_enabled:
            # Fallback: legacy binary session filter
            start = self.config.execution.session_start_utc
            end = self.config.execution.session_end_utc
            if start <= end:
                in_session = start <= current_hour < end
            else:
                in_session = current_hour >= start or current_hour < end
            if not in_session:
                logger.info("Outside trading session (%02d:00-%02d:00 UTC) — skipping signals", start, end)
                return
            session_quality = 1.0  # Binary mode: in-session = full quality

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

        # ── 6. Generate signals (H1 templates) ──────────────────────
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

        # ── 6b. Lower-timeframe entry scanning ─────────────────────
        for ltf_gen in self.ltf_generators:
            ltf_candles = self._get_ltf_candles(ltf_gen.timeframe)
            if ltf_candles:
                ltf_setups = ltf_gen.process_candles(
                    ltf_candles=ltf_candles,
                    h1_swings=swings,
                    daily_levels=daily_levels,
                    h1_atr=current_atr,
                    bias=bias,
                    h1_current_index=current_index,
                )
                new_setups.extend(ltf_setups)
                if ltf_setups:
                    logger.info(
                        "[%s] Generated %d new setup(s)", ltf_gen.timeframe, len(ltf_setups),
                    )

        # ── 6c. Intra-batch dedup: one setup per structural zone ──
        # When multiple generators produce setups at the same structural level
        # (same direction, entries within dedup_radius), keep only the best R:R.
        if len(new_setups) > 1:
            dedup_radius = current_atr * self.config.execution.dedup_atr_fraction
            if dedup_radius > 0:
                by_direction: dict[str, list] = {}
                for setup in new_setups:
                    by_direction.setdefault(setup.direction, []).append(setup)

                filtered_setups = []
                for direction, group in by_direction.items():
                    group.sort(key=lambda s: s.entry_price)
                    clusters: list[list] = []
                    for setup in group:
                        if clusters and abs(setup.entry_price - clusters[-1][-1].entry_price) < dedup_radius:
                            clusters[-1].append(setup)
                        else:
                            clusters.append([setup])

                    for cluster in clusters:
                        best = max(cluster, key=lambda s: s.r_multiple)
                        filtered_setups.append(best)
                        for discarded in cluster:
                            if discarded is not best:
                                logger.info(
                                    "Intra-batch dedup: %s %s @ %.2f (R=%.2f) superseded by %s @ %.2f (R=%.2f)",
                                    discarded.template, discarded.direction,
                                    discarded.entry_price, discarded.r_multiple,
                                    best.template, best.entry_price, best.r_multiple,
                                )
                new_setups = filtered_setups

        # ── 7. Deduplicate and place orders for new setups ────────
        for setup in new_setups:
            # Dedup: skip if existing pending/active trade has entry within dedup radius
            dedup_radius = current_atr * self.config.execution.dedup_atr_fraction
            is_dup = False
            for existing in self.trade_mgr.pending_setups + list(self.trade_mgr.active_trades):
                if (existing.direction == setup.direction
                        and abs(existing.entry_price - setup.entry_price) < dedup_radius):
                    is_dup = True
                    logger.info(
                        "Duplicate setup skipped: %s %s @ %.2f (existing @ %.2f within %.1f ATR)",
                        setup.template, setup.direction, setup.entry_price, existing.entry_price,
                        self.config.execution.dedup_atr_fraction,
                    )
                    break
            if is_dup:
                continue

            # Re-check capacity (may have changed with previous order)
            if self.trade_mgr.total_open_count >= self.config.risk.max_positions:
                logger.info(
                    "Max positions reached (%d/%d) — skipping %s %s setup",
                    self.trade_mgr.total_open_count, self.config.risk.max_positions,
                    setup.template, setup.direction,
                )
                break

            # Validate minimum R (higher threshold during low-quality hours)
            min_r = 1.0
            if (self.config.kill_zone.enabled
                    and session_quality < 0.8
                    and session_quality >= self.config.kill_zone.min_quality):
                min_r = self.config.kill_zone.low_quality_min_r
            if setup.r_multiple < min_r:
                logger.info("Setup R too low (%.2f < %.1f) — skipping (quality=%.2f)", setup.r_multiple, min_r, session_quality)
                continue

            success = self.trade_mgr.place_order(setup)
            if success:
                logger.info(
                    "New order placed: %s %s | Entry: %.2f | SL: %.2f | TP: %.2f | R: %.2f | Lots: %.4f",
                    setup.template, setup.direction, setup.entry_price,
                    setup.stop_price, setup.target_price, setup.r_multiple, setup.lot_size,
                )

        # ── 8. Periodic status logging ────────────────────────────
        if self._candle_count % 8 == 0:  # Every ~8 hours (8 × 1H)
            logger.info(self.risk.get_status_report())

    # ── Paper Trading Helpers ─────────────────────────────────────

    def _get_ltf_candles(self, timeframe: str) -> list[Candle]:
        """Fetch lower-timeframe candles (M15 or M30)."""
        if self.config.execution.paper_trading:
            try:
                if self.mt5.is_connected():
                    return self.mt5.get_candles(timeframe=timeframe, count=500)
            except Exception:
                pass
            return []
        else:
            return self.mt5.get_candles(timeframe=timeframe, count=500)

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

    # ── Bias Combination ─────────────────────────────────────────

    def _combine_bias(self, ema_bias: Optional[str], sentiment_bias: Optional[str]) -> Optional[str]:
        """
        Combine EMA bias and sentiment bias according to configured mode.

        Modes:
        - augment: EMA prevails unless sentiment disagrees with high confidence.
        - replace: Sentiment replaces EMA when available.
        - confirm: Both must agree; disagreement → None (no trade).

        If sentiment engine is disabled or unavailable, returns EMA bias unchanged.
        """
        if not self.sentiment_engine or sentiment_bias is None:
            return ema_bias

        mode = self.config.sentiment.mode

        if mode == "replace":
            return sentiment_bias

        if mode == "confirm":
            if ema_bias == sentiment_bias:
                return ema_bias
            if ema_bias is None:
                return sentiment_bias
            if sentiment_bias is None:
                return ema_bias
            # Disagreement → no trade
            logger.info(
                "Bias CONFLICT (confirm mode): EMA=%s vs Sentiment=%s → no bias",
                ema_bias, sentiment_bias,
            )
            return None

        # Default: "augment" mode
        if ema_bias == sentiment_bias:
            return ema_bias  # Agreement — strong signal
        if ema_bias is None:
            return sentiment_bias  # EMA unavailable, use sentiment
        if sentiment_bias is None:
            return ema_bias  # Sentiment unavailable, use EMA

        # Disagreement — check sentiment confidence
        signal = self.sentiment_engine.last_signal
        if signal and signal.confidence >= self.config.sentiment.high_confidence:
            logger.info(
                "Bias override (augment mode): EMA=%s overridden by Sentiment=%s (conf=%.2f >= %.2f)",
                ema_bias, sentiment_bias, signal.confidence, self.config.sentiment.high_confidence,
            )
            return sentiment_bias

        # Low-confidence disagreement — EMA prevails
        logger.info(
            "Bias kept (augment mode): EMA=%s retained over Sentiment=%s (conf=%.2f < %.2f)",
            ema_bias, sentiment_bias,
            signal.confidence if signal else 0, self.config.sentiment.high_confidence,
        )
        return ema_bias

    # ── Journal Export ────────────────────────────────────────────

    def _export_journal(self):
        """Export closed trades to CSV."""
        import csv
        closed = self.trade_mgr.closed_trades
        if not closed:
            return

        path = self.config.execution.trade_journal_path
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ticket", "template", "direction", "order_type",
                    "entry_price", "fill_price", "exit_price", "stop_price", "target_price",
                    "lot_size", "original_lot_size",
                    "r_multiple", "realized_r", "pnl", "result",
                    "partial_closed", "partial_close_price", "breakeven_moved",
                    "signal_time", "fill_time", "exit_time",
                ])
                for t in closed:
                    writer.writerow([
                        t.ticket, t.template, t.direction,
                        t.order_type.value if t.order_type else "",
                        t.entry_price, t.fill_price, t.exit_price, t.stop_price, t.target_price,
                        t.lot_size, t.original_lot_size,
                        f"{t.r_multiple:.2f}", f"{t.realized_r:.2f}", f"{t.pnl:.2f}",
                        t.result.value if t.result else "unknown",
                        t.partial_closed, f"{t.partial_close_price:.2f}", t.breakeven_moved,
                        t.signal_time, t.fill_time, t.exit_time,
                    ])
            logger.info("Trade journal exported to %s (%d trades)", path, len(closed))
        except Exception as e:
            logger.error("Failed to export trade journal: %s", e)

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
