"""
Trade Execution and Management Module.

Handles:
- Placing limit orders from TradeSetup objects
- Monitoring pending orders (fill/expiry)
- Managing active positions (break-even, time stops)
- Closing positions and recording results
- Paper trading mode for safe testing
"""

import logging
from datetime import datetime
from typing import Optional

from .config import BotConfig
from .models import Candle, SetupState, TradeResult, TradeSetup
from .mt5_manager import MT5Manager
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)


class TradeManager:
    """Manages the lifecycle of trades from setup to close."""

    def __init__(self, config: BotConfig, mt5: MT5Manager, risk: RiskManager):
        self.config = config
        self.mt5 = mt5
        self.risk = risk

        # Active tracking
        self.pending_setups: list[TradeSetup] = []  # Waiting for limit fill
        self.active_trades: list[TradeSetup] = []   # Open positions
        self.closed_trades: list[TradeSetup] = []   # Completed trades

        # Paper trading state
        self._paper_mode = config.execution.paper_trading
        self._paper_ticket_counter = 100000

    # ── Order Placement ───────────────────────────────────────────

    def place_order(self, setup: TradeSetup) -> bool:
        """
        Place a limit order for a trade setup.

        Computes lot size dynamically from current equity and stop distance,
        then places the order via MT5 (or simulates in paper mode).
        """
        # Compute position size
        equity = self.mt5.account_equity if not self._paper_mode else self._get_paper_equity()
        lot_size = self.risk.calculate_lot_size(
            equity=equity,
            stop_distance=setup.risk_distance,
            contract_size=self.mt5.symbol_contract_size,
            volume_min=self.mt5.symbol_volume_min,
            volume_max=self.mt5.symbol_volume_max,
            volume_step=self.mt5.symbol_volume_step,
        )

        if lot_size <= 0:
            logger.error(
                "Lot size is zero — cannot place order | equity=%.2f stop_dist=%.4f contract=%.1f",
                equity, setup.risk_distance, self.mt5.symbol_contract_size,
            )
            setup.state = SetupState.CANCELLED
            return False

        setup.lot_size = lot_size

        if self._paper_mode:
            return self._place_paper_order(setup)
        else:
            return self._place_live_order(setup)

    def _place_live_order(self, setup: TradeSetup) -> bool:
        """Place a live limit order via MT5."""
        comment = f"SMC_{setup.template[:3].upper()}_{setup.direction[0].upper()}"

        if setup.direction == "long":
            ticket = self.mt5.place_buy_limit(
                price=setup.entry_price,
                volume=setup.lot_size,
                sl=setup.stop_price,
                tp=setup.target_price,
                comment=comment,
            )
        else:
            ticket = self.mt5.place_sell_limit(
                price=setup.entry_price,
                volume=setup.lot_size,
                sl=setup.stop_price,
                tp=setup.target_price,
                comment=comment,
            )

        if ticket is None:
            logger.error("Failed to place limit order for setup")
            setup.state = SetupState.CANCELLED
            return False

        setup.ticket = ticket
        setup.state = SetupState.ENTRY_PENDING
        self.pending_setups.append(setup)

        logger.info(
            "ORDER PLACED | Ticket: %d | %s %s @ %.2f | SL: %.2f | TP: %.2f | Lots: %.4f",
            ticket, setup.direction.upper(), setup.template.upper(),
            setup.entry_price, setup.stop_price, setup.target_price, setup.lot_size,
        )
        return True

    def _place_paper_order(self, setup: TradeSetup) -> bool:
        """Simulate a limit order in paper mode."""
        # Round prices to symbol precision (default 2 digits for XAUUSD)
        digits = self.mt5.symbol_digits
        setup.entry_price = round(setup.entry_price, digits)
        setup.stop_price = round(setup.stop_price, digits)
        setup.target_price = round(setup.target_price, digits)

        self._paper_ticket_counter += 1
        setup.ticket = self._paper_ticket_counter
        setup.state = SetupState.ENTRY_PENDING
        self.pending_setups.append(setup)

        logger.info(
            "[PAPER] ORDER PLACED | Ticket: %d | %s %s @ %.2f | SL: %.2f | TP: %.2f | Lots: %.4f",
            setup.ticket, setup.direction.upper(), setup.template.upper(),
            setup.entry_price, setup.stop_price, setup.target_price, setup.lot_size,
        )
        return True

    # ── Order Monitoring ──────────────────────────────────────────

    def update(self, candles: list[Candle], current_index: int):
        """
        Main update loop — call on each new candle.
        Checks pending orders for fills/expiry and active trades for exits.
        """
        candle = candles[current_index]

        # Process pending orders
        self._check_pending_orders(candle, current_index)

        # Process active trades
        self._check_active_trades(candle, current_index)

    def _check_pending_orders(self, candle: Candle, current_index: int):
        """Check if pending limit orders have filled or expired."""
        filled = []
        expired = []

        for setup in self.pending_setups:
            # Check expiry
            if current_index >= setup.entry_expiry_index:
                expired.append(setup)
                continue

            if self._paper_mode:
                # Paper mode: check if candle range touched the limit price
                if setup.direction == "long" and candle.low <= setup.entry_price:
                    setup.fill_price = setup.entry_price
                    setup.fill_time = candle.time
                    setup.state = SetupState.ACTIVE
                    filled.append(setup)
                elif setup.direction == "short" and candle.high >= setup.entry_price:
                    setup.fill_price = setup.entry_price
                    setup.fill_time = candle.time
                    setup.state = SetupState.ACTIVE
                    filled.append(setup)
            else:
                # Live mode: check if the pending order still exists
                if not self.mt5.is_order_pending(setup.ticket):
                    # Order is gone — check if it became a position (filled)
                    if self.mt5.is_position_open(setup.ticket):
                        setup.fill_price = setup.entry_price  # Approximate
                        setup.fill_time = candle.time
                        setup.state = SetupState.ACTIVE
                        filled.append(setup)
                    else:
                        # Order was cancelled externally or expired
                        expired.append(setup)

        for setup in filled:
            self.pending_setups.remove(setup)
            self.active_trades.append(setup)
            logger.info(
                "ORDER FILLED | Ticket: %d | %s %s @ %.2f",
                setup.ticket, setup.direction.upper(), setup.template.upper(),
                setup.fill_price,
            )

        for setup in expired:
            self.pending_setups.remove(setup)
            setup.state = SetupState.CANCELLED
            if not self._paper_mode:
                self.mt5.cancel_pending_order(setup.ticket)
            logger.info(
                "ORDER EXPIRED | Ticket: %d | %s %s — not filled within %d candles",
                setup.ticket, setup.direction.upper(), setup.template.upper(),
                self.config.order_block.entry_expiry_candles,
            )

    def _check_active_trades(self, candle: Candle, current_index: int):
        """Check active trades for stop/target/time-stop/break-even."""
        closed = []

        for setup in self.active_trades:
            if self._paper_mode:
                result = self._check_paper_exit(setup, candle, current_index)
            else:
                result = self._check_live_exit(setup, candle, current_index)

            if result:
                closed.append(setup)

        for setup in closed:
            self.active_trades.remove(setup)
            self.closed_trades.append(setup)
            self.risk.record_trade(setup)
            logger.info(
                "TRADE CLOSED | Ticket: %d | %s %s | Result: %s | R: %.2f | PnL: %.2f",
                setup.ticket, setup.direction.upper(), setup.template.upper(),
                setup.result.value if setup.result else "unknown",
                setup.realized_r, setup.pnl,
            )

    def _check_paper_exit(self, setup: TradeSetup, candle: Candle, current_index: int) -> bool:
        """Check exit conditions in paper mode using OHLC candle data."""

        # ── Break-even logic ──────────────────────────────────────
        if self.config.trade_mgmt.breakeven_enabled and not setup.breakeven_moved:
            be_trigger = self.config.trade_mgmt.breakeven_trigger_r
            be_offset = self.config.trade_mgmt.breakeven_offset_r

            if setup.direction == "long":
                unrealized_r = (candle.high - setup.fill_price) / setup.risk_distance
                if unrealized_r >= be_trigger:
                    new_sl = setup.fill_price + be_offset * setup.risk_distance
                    setup.stop_price = new_sl
                    setup.breakeven_moved = True
                    logger.info("[PAPER] Break-even moved for ticket %d: SL → %.2f", setup.ticket, new_sl)
            else:
                unrealized_r = (setup.fill_price - candle.low) / setup.risk_distance
                if unrealized_r >= be_trigger:
                    new_sl = setup.fill_price - be_offset * setup.risk_distance
                    setup.stop_price = new_sl
                    setup.breakeven_moved = True
                    logger.info("[PAPER] Break-even moved for ticket %d: SL → %.2f", setup.ticket, new_sl)

        # ── Time stop ────────────────────────────────────────────
        if current_index >= setup.max_hold_index:
            setup.exit_price = candle.close
            setup.exit_time = candle.time
            setup.result = TradeResult.TIME_STOP
            self._calculate_realized(setup)
            held = current_index - setup.signal_candle_index
            logger.info(
                "[PAPER] TIME STOP | Ticket: %d | Held %d candles | Exit: %.2f | R: %.2f",
                setup.ticket, held, setup.exit_price, setup.realized_r,
            )
            return True

        # ── Stop and target check ────────────────────────────────
        # Conservative assumption: when both stop and target are within
        # the same candle, assume stop fills first.
        if setup.direction == "long":
            stop_hit = candle.low <= setup.stop_price
            target_hit = candle.high >= setup.target_price

            if stop_hit and target_hit:
                # Conservative: stop fills first
                setup.exit_price = setup.stop_price
                setup.exit_time = candle.time
                setup.result = (
                    TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                )
                self._calculate_realized(setup)
                return True
            elif stop_hit:
                setup.exit_price = setup.stop_price
                setup.exit_time = candle.time
                setup.result = (
                    TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                )
                self._calculate_realized(setup)
                return True
            elif target_hit:
                setup.exit_price = setup.target_price
                setup.exit_time = candle.time
                setup.result = TradeResult.WIN
                self._calculate_realized(setup)
                return True

        else:  # short
            stop_hit = candle.high >= setup.stop_price
            target_hit = candle.low <= setup.target_price

            if stop_hit and target_hit:
                setup.exit_price = setup.stop_price
                setup.exit_time = candle.time
                setup.result = (
                    TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                )
                self._calculate_realized(setup)
                return True
            elif stop_hit:
                setup.exit_price = setup.stop_price
                setup.exit_time = candle.time
                setup.result = (
                    TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                )
                self._calculate_realized(setup)
                return True
            elif target_hit:
                setup.exit_price = setup.target_price
                setup.exit_time = candle.time
                setup.result = TradeResult.WIN
                self._calculate_realized(setup)
                return True

        return False

    def _check_live_exit(self, setup: TradeSetup, candle: Candle, current_index: int) -> bool:
        """Check exit conditions for live positions."""

        # Break-even logic (live)
        if self.config.trade_mgmt.breakeven_enabled and not setup.breakeven_moved:
            be_trigger = self.config.trade_mgmt.breakeven_trigger_r
            be_offset = self.config.trade_mgmt.breakeven_offset_r

            bid, ask = self.mt5.get_current_price()
            if setup.direction == "long":
                unrealized_r = (bid - setup.fill_price) / setup.risk_distance if setup.risk_distance > 0 else 0
                if unrealized_r >= be_trigger:
                    new_sl = setup.fill_price + be_offset * setup.risk_distance
                    if self.mt5.modify_position_sl(setup.ticket, new_sl):
                        setup.stop_price = new_sl
                        setup.breakeven_moved = True
                        logger.info("Break-even moved for ticket %d: SL → %.2f", setup.ticket, new_sl)
            else:
                unrealized_r = (setup.fill_price - ask) / setup.risk_distance if setup.risk_distance > 0 else 0
                if unrealized_r >= be_trigger:
                    new_sl = setup.fill_price - be_offset * setup.risk_distance
                    if self.mt5.modify_position_sl(setup.ticket, new_sl):
                        setup.stop_price = new_sl
                        setup.breakeven_moved = True
                        logger.info("Break-even moved for ticket %d: SL → %.2f", setup.ticket, new_sl)

        # Time stop (live)
        if current_index >= setup.max_hold_index:
            logger.info("TIME STOP triggered for ticket %d", setup.ticket)
            if self.mt5.close_position(setup.ticket):
                bid, ask = self.mt5.get_current_price()
                setup.exit_price = bid if setup.direction == "long" else ask
                setup.exit_time = candle.time
                setup.result = TradeResult.TIME_STOP
                self._calculate_realized(setup)
                return True

        # Check if position is still open (stop/TP may have been hit by broker)
        if not self.mt5.is_position_open(setup.ticket):
            # Position was closed by broker (SL or TP hit)
            bid, ask = self.mt5.get_current_price()
            last_price = bid if setup.direction == "long" else ask

            setup.exit_time = candle.time

            # Determine result based on last known price relative to entry
            if setup.direction == "long":
                if last_price >= setup.target_price * 0.999:
                    setup.exit_price = setup.target_price
                    setup.result = TradeResult.WIN
                else:
                    setup.exit_price = setup.stop_price
                    setup.result = (
                        TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                    )
            else:
                if last_price <= setup.target_price * 1.001:
                    setup.exit_price = setup.target_price
                    setup.result = TradeResult.WIN
                else:
                    setup.exit_price = setup.stop_price
                    setup.result = (
                        TradeResult.BREAKEVEN if setup.breakeven_moved else TradeResult.LOSS
                    )

            self._calculate_realized(setup)
            return True

        return False

    def _calculate_realized(self, setup: TradeSetup):
        """Calculate realized R and PnL for a closed trade."""
        if setup.risk_distance <= 0:
            setup.realized_r = 0.0
            setup.pnl = 0.0
            return

        if setup.direction == "long":
            setup.realized_r = (setup.exit_price - setup.fill_price) / setup.risk_distance
            setup.pnl = (setup.exit_price - setup.fill_price) * setup.lot_size * self.mt5.symbol_contract_size
        else:
            setup.realized_r = (setup.fill_price - setup.exit_price) / setup.risk_distance
            setup.pnl = (setup.fill_price - setup.exit_price) * setup.lot_size * self.mt5.symbol_contract_size

        setup.state = SetupState.CLOSED
        logger.info(
            "P&L calculated | Ticket: %d | Entry: %.2f → Exit: %.2f | R: %+.2f | PnL: $%+.2f",
            setup.ticket, setup.fill_price, setup.exit_price, setup.realized_r, setup.pnl,
        )

    def _get_paper_equity(self) -> float:
        """Get simulated equity for paper trading."""
        base_equity = 10000.0  # Default paper equity
        total_pnl = sum(t.pnl for t in self.closed_trades)
        return base_equity + total_pnl

    # ── Cleanup ───────────────────────────────────────────────────

    def cancel_all_pending(self):
        """Cancel all pending orders (emergency or shutdown)."""
        for setup in self.pending_setups:
            if not self._paper_mode:
                self.mt5.cancel_pending_order(setup.ticket)
            setup.state = SetupState.CANCELLED
            logger.info("Cancelled pending order: ticket=%d", setup.ticket)
        self.pending_setups.clear()

    def close_all_positions(self):
        """Close all active positions (emergency or shutdown)."""
        for setup in self.active_trades:
            if not self._paper_mode:
                self.mt5.close_position(setup.ticket)
            setup.state = SetupState.CLOSED
            setup.result = TradeResult.TIME_STOP
            logger.info("Force-closed position: ticket=%d", setup.ticket)
        self.active_trades.clear()

    @property
    def has_open_position(self) -> bool:
        return len(self.active_trades) > 0

    @property
    def has_pending_order(self) -> bool:
        return len(self.pending_setups) > 0

    @property
    def total_open_count(self) -> int:
        return len(self.active_trades) + len(self.pending_setups)
