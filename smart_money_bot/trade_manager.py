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
from collections import deque
from datetime import datetime
from typing import Optional

from .config import BotConfig
from .models import Candle, OrderType, SetupState, TradeResult, TradeSetup
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
        self.closed_trades: deque[TradeSetup] = deque(maxlen=1000)  # Completed trades (capped)

        # Paper trading state
        self._paper_mode = config.execution.paper_trading
        self._paper_ticket_counter = 100000
        self._last_candle: Optional[Candle] = None

    # ── Order Placement ───────────────────────────────────────────

    def place_order(self, setup: TradeSetup) -> bool:
        """
        Place a limit order for a trade setup.

        Computes lot size dynamically from current equity and stop distance,
        then places the order via MT5 (or simulates in paper mode).
        """
        # Round all prices to symbol precision before computing risk_distance
        digits = self.mt5.symbol_digits
        point = self.mt5.symbol_point
        setup.entry_price = round(setup.entry_price, digits)
        setup.stop_price = round(setup.stop_price, digits)
        setup.target_price = round(setup.target_price, digits)

        # Nudge stop by 1 tick if rounding collapsed or inverted the distance
        if setup.direction == "long":
            if setup.stop_price >= setup.entry_price:
                logger.info(
                    "Rounding collapsed long SL %.5f >= entry %.5f — nudging SL down by 1 tick",
                    setup.stop_price, setup.entry_price,
                )
                setup.stop_price = round(setup.entry_price - point, digits)
            if setup.target_price <= setup.entry_price:
                setup.target_price = round(setup.entry_price + point, digits)
        else:
            if setup.stop_price <= setup.entry_price:
                logger.info(
                    "Rounding collapsed short SL %.5f <= entry %.5f — nudging SL up by 1 tick",
                    setup.stop_price, setup.entry_price,
                )
                setup.stop_price = round(setup.entry_price + point, digits)
            if setup.target_price >= setup.entry_price:
                setup.target_price = round(setup.entry_price - point, digits)

        setup.risk_distance = abs(setup.entry_price - setup.stop_price)

        # SL/TP direction validation (defense-in-depth — should not trigger after nudge)
        if setup.direction == "long":
            if setup.stop_price >= setup.entry_price:
                logger.error("Invalid long setup after nudge: SL %.2f >= entry %.2f", setup.stop_price, setup.entry_price)
                setup.state = SetupState.CANCELLED
                return False
            if setup.target_price <= setup.entry_price:
                logger.error("Invalid long setup after nudge: TP %.2f <= entry %.2f", setup.target_price, setup.entry_price)
                setup.state = SetupState.CANCELLED
                return False
        else:
            if setup.stop_price <= setup.entry_price:
                logger.error("Invalid short setup after nudge: SL %.2f <= entry %.2f", setup.stop_price, setup.entry_price)
                setup.state = SetupState.CANCELLED
                return False
            if setup.target_price >= setup.entry_price:
                logger.error("Invalid short setup after nudge: TP %.2f >= entry %.2f", setup.target_price, setup.entry_price)
                setup.state = SetupState.CANCELLED
                return False

        # Compute position size
        equity = self.mt5.account_equity if not self._paper_mode else self._get_paper_equity(self._last_candle)
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

    @staticmethod
    def _determine_order_type(
        direction: str, entry_price: float, bid: float, ask: float,
        trigger_price: float = 0.0, spread_tolerance: float = 0.5,
        symbol_point: float = 0.01,
    ) -> OrderType:
        """
        Determine the correct MT5 order type based on entry price vs current market.

        Rules:
          Long:  entry < ask → Buy Limit | entry > ask → Buy Stop | entry ≈ ask → Market
          Short: entry > bid → Sell Limit | entry < bid → Sell Stop | entry ≈ bid → Market
          Stop-Limit: when trigger_price is set and conditions are met.
        """
        spread = max(ask - bid, symbol_point)  # Prevent zero-spread edge case
        tolerance = spread * spread_tolerance

        if direction == "long":
            # Stop-limit: trigger above ask, limit below trigger
            if trigger_price > 0 and trigger_price > ask and entry_price < trigger_price:
                return OrderType.BUY_STOP_LIMIT
            if abs(entry_price - ask) <= tolerance:
                return OrderType.BUY_MARKET
            elif entry_price < ask:
                return OrderType.BUY_LIMIT
            else:
                return OrderType.BUY_STOP
        else:
            # Stop-limit: trigger below bid, limit above trigger
            if trigger_price > 0 and trigger_price < bid and entry_price > trigger_price:
                return OrderType.SELL_STOP_LIMIT
            if abs(entry_price - bid) <= tolerance:
                return OrderType.SELL_MARKET
            elif entry_price > bid:
                return OrderType.SELL_LIMIT
            else:
                return OrderType.SELL_STOP

    def _place_live_order(self, setup: TradeSetup) -> bool:
        """Place a live order via MT5, choosing the correct order type based on price rules."""
        comment = f"SMC_{setup.template[:3].upper()}_{setup.direction[0].upper()}"
        bid, ask = self.mt5.get_current_price()

        if bid <= 0 or ask <= 0:
            logger.error("Invalid bid/ask: bid=%.2f ask=%.2f — cannot place order", bid, ask)
            setup.state = SetupState.CANCELLED
            return False

        order_type = self._determine_order_type(
            direction=setup.direction,
            entry_price=setup.entry_price,
            bid=bid,
            ask=ask,
            trigger_price=setup.trigger_price,
            symbol_point=self.mt5.symbol_point,
        )
        setup.order_type = order_type
        ticket = None

        if order_type == OrderType.BUY_LIMIT:
            ticket = self.mt5.place_buy_limit(
                price=setup.entry_price, volume=setup.lot_size,
                sl=setup.stop_price, tp=setup.target_price, comment=comment,
            )
        elif order_type == OrderType.SELL_LIMIT:
            ticket = self.mt5.place_sell_limit(
                price=setup.entry_price, volume=setup.lot_size,
                sl=setup.stop_price, tp=setup.target_price, comment=comment,
            )
        elif order_type == OrderType.BUY_STOP:
            ticket = self.mt5.place_buy_stop(
                price=setup.entry_price, volume=setup.lot_size,
                sl=setup.stop_price, tp=setup.target_price, comment=comment,
            )
        elif order_type == OrderType.SELL_STOP:
            ticket = self.mt5.place_sell_stop(
                price=setup.entry_price, volume=setup.lot_size,
                sl=setup.stop_price, tp=setup.target_price, comment=comment,
            )
        elif order_type == OrderType.BUY_STOP_LIMIT:
            ticket = self.mt5.place_buy_stop_limit(
                trigger_price=setup.trigger_price, limit_price=setup.entry_price,
                volume=setup.lot_size, sl=setup.stop_price, tp=setup.target_price,
                comment=comment,
            )
            if ticket is None:
                # Deriv may not support stop-limit — fall back to buy stop
                logger.warning("Buy stop-limit failed, falling back to Buy Stop order")
                setup.order_type = OrderType.BUY_STOP
                order_type = OrderType.BUY_STOP
                ticket = self.mt5.place_buy_stop(
                    price=setup.entry_price, volume=setup.lot_size,
                    sl=setup.stop_price, tp=setup.target_price, comment=comment,
                )
        elif order_type == OrderType.SELL_STOP_LIMIT:
            ticket = self.mt5.place_sell_stop_limit(
                trigger_price=setup.trigger_price, limit_price=setup.entry_price,
                volume=setup.lot_size, sl=setup.stop_price, tp=setup.target_price,
                comment=comment,
            )
            if ticket is None:
                # Deriv may not support stop-limit — fall back to sell stop
                logger.warning("Sell stop-limit failed, falling back to Sell Stop order")
                setup.order_type = OrderType.SELL_STOP
                order_type = OrderType.SELL_STOP
                ticket = self.mt5.place_sell_stop(
                    price=setup.entry_price, volume=setup.lot_size,
                    sl=setup.stop_price, tp=setup.target_price, comment=comment,
                )
        elif order_type == OrderType.BUY_MARKET:
            logger.info("Buy entry %.2f ≈ ask %.2f — using market order", setup.entry_price, ask)
            ticket = self.mt5.place_buy_market(
                volume=setup.lot_size, sl=setup.stop_price,
                tp=setup.target_price, comment=comment,
            )
        elif order_type == OrderType.SELL_MARKET:
            logger.info("Sell entry %.2f ≈ bid %.2f — using market order", setup.entry_price, bid)
            ticket = self.mt5.place_sell_market(
                volume=setup.lot_size, sl=setup.stop_price,
                tp=setup.target_price, comment=comment,
            )

        if ticket is None:
            logger.error("Failed to place %s order for setup", order_type.value)
            setup.state = SetupState.CANCELLED
            return False

        setup.ticket = ticket
        setup.state = SetupState.ENTRY_PENDING

        # Market orders are immediately active (filled)
        if order_type in (OrderType.BUY_MARKET, OrderType.SELL_MARKET):
            actual_price = self.mt5.get_position_open_price(ticket)
            setup.fill_price = actual_price if actual_price else setup.entry_price
            setup.state = SetupState.ACTIVE
            self.active_trades.append(setup)
        else:
            self.pending_setups.append(setup)

        logger.info(
            "ORDER PLACED | Type: %s | Ticket: %d | %s %s @ %.2f | SL: %.2f | TP: %.2f | Lots: %.4f",
            order_type.value, ticket, setup.direction.upper(), setup.template.upper(),
            setup.entry_price, setup.stop_price, setup.target_price, setup.lot_size,
        )
        return True

    def _place_paper_order(self, setup: TradeSetup) -> bool:
        """Simulate an order in paper mode with correct order type classification."""
        digits = self.mt5.symbol_digits
        setup.entry_price = round(setup.entry_price, digits)
        setup.stop_price = round(setup.stop_price, digits)
        setup.target_price = round(setup.target_price, digits)

        # Determine order type using last known price as proxy for bid/ask
        # In paper mode we approximate: bid ≈ ask ≈ last close
        proxy_price = setup.entry_price  # Fallback
        bid = self.mt5.current_bid
        ask = self.mt5.current_ask
        if bid > 0 and ask > 0:
            order_type = self._determine_order_type(
                direction=setup.direction,
                entry_price=setup.entry_price,
                bid=bid, ask=ask,
                trigger_price=setup.trigger_price,
                symbol_point=self.mt5.symbol_point,
            )
        else:
            # No live prices — default to limit orders
            order_type = OrderType.BUY_LIMIT if setup.direction == "long" else OrderType.SELL_LIMIT

        setup.order_type = order_type

        self._paper_ticket_counter += 1
        setup.ticket = self._paper_ticket_counter

        # Market orders fill immediately in paper mode
        if order_type in (OrderType.BUY_MARKET, OrderType.SELL_MARKET):
            half_spread = self.mt5.symbol_point * self.config.execution.paper_spread_points / 2.0
            if setup.direction == "long":
                setup.fill_price = setup.entry_price + half_spread
            else:
                setup.fill_price = setup.entry_price - half_spread
            setup.state = SetupState.ACTIVE
            self.active_trades.append(setup)
            logger.info(
                "[PAPER] MARKET ORDER FILLED | Ticket: %d | %s %s @ %.2f | Lots: %.4f",
                setup.ticket, setup.direction.upper(), setup.template.upper(),
                setup.fill_price, setup.lot_size,
            )
        else:
            setup.state = SetupState.ENTRY_PENDING
            self.pending_setups.append(setup)
            logger.info(
                "[PAPER] ORDER PLACED | Type: %s | Ticket: %d | %s %s @ %.2f | SL: %.2f | TP: %.2f | Lots: %.4f",
                order_type.value, setup.ticket, setup.direction.upper(), setup.template.upper(),
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
        self._last_candle = candle

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
                # Paper mode: check fill conditions based on order type
                half_spread = self.mt5.symbol_point * self.config.execution.paper_spread_points / 2.0
                order_filled = False

                if setup.order_type == OrderType.BUY_LIMIT:
                    # Buy Limit: fills when price dips to entry (candle.low touches entry)
                    if candle.low <= setup.entry_price:
                        setup.fill_price = setup.entry_price + half_spread
                        order_filled = True

                elif setup.order_type == OrderType.SELL_LIMIT:
                    # Sell Limit: fills when price rises to entry (candle.high touches entry)
                    if candle.high >= setup.entry_price:
                        setup.fill_price = setup.entry_price - half_spread
                        order_filled = True

                elif setup.order_type == OrderType.BUY_STOP:
                    # Buy Stop: fills when price rises THROUGH entry (breakout)
                    if candle.high >= setup.entry_price:
                        # Stop orders get worse fill (slippage through the stop level)
                        setup.fill_price = setup.entry_price + half_spread
                        order_filled = True

                elif setup.order_type == OrderType.SELL_STOP:
                    # Sell Stop: fills when price falls THROUGH entry (breakdown)
                    if candle.low <= setup.entry_price:
                        setup.fill_price = setup.entry_price - half_spread
                        order_filled = True

                elif setup.order_type == OrderType.BUY_STOP_LIMIT:
                    # Two-phase: first trigger must be hit, then limit fill
                    if not setup.stop_limit_triggered:
                        if candle.high >= setup.trigger_price:
                            setup.stop_limit_triggered = True
                            logger.info(
                                "[PAPER] Buy stop-limit TRIGGERED | Ticket: %d | Trigger: %.2f hit, awaiting limit fill at %.2f",
                                setup.ticket, setup.trigger_price, setup.entry_price,
                            )
                    if setup.stop_limit_triggered and candle.low <= setup.entry_price:
                        setup.fill_price = setup.entry_price + half_spread
                        order_filled = True

                elif setup.order_type == OrderType.SELL_STOP_LIMIT:
                    # Two-phase: first trigger must be hit, then limit fill
                    if not setup.stop_limit_triggered:
                        if candle.low <= setup.trigger_price:
                            setup.stop_limit_triggered = True
                            logger.info(
                                "[PAPER] Sell stop-limit TRIGGERED | Ticket: %d | Trigger: %.2f hit, awaiting limit fill at %.2f",
                                setup.ticket, setup.trigger_price, setup.entry_price,
                            )
                    if setup.stop_limit_triggered and candle.high >= setup.entry_price:
                        setup.fill_price = setup.entry_price - half_spread
                        order_filled = True

                else:
                    # Fallback for legacy orders without order_type set
                    if setup.direction == "long" and candle.low <= setup.entry_price:
                        setup.fill_price = setup.entry_price + half_spread
                        order_filled = True
                    elif setup.direction == "short" and candle.high >= setup.entry_price:
                        setup.fill_price = setup.entry_price - half_spread
                        order_filled = True

                if order_filled:
                    setup.fill_time = candle.time
                    setup.state = SetupState.ACTIVE
                    filled.append(setup)
            else:
                # Live mode: check if the pending order still exists
                if not self.mt5.is_order_pending(setup.ticket):
                    # Order is gone — check if it became a position (filled)
                    if self.mt5.is_position_open(setup.ticket):
                        # Get actual fill price from MT5 position
                        actual_price = self.mt5.get_position_open_price(setup.ticket)
                        setup.fill_price = actual_price if actual_price else setup.entry_price
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

        # ── Multi-level partial close schedule ─────────────────────
        if (self.config.trade_mgmt.partial_close_enabled
                and setup.risk_distance > 0):
            if setup.direction == "long":
                unrealized_r_pc = (candle.high - setup.fill_price) / setup.risk_distance
            else:
                unrealized_r_pc = (setup.fill_price - candle.low) / setup.risk_distance

            digits = self.mt5.symbol_digits
            vol_step = self.mt5.symbol_volume_step
            vol_min = self.mt5.symbol_volume_min
            schedule = self.config.trade_mgmt.multi_partial_schedule
            for trigger_r, frac in sorted(schedule, key=lambda x: x[0]):
                level_key = f"{trigger_r:.1f}"
                if level_key in setup.partial_closes:
                    continue  # Already closed at this level
                if unrealized_r_pc >= trigger_r:
                    if not setup.original_lot_size:
                        setup.original_lot_size = setup.lot_size
                    close_lots = round(setup.lot_size * frac / vol_step) * vol_step
                    close_lots = max(vol_min, close_lots)
                    setup.lot_size = max(0.0, setup.lot_size - close_lots)
                    if setup.direction == "long":
                        close_price = setup.fill_price + trigger_r * setup.risk_distance
                    else:
                        close_price = setup.fill_price - trigger_r * setup.risk_distance
                    setup.partial_closes[level_key] = {"price": close_price, "fraction": frac, "lots": close_lots}
                    setup.partial_closed = True
                    setup.partial_close_price = close_price
                    # Move SL up with each partial level (rounded to symbol precision)
                    new_sl = setup.fill_price + (trigger_r * 0.5) * setup.risk_distance if setup.direction == "long" else setup.fill_price - (trigger_r * 0.5) * setup.risk_distance
                    new_sl = round(new_sl, digits)
                    if setup.direction == "long" and new_sl > setup.stop_price:
                        setup.stop_price = new_sl
                    elif setup.direction == "short" and new_sl < setup.stop_price:
                        setup.stop_price = new_sl
                    setup.breakeven_moved = True
                    logger.info(
                        "[PAPER] PARTIAL CLOSE L%s | Ticket: %d | Closed %.0f%% (%.4f lots) at %.1fR (%.2f) | Remainder: %.4f lots | SL → %.2f",
                        level_key, setup.ticket, frac * 100, close_lots, trigger_r,
                        close_price, setup.lot_size, setup.stop_price,
                    )
                    break  # Only one partial close level per candle

        # ── Trailing stop logic (progressive R levels) ─────────────
        if self.config.trade_mgmt.breakeven_enabled and setup.risk_distance > 0:
            trailing_levels = self.config.trade_mgmt.trailing_stop_levels
            trail_digits = self.mt5.symbol_digits

            if setup.direction == "long":
                unrealized_r = (candle.high - setup.fill_price) / setup.risk_distance
                # Check each trailing level from highest to lowest trigger
                for trigger_r, stop_r in sorted(trailing_levels, key=lambda x: x[0], reverse=True):
                    if unrealized_r >= trigger_r:
                        new_sl = round(setup.fill_price + stop_r * setup.risk_distance, trail_digits)
                        if new_sl > setup.stop_price:
                            setup.stop_price = new_sl
                            setup.breakeven_moved = True
                            logger.info("[PAPER] Trailing stop moved for ticket %d at %.1fR: SL → %.2f", setup.ticket, trigger_r, new_sl)
                        break
            else:
                unrealized_r = (setup.fill_price - candle.low) / setup.risk_distance
                for trigger_r, stop_r in sorted(trailing_levels, key=lambda x: x[0], reverse=True):
                    if unrealized_r >= trigger_r:
                        new_sl = round(setup.fill_price - stop_r * setup.risk_distance, trail_digits)
                        if new_sl < setup.stop_price:
                            setup.stop_price = new_sl
                            setup.breakeven_moved = True
                            logger.info("[PAPER] Trailing stop moved for ticket %d at %.1fR: SL → %.2f", setup.ticket, trigger_r, new_sl)
                        break

        # ── Urgency time stop (cut dead trades early) ───────────
        urgency_candles = self.config.trade_mgmt.urgency_candles
        candles_held = current_index - setup.signal_candle_index
        if urgency_candles > 0 and candles_held >= urgency_candles and setup.risk_distance > 0:
            if setup.direction == "long":
                urgency_r = (candle.close - setup.fill_price) / setup.risk_distance
            else:
                urgency_r = (setup.fill_price - candle.close) / setup.risk_distance
            if urgency_r < 0.5:
                # Cap exit at stop level — never worse than planned risk
                if setup.direction == "long":
                    setup.exit_price = max(candle.close, setup.stop_price)
                else:
                    setup.exit_price = min(candle.close, setup.stop_price)
                setup.exit_time = candle.time
                setup.result = TradeResult.TIME_STOP
                self._calculate_realized(setup)
                logger.info(
                    "[PAPER] URGENCY STOP | Ticket: %d | Held %d candles, only %.2fR profit | Exit: %.2f",
                    setup.ticket, candles_held, urgency_r, setup.exit_price,
                )
                return True

        # ── Time stop ────────────────────────────────────────────
        if current_index >= setup.max_hold_index:
            # Cap exit at stop level — never worse than planned risk
            if setup.direction == "long":
                setup.exit_price = max(candle.close, setup.stop_price)
            else:
                setup.exit_price = min(candle.close, setup.stop_price)
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

        # Multi-level partial close (live)
        if (self.config.trade_mgmt.partial_close_enabled
                and setup.risk_distance > 0):
            bid, ask = self.mt5.get_current_price()
            if setup.direction == "long":
                unrealized_r_pc = (bid - setup.fill_price) / setup.risk_distance
            else:
                unrealized_r_pc = (setup.fill_price - ask) / setup.risk_distance

            schedule = self.config.trade_mgmt.multi_partial_schedule
            for trigger_r, frac in sorted(schedule, key=lambda x: x[0]):
                level_key = f"{trigger_r:.1f}"
                if level_key in setup.partial_closes:
                    continue
                if unrealized_r_pc >= trigger_r:
                    if self.mt5.partial_close_position(setup.ticket, frac):
                        if not setup.original_lot_size:
                            setup.original_lot_size = setup.lot_size
                        close_lots = setup.lot_size * frac
                        setup.lot_size = max(0.0, setup.lot_size - close_lots)
                        # Use actual bid/ask as close price, not theoretical R-level
                        close_price = bid if setup.direction == "long" else ask
                        setup.partial_closes[level_key] = {"price": close_price, "fraction": frac, "lots": close_lots}
                        setup.partial_closed = True
                        setup.partial_close_price = close_price
                        # Move SL up proportionally (rounded)
                        new_sl = setup.fill_price + (trigger_r * 0.5) * setup.risk_distance if setup.direction == "long" else setup.fill_price - (trigger_r * 0.5) * setup.risk_distance
                        if setup.direction == "long" and new_sl > setup.stop_price:
                            self.mt5.modify_position_sl(setup.ticket, new_sl)
                            setup.stop_price = new_sl
                        elif setup.direction == "short" and new_sl < setup.stop_price:
                            self.mt5.modify_position_sl(setup.ticket, new_sl)
                            setup.stop_price = new_sl
                        setup.breakeven_moved = True
                        # Sync lot_size to actual MT5 position volume to prevent drift
                        actual_vol = self.mt5.get_position_volume(setup.ticket)
                        if actual_vol is not None:
                            setup.lot_size = actual_vol
                        logger.info(
                            "PARTIAL CLOSE L%s | Ticket: %d | Closed %.0f%% at %.1fR | Remainder: %.4f lots | SL → %.2f",
                            level_key, setup.ticket, frac * 100, trigger_r, setup.lot_size, setup.stop_price,
                        )
                        break  # Only one partial close level per candle

        # Trailing stop logic (live)
        if self.config.trade_mgmt.breakeven_enabled and setup.risk_distance > 0:
            trailing_levels = self.config.trade_mgmt.trailing_stop_levels
            bid, ask = self.mt5.get_current_price()

            if setup.direction == "long":
                unrealized_r = (bid - setup.fill_price) / setup.risk_distance
                for trigger_r, stop_r in sorted(trailing_levels, key=lambda x: x[0], reverse=True):
                    if unrealized_r >= trigger_r:
                        new_sl = setup.fill_price + stop_r * setup.risk_distance
                        if new_sl > setup.stop_price:
                            # Cooldown: only attempt SL modify every 5 ticks
                            last_attempt = getattr(setup, '_last_sl_tick', 0)
                            if current_index - last_attempt >= 5 or last_attempt == 0:
                                if self.mt5.modify_position_sl(setup.ticket, new_sl):
                                    setup.stop_price = new_sl
                                    setup.breakeven_moved = True
                                    logger.info("Trailing stop moved for ticket %d at %.1fR: SL → %.2f", setup.ticket, trigger_r, new_sl)
                                setup._last_sl_tick = current_index
                        break
            else:
                unrealized_r = (setup.fill_price - ask) / setup.risk_distance
                for trigger_r, stop_r in sorted(trailing_levels, key=lambda x: x[0], reverse=True):
                    if unrealized_r >= trigger_r:
                        new_sl = setup.fill_price - stop_r * setup.risk_distance
                        if new_sl < setup.stop_price:
                            last_attempt = getattr(setup, '_last_sl_tick', 0)
                            if current_index - last_attempt >= 5 or last_attempt == 0:
                                if self.mt5.modify_position_sl(setup.ticket, new_sl):
                                    setup.stop_price = new_sl
                                    setup.breakeven_moved = True
                                    logger.info("Trailing stop moved for ticket %d at %.1fR: SL → %.2f", setup.ticket, trigger_r, new_sl)
                                setup._last_sl_tick = current_index
                        break

        # Urgency time stop (live) — cut dead trades early
        urgency_candles = self.config.trade_mgmt.urgency_candles
        candles_held = current_index - setup.signal_candle_index
        if urgency_candles > 0 and candles_held >= urgency_candles and setup.risk_distance > 0:
            bid, ask = self.mt5.get_current_price()
            current_price = bid if setup.direction == "long" else ask
            if setup.direction == "long":
                urgency_r = (current_price - setup.fill_price) / setup.risk_distance
            else:
                urgency_r = (setup.fill_price - current_price) / setup.risk_distance
            if urgency_r < 0.5:
                logger.info("URGENCY STOP triggered for ticket %d: %d candles held, only %.2fR", setup.ticket, candles_held, urgency_r)
                if self.mt5.close_position(setup.ticket):
                    setup.exit_price = current_price
                    setup.exit_time = candle.time
                    setup.result = TradeResult.TIME_STOP
                    self._calculate_realized(setup)
                    return True

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
        """Calculate realized R and PnL for a closed trade, accounting for multi-level partial closes."""
        if setup.risk_distance <= 0:
            setup.realized_r = 0.0
            setup.pnl = 0.0
            return

        contract_size = self.mt5.symbol_contract_size

        if setup.partial_closes and setup.original_lot_size > 0:
            # Multi-partial close: sum up PnL from each partial + remainder
            total_pnl = 0.0
            total_weighted_r = 0.0
            total_lots = setup.original_lot_size

            for level_key, info in setup.partial_closes.items():
                trigger_r = float(level_key)
                close_lots = info.get("lots", 0.0)
                close_price = info.get("price", 0.0)
                lot_fraction = close_lots / total_lots if total_lots > 0 else 0.0

                if setup.direction == "long":
                    total_pnl += (close_price - setup.fill_price) * close_lots * contract_size
                else:
                    total_pnl += (setup.fill_price - close_price) * close_lots * contract_size
                total_weighted_r += lot_fraction * trigger_r

            # Remainder PnL
            remaining_lots = setup.lot_size
            remaining_fraction = remaining_lots / total_lots if total_lots > 0 else 0.0
            if setup.direction == "long":
                total_pnl += (setup.exit_price - setup.fill_price) * remaining_lots * contract_size
                remainder_r = (setup.exit_price - setup.fill_price) / setup.risk_distance
            else:
                total_pnl += (setup.fill_price - setup.exit_price) * remaining_lots * contract_size
                remainder_r = (setup.fill_price - setup.exit_price) / setup.risk_distance
            total_weighted_r += remaining_fraction * remainder_r

            setup.pnl = total_pnl
            setup.realized_r = total_weighted_r
        else:
            if setup.direction == "long":
                setup.realized_r = (setup.exit_price - setup.fill_price) / setup.risk_distance
                setup.pnl = (setup.exit_price - setup.fill_price) * setup.lot_size * contract_size
            else:
                setup.realized_r = (setup.fill_price - setup.exit_price) / setup.risk_distance
                setup.pnl = (setup.fill_price - setup.exit_price) * setup.lot_size * contract_size

        setup.state = SetupState.CLOSED
        logger.info(
            "P&L calculated | Ticket: %d | Entry: %.2f → Exit: %.2f | R: %+.2f | PnL: $%+.2f%s",
            setup.ticket, setup.fill_price, setup.exit_price, setup.realized_r, setup.pnl,
            " (partial)" if setup.partial_closed else "",
        )

    def _get_paper_equity(self, current_candle: Optional[Candle] = None) -> float:
        """Get simulated equity for paper trading, including floating PnL."""
        base_equity = 10000.0  # Default paper equity
        closed_pnl = sum(t.pnl for t in self.closed_trades)

        # Include unrealized PnL from active positions
        floating_pnl = 0.0
        if current_candle:
            for t in self.active_trades:
                if t.fill_price and t.lot_size:
                    contract = self.mt5.symbol_contract_size
                    if t.direction == "long":
                        floating_pnl += (current_candle.close - t.fill_price) * t.lot_size * contract
                    else:
                        floating_pnl += (t.fill_price - current_candle.close) * t.lot_size * contract

        return base_equity + closed_pnl + floating_pnl

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

    def reconcile_positions(self):
        """Reconcile internal state with actual MT5 positions (live mode only)."""
        if self._paper_mode:
            return

        orphaned = []
        for setup in self.active_trades:
            if not self.mt5.is_position_open(setup.ticket):
                orphaned.append(setup)
                logger.warning(
                    "RECONCILE: Position ticket %d no longer open in MT5 — removing from tracking",
                    setup.ticket,
                )

        for setup in orphaned:
            self.active_trades.remove(setup)
            setup.state = SetupState.CLOSED
            setup.result = TradeResult.TIME_STOP  # Best-effort classification
            self.closed_trades.append(setup)

    @property
    def has_open_position(self) -> bool:
        return len(self.active_trades) > 0

    @property
    def has_pending_order(self) -> bool:
        return len(self.pending_setups) > 0

    @property
    def total_open_count(self) -> int:
        return len(self.active_trades) + len(self.pending_setups)
