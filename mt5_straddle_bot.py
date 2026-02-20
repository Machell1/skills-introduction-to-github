#!/usr/bin/env python3
"""
MT5 XAUUSD M1 Tight-Straddle Pending-Order Scalp Bot
=====================================================
Places a Buy Stop + Sell Stop sandwiching the price in the last 20 s of each
M1 candle.  When one fills, the other is cancelled.  Exits are managed with
break-even logic, a scalp target, a runner/trailing-stop mode, and strict
time-in-trade and emergency-loss guards.

Run in PyCharm with the MT5 terminal already open and logged in.
Credentials are loaded from credentials.json next to this script.
"""

import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit(
        "ERROR: MetaTrader5 package not installed.  "
        "Run:  pip install MetaTrader5"
    )

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  (edit here or override via environment variables)
# ─────────────────────────────────────────────────────────────────────────────
CFG = dict(
    # ── Symbol / timeframe ──────────────────────────────────────────────
    SYMBOL="XAUUSD",

    # ── Volume ──────────────────────────────────────────────────────────
    DEFAULT_VOLUME=0.05,          # lots
    # "strict" = skip trade if margin insufficient; "adaptive" = reduce vol
    MARGIN_MODE="adaptive",
    MIN_FREE_MARGIN_BUFFER=2.0,   # USD – keep at least this much free margin

    # ── Entry offsets (in *points*) ─────────────────────────────────────
    ENTRY_OFFSET_POINTS=30,       # distance from ask/bid for pending orders
    SL_DISTANCE_POINTS=100,       # emergency SL distance
    TP_DISTANCE_POINTS=80,        # optional initial TP (0 = no TP)

    # ── Spread / volatility filters ─────────────────────────────────────
    MAX_SPREAD_POINTS=60,         # skip if spread > this
    MAX_CANDLE_RANGE_POINTS=500,  # skip if candle range exceeds this
    WIDEN_ON_VOLATILITY=False,    # True = widen offsets instead of skipping
    VOLATILITY_WIDEN_FACTOR=1.5,  # multiplier for offset when volatile

    # ── Exit management ─────────────────────────────────────────────────
    BE_BUFFER_POINTS=5,           # move SL to entry + this once in profit
    SCALP_TARGET_POINTS=50,       # close immediately when profit >= this
    SCALP_TARGET_USD=0.0,         # alternative: close at USD profit (0=off)
    RUNNER_THRESHOLD_POINTS=100,  # activate trailing stop above this
    TRAIL_DISTANCE_POINTS=40,     # trailing-stop distance
    MAX_HOLD_SECONDS=120,         # force-close after this many seconds
    TIME_IN_TRADE_SECONDS=30,     # if profit < threshold after N s, close
    TIME_IN_TRADE_MIN_PROFIT_POINTS=10,  # minimum profit after N seconds
    EMERGENCY_LOSS_USD=1.50,      # close if floating loss exceeds this

    # ── Daily limits ────────────────────────────────────────────────────
    MAX_DAILY_LOSS_USD=5.0,
    MAX_TRADES_PER_DAY=50,

    # ── Timing ──────────────────────────────────────────────────────────
    POLL_FAST_HZ=10,              # polls/sec inside active window
    POLL_SLOW_HZ=2,               # polls/sec outside active window

    # ── Misc ────────────────────────────────────────────────────────────
    MAGIC=20240101,
    DRY_RUN=False,
    CREDENTIALS_FILE="credentials.json",
    LOG_FILE="mt5_straddle_bot.log",
    LOG_MAX_BYTES=5_000_000,
    LOG_BACKUP_COUNT=3,
)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
_log_fmt = "%(asctime)s [%(levelname)s] %(message)s"
_log_datefmt = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("straddle_bot")
logger.setLevel(logging.DEBUG)

# Rotating file handler
_fh = RotatingFileHandler(
    CFG["LOG_FILE"],
    maxBytes=CFG["LOG_MAX_BYTES"],
    backupCount=CFG["LOG_BACKUP_COUNT"],
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(_log_fmt, _log_datefmt))
logger.addHandler(_fh)

# Console handler
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter(_log_fmt, _log_datefmt))
logger.addHandler(_ch)

# ─────────────────────────────────────────────────────────────────────────────
# DAILY ACCOUNTING (reset on new UTC day)
# ─────────────────────────────────────────────────────────────────────────────
_daily = {
    "date": None,       # date object for the current trading day
    "pnl": 0.0,         # cumulative realized PnL today
    "trades": 0,        # number of completed trades today
}


def _reset_daily_if_needed():
    """Reset daily counters when the UTC date rolls over."""
    today = datetime.now(timezone.utc).date()
    if _daily["date"] != today:
        if _daily["date"] is not None:
            logger.info(
                "Day rollover – previous day PnL=%.2f  trades=%d",
                _daily["pnl"], _daily["trades"],
            )
        _daily["date"] = today
        _daily["pnl"] = 0.0
        _daily["trades"] = 0


def _daily_limit_hit() -> bool:
    """Return True if any daily limit has been reached."""
    _reset_daily_if_needed()
    if _daily["pnl"] <= -abs(CFG["MAX_DAILY_LOSS_USD"]):
        logger.warning("Daily max loss (%.2f) reached.", CFG["MAX_DAILY_LOSS_USD"])
        return True
    if _daily["trades"] >= CFG["MAX_TRADES_PER_DAY"]:
        logger.warning("Daily max trades (%d) reached.", CFG["MAX_TRADES_PER_DAY"])
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MT5 CONNECTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load_credentials() -> dict:
    cred_path = Path(__file__).with_name(CFG["CREDENTIALS_FILE"])
    if not cred_path.exists():
        sys.exit(
            f"ERROR: {cred_path} not found.  Create it with keys: "
            '"login", "password", "server".'
        )
    with open(cred_path, "r") as f:
        creds = json.load(f)
    for key in ("login", "password", "server"):
        if key not in creds:
            sys.exit(f"ERROR: credentials.json missing key '{key}'.")
    creds["login"] = int(creds["login"])
    return creds


def connect_mt5(creds: dict) -> bool:
    """Initialize MT5 and log in.  Returns True on success."""
    if not mt5.initialize():
        logger.error("mt5.initialize() failed: %s", mt5.last_error())
        return False
    if not mt5.login(creds["login"], password=creds["password"],
                     server=creds["server"]):
        logger.error("mt5.login() failed: %s", mt5.last_error())
        mt5.shutdown()
        return False
    logger.info(
        "Connected – account=%d  server=%s  balance=%.2f",
        creds["login"], creds["server"],
        mt5.account_info().balance,
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SYMBOL UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def ensure_symbol() -> bool:
    """Make sure the symbol is visible in Market Watch."""
    sym = CFG["SYMBOL"]
    info = mt5.symbol_info(sym)
    if info is None:
        logger.error("Symbol %s not found.", sym)
        return False
    if not info.visible:
        if not mt5.symbol_select(sym, True):
            logger.error("Cannot select %s in Market Watch.", sym)
            return False
    return True


def get_symbol_props() -> dict:
    """Return a dict of useful symbol properties, or None on failure."""
    info = mt5.symbol_info(CFG["SYMBOL"])
    if info is None:
        return None
    return {
        "point": info.point,
        "digits": info.digits,
        "stops_level": info.trade_stops_level,   # minimum SL/TP distance in points
        "freeze_level": info.trade_freeze_level,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "filling_mode": info.filling_mode,        # bitmask of supported modes
        "spread": info.spread,                    # current spread in points
        "ask": info.ask,
        "bid": info.bid,
    }


def supported_filling(props: dict) -> int:
    """Pick a filling type the broker supports."""
    fm = props["filling_mode"]
    # Bit 1 = FOK, Bit 2 = IOC.  Some brokers only allow RETURN (0).
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


# ─────────────────────────────────────────────────────────────────────────────
# CANDLE-TIMING LOGIC
# ─────────────────────────────────────────────────────────────────────────────
def get_candle_info():
    """
    Return (bar_time_epoch, server_now_epoch) using MT5 server time.
    bar_time is the open time of the current M1 bar.
    """
    rates = mt5.copy_rates_from_pos(CFG["SYMBOL"], mt5.TIMEFRAME_M1, 0, 2)
    if rates is None or len(rates) < 1:
        return None, None
    bar_time = int(rates[-1]["time"])             # latest bar open, epoch
    server_now = int(mt5.symbol_info_tick(CFG["SYMBOL"]).time)  # server epoch
    return bar_time, server_now


def in_placement_window(bar_time: int, server_now: int) -> bool:
    """
    True when server_now is in [bar_time+40, bar_time+60).
    This is the last 20 seconds of the M1 candle.
    """
    elapsed = server_now - bar_time
    return 40 <= elapsed < 60


# ─────────────────────────────────────────────────────────────────────────────
# VOLUME CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
def compute_volume(props: dict) -> float | None:
    """
    Return the volume to use, respecting margin and config.
    Returns None if no valid volume can be placed.
    """
    vol = CFG["DEFAULT_VOLUME"]
    # Clamp to symbol limits
    vol = max(vol, props["volume_min"])
    vol = min(vol, props["volume_max"])
    # Round to volume_step
    vol = _round_volume(vol, props)

    # Check margin for a Buy Stop (worst-case side)
    margin_needed = mt5.order_calc_margin(
        mt5.ORDER_TYPE_BUY, CFG["SYMBOL"], vol, props["ask"]
    )
    if margin_needed is None:
        logger.warning("order_calc_margin returned None.")
        return None

    acct = mt5.account_info()
    available = acct.margin_free - CFG["MIN_FREE_MARGIN_BUFFER"]
    if available <= 0:
        logger.warning("Free margin (%.2f) below buffer.", acct.margin_free)
        return None

    if margin_needed <= available:
        return vol

    # Insufficient margin for requested volume
    if CFG["MARGIN_MODE"] == "strict":
        logger.warning(
            "Strict mode: margin needed=%.2f > available=%.2f – skipping.",
            margin_needed, available,
        )
        return None

    # Adaptive: scale down
    ratio = available / margin_needed
    reduced = vol * ratio
    reduced = _round_volume(reduced, props)
    if reduced < props["volume_min"]:
        logger.warning("Reduced volume below minimum – skipping.")
        return None
    logger.info("Volume reduced from %.2f to %.2f (margin adaptive).", vol, reduced)
    return reduced


def _round_volume(vol: float, props: dict) -> float:
    """Round volume down to nearest volume_step."""
    step = props["volume_step"]
    return math.floor(vol / step) * step


# ─────────────────────────────────────────────────────────────────────────────
# SPREAD / VOLATILITY FILTERS
# ─────────────────────────────────────────────────────────────────────────────
def spread_ok(props: dict) -> bool:
    if props["spread"] > CFG["MAX_SPREAD_POINTS"]:
        logger.info("Spread %d > max %d – skipping.", props["spread"],
                     CFG["MAX_SPREAD_POINTS"])
        return False
    return True


def volatility_filter(props: dict) -> tuple[bool, int]:
    """
    Check last-candle range.  Returns (ok, adjusted_offset_points).
    If candle range is too large and WIDEN_ON_VOLATILITY is False, ok=False.
    """
    rates = mt5.copy_rates_from_pos(CFG["SYMBOL"], mt5.TIMEFRAME_M1, 0, 2)
    if rates is None or len(rates) < 2:
        return True, CFG["ENTRY_OFFSET_POINTS"]

    prev = rates[-2]  # previous completed candle
    candle_range_pts = round((prev["high"] - prev["low"]) / props["point"])

    offset = CFG["ENTRY_OFFSET_POINTS"]
    if candle_range_pts > CFG["MAX_CANDLE_RANGE_POINTS"]:
        if CFG["WIDEN_ON_VOLATILITY"]:
            offset = int(offset * CFG["VOLATILITY_WIDEN_FACTOR"])
            logger.info(
                "Volatility high (range=%d pts) – widened offset to %d.",
                candle_range_pts, offset,
            )
        else:
            logger.info(
                "Volatility high (range=%d pts) – skipping.", candle_range_pts
            )
            return False, offset
    return True, offset


# ─────────────────────────────────────────────────────────────────────────────
# ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────────────────────
def _clamp_sl_tp(price: float, sl: float, tp: float, order_type: int,
                 props: dict) -> tuple[float, float]:
    """
    Ensure SL and TP respect the broker's minimum stop distance.
    Adjusts outward if too close to price.
    """
    min_dist = props["stops_level"] * props["point"]
    digits = props["digits"]

    if order_type in (mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY):
        # SL must be below price by at least min_dist
        if price - sl < min_dist:
            sl = round(price - min_dist, digits)
        # TP must be above price by at least min_dist
        if tp > 0 and tp - price < min_dist:
            tp = round(price + min_dist, digits)
    else:
        # SL must be above price by at least min_dist
        if sl - price < min_dist:
            sl = round(price + min_dist, digits)
        # TP must be below price by at least min_dist
        if tp > 0 and price - tp < min_dist:
            tp = round(price - min_dist, digits)

    return round(sl, digits), round(tp, digits)


def place_straddle(props: dict, offset_points: int, volume: float):
    """
    Place Buy Stop above ask and Sell Stop below bid.
    Returns list of order tickets placed (0–2 items).
    """
    point = props["point"]
    digits = props["digits"]
    ask = props["ask"]
    bid = props["bid"]
    filling = supported_filling(props)

    offset_price = offset_points * point
    sl_dist = CFG["SL_DISTANCE_POINTS"] * point
    tp_dist = CFG["TP_DISTANCE_POINTS"] * point

    tickets = []

    # ── Buy Stop ────────────────────────────────────────────────────────
    buy_price = round(ask + offset_price, digits)
    buy_sl = round(buy_price - sl_dist, digits)
    buy_tp = round(buy_price + tp_dist, digits) if tp_dist > 0 else 0.0
    buy_sl, buy_tp = _clamp_sl_tp(buy_price, buy_sl, buy_tp,
                                  mt5.ORDER_TYPE_BUY_STOP, props)

    buy_req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": CFG["SYMBOL"],
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY_STOP,
        "price": buy_price,
        "sl": buy_sl,
        "tp": buy_tp,
        "deviation": 20,
        "magic": CFG["MAGIC"],
        "comment": "straddle_buy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    # ── Sell Stop ───────────────────────────────────────────────────────
    sell_price = round(bid - offset_price, digits)
    sell_sl = round(sell_price + sl_dist, digits)
    sell_tp = round(sell_price - tp_dist, digits) if tp_dist > 0 else 0.0
    sell_sl, sell_tp = _clamp_sl_tp(sell_price, sell_sl, sell_tp,
                                    mt5.ORDER_TYPE_SELL_STOP, props)

    sell_req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": CFG["SYMBOL"],
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL_STOP,
        "price": sell_price,
        "sl": sell_sl,
        "tp": sell_tp,
        "deviation": 20,
        "magic": CFG["MAGIC"],
        "comment": "straddle_sell",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    for label, req in [("BUY_STOP", buy_req), ("SELL_STOP", sell_req)]:
        fmt = f"Placing %s: price=%.*f  sl=%.*f  tp=%.*f  vol=%.2f"
        logger.info(
            fmt, label,
            digits, req["price"], digits, req["sl"],
            digits, req["tp"], req["volume"],
        )

        if CFG["DRY_RUN"]:
            logger.info("[DRY_RUN] Would send: %s", req)
            continue

        result = mt5.order_send(req)
        if result is None:
            logger.error("%s order_send returned None: %s", label,
                         mt5.last_error())
            continue
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "%s REJECTED retcode=%d  comment='%s'  request=%s",
                label, result.retcode, result.comment, req,
            )
            continue
        logger.info("%s placed – ticket=%d", label, result.order)
        tickets.append(result.order)

    return tickets


# ─────────────────────────────────────────────────────────────────────────────
# PENDING-ORDER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def get_bot_pending_orders() -> list:
    """Return list of pending orders placed by this bot (by magic number)."""
    orders = mt5.orders_get(symbol=CFG["SYMBOL"])
    if orders is None:
        return []
    return [o for o in orders if o.magic == CFG["MAGIC"]]


def cancel_order(ticket: int) -> bool:
    """Cancel a pending order by ticket."""
    if CFG["DRY_RUN"]:
        logger.info("[DRY_RUN] Would cancel order %d", ticket)
        return True
    req = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
    }
    result = mt5.order_send(req)
    if result is None:
        logger.error("Cancel order %d – order_send None: %s", ticket,
                     mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Cancel order %d failed retcode=%d comment='%s'",
                     ticket, result.retcode, result.comment)
        return False
    logger.info("Cancelled pending order %d", ticket)
    return True


def cancel_all_bot_orders():
    """Cancel every pending order belonging to this bot."""
    for o in get_bot_pending_orders():
        cancel_order(o.ticket)


# ─────────────────────────────────────────────────────────────────────────────
# POSITION MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def get_bot_position():
    """Return the open position for this bot's symbol+magic, or None."""
    positions = mt5.positions_get(symbol=CFG["SYMBOL"])
    if positions is None:
        return None
    for p in positions:
        if p.magic == CFG["MAGIC"]:
            return p
    return None


def close_position(pos) -> bool:
    """Market-close an open position."""
    if CFG["DRY_RUN"]:
        logger.info("[DRY_RUN] Would close position ticket=%d", pos.ticket)
        return True

    # Determine close direction
    close_type = (mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY
                  else mt5.ORDER_TYPE_BUY)
    props = get_symbol_props()
    if props is None:
        logger.error("Cannot get symbol props to close position.")
        return False

    price = props["bid"] if close_type == mt5.ORDER_TYPE_SELL else props["ask"]

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": CFG["SYMBOL"],
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 30,
        "magic": CFG["MAGIC"],
        "comment": "straddle_close",
        "type_filling": supported_filling(props),
    }
    result = mt5.order_send(req)
    if result is None:
        logger.error("Close position order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Close position failed retcode=%d comment='%s'",
                     result.retcode, result.comment)
        return False
    logger.info("Position %d closed at %.2f  PnL=%.2f", pos.ticket,
                price, pos.profit)
    return True


def modify_sl(pos, new_sl: float) -> bool:
    """Move the SL of an open position."""
    if CFG["DRY_RUN"]:
        logger.info("[DRY_RUN] Would modify SL of %d to %.5f",
                     pos.ticket, new_sl)
        return True

    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": CFG["SYMBOL"],
        "position": pos.ticket,
        "sl": new_sl,
        "tp": pos.tp,          # keep existing TP
        "magic": CFG["MAGIC"],
    }
    result = mt5.order_send(req)
    if result is None:
        logger.error("Modify SL order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Modify SL failed retcode=%d comment='%s'",
                     result.retcode, result.comment)
        return False
    logger.debug("SL moved to %.5f for ticket %d", new_sl, pos.ticket)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# EXIT MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
class ExitManager:
    """
    Tracks an open position and applies the exit rules:
      1. Move SL to break-even once in small profit.
      2. Close at scalp target.
      3. Activate trailing stop above runner threshold.
      4. Close if profit stagnant after time-in-trade seconds.
      5. Close if floating loss exceeds emergency limit.
      6. Force-close after max-hold time.

    NOTE: slippage and spread can still produce small realized losses; this
    is the best-effort approximation as described in the spec.
    """

    def __init__(self, pos):
        self.ticket = pos.ticket
        self.entry_price = pos.price_open
        self.direction = pos.type  # POSITION_TYPE_BUY or POSITION_TYPE_SELL
        self.entry_time = time.time()
        self.be_moved = False      # True once SL has been moved to break-even
        self.trailing_active = False
        self.trailing_sl = 0.0

        # Log entry details
        props = get_symbol_props()
        spread = props["spread"] if props else "?"
        logger.info(
            "ExitManager started – ticket=%d  entry=%.5f  dir=%s  spread=%s",
            self.ticket, self.entry_price,
            "BUY" if self.direction == mt5.POSITION_TYPE_BUY else "SELL",
            spread,
        )

    def update(self) -> str | None:
        """
        Called on every poll tick while a position is open.
        Returns a reason string if the position was closed, else None.
        """
        pos = get_bot_position()
        if pos is None or pos.ticket != self.ticket:
            # Position disappeared (SL/TP hit by broker)
            return "sl_tp_hit"

        props = get_symbol_props()
        if props is None:
            return None

        point = props["point"]
        profit_usd = pos.profit
        elapsed = time.time() - self.entry_time

        # Current price for the position side
        if self.direction == mt5.POSITION_TYPE_BUY:
            current = props["bid"]
            profit_pts = (current - self.entry_price) / point
        else:
            current = props["ask"]
            profit_pts = (self.entry_price - current) / point

        # ── 5) Emergency loss guard ────────────────────────────────────
        if profit_usd < 0 and abs(profit_usd) >= CFG["EMERGENCY_LOSS_USD"]:
            logger.warning(
                "Emergency loss %.2f >= limit %.2f – closing.",
                profit_usd, CFG["EMERGENCY_LOSS_USD"],
            )
            if close_position(pos):
                _daily["pnl"] += profit_usd
                _daily["trades"] += 1
                return "emergency_loss"

        # ── 6) Max hold time ───────────────────────────────────────────
        if elapsed >= CFG["MAX_HOLD_SECONDS"]:
            logger.info("Max hold time %ds exceeded – closing.", int(elapsed))
            if close_position(pos):
                _daily["pnl"] += profit_usd
                _daily["trades"] += 1
                return "max_hold"

        # ── 1) Break-even SL ──────────────────────────────────────────
        if not self.be_moved and profit_pts > 0:
            be_buffer = CFG["BE_BUFFER_POINTS"] * point
            if self.direction == mt5.POSITION_TYPE_BUY:
                new_sl = round(self.entry_price + be_buffer, props["digits"])
            else:
                new_sl = round(self.entry_price - be_buffer, props["digits"])
            if modify_sl(pos, new_sl):
                self.be_moved = True
                logger.info("SL moved to break-even+buffer: %.5f", new_sl)

        # ── 2) Scalp target ───────────────────────────────────────────
        scalp_hit = False
        if CFG["SCALP_TARGET_POINTS"] > 0 and profit_pts >= CFG["SCALP_TARGET_POINTS"]:
            scalp_hit = True
        if CFG["SCALP_TARGET_USD"] > 0 and profit_usd >= CFG["SCALP_TARGET_USD"]:
            scalp_hit = True

        # Only close at scalp target if we haven't entered runner mode
        if scalp_hit and not self.trailing_active:
            # Check if this qualifies as a runner instead
            if profit_pts >= CFG["RUNNER_THRESHOLD_POINTS"]:
                pass  # fall through to runner logic below
            else:
                logger.info("Scalp target hit (%.1f pts / $%.2f) – closing.",
                            profit_pts, profit_usd)
                if close_position(pos):
                    _daily["pnl"] += profit_usd
                    _daily["trades"] += 1
                    return "scalp_target"

        # ── 3) Runner / trailing stop ─────────────────────────────────
        if profit_pts >= CFG["RUNNER_THRESHOLD_POINTS"]:
            trail = CFG["TRAIL_DISTANCE_POINTS"] * point
            if self.direction == mt5.POSITION_TYPE_BUY:
                ideal_sl = round(current - trail, props["digits"])
                if not self.trailing_active or ideal_sl > self.trailing_sl:
                    self.trailing_sl = ideal_sl
                    self.trailing_active = True
                    modify_sl(pos, self.trailing_sl)
                    logger.debug("Trailing SL (BUY) updated to %.5f",
                                 self.trailing_sl)
            else:
                ideal_sl = round(current + trail, props["digits"])
                if not self.trailing_active or ideal_sl < self.trailing_sl:
                    self.trailing_sl = ideal_sl
                    self.trailing_active = True
                    modify_sl(pos, self.trailing_sl)
                    logger.debug("Trailing SL (SELL) updated to %.5f",
                                 self.trailing_sl)

        # ── 4) Time-in-trade stagnation rule ──────────────────────────
        if (elapsed >= CFG["TIME_IN_TRADE_SECONDS"]
                and profit_pts < CFG["TIME_IN_TRADE_MIN_PROFIT_POINTS"]
                and not self.trailing_active):
            logger.info(
                "Time-in-trade %ds, profit %.1f pts < min %d – closing.",
                int(elapsed), profit_pts, CFG["TIME_IN_TRADE_MIN_PROFIT_POINTS"],
            )
            if close_position(pos):
                _daily["pnl"] += profit_usd
                _daily["trades"] += 1
                return "time_stagnant"

        return None  # position still open


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  MT5 XAUUSD M1 Tight-Straddle Scalp Bot")
    print("=" * 60)
    print()
    print("IMPORTANT: Make sure the MetaTrader 5 terminal is open and")
    print("logged in before running this script.")
    print()
    if CFG["DRY_RUN"]:
        print("*** DRY-RUN MODE – no real orders will be sent ***")
        print()

    # ── Connect ─────────────────────────────────────────────────────────
    creds = load_credentials()
    if not connect_mt5(creds):
        sys.exit("Failed to connect to MT5.")
    if not ensure_symbol():
        mt5.shutdown()
        sys.exit("Symbol setup failed.")

    # Track state across the main loop
    exit_mgr: ExitManager | None = None     # active when a position is open
    last_candle_placed = 0                   # bar_time of last straddle placed
    straddle_tickets: list[int] = []         # pending order tickets we placed

    logger.info("Bot started.  DRY_RUN=%s  MAGIC=%d", CFG["DRY_RUN"], CFG["MAGIC"])

    try:
        while True:
            # ── Timing ──────────────────────────────────────────────────
            bar_time, server_now = get_candle_info()
            if bar_time is None or server_now is None:
                logger.warning("No candle data – connection issue?  Cancelling orders.")
                cancel_all_bot_orders()
                straddle_tickets.clear()
                time.sleep(2)
                continue

            in_window = in_placement_window(bar_time, server_now)

            # ── Daily limits ────────────────────────────────────────────
            _reset_daily_if_needed()

            # ── Position monitoring ─────────────────────────────────────
            pos = get_bot_position()

            if pos is not None:
                # We have an open position – manage exits
                if exit_mgr is None or exit_mgr.ticket != pos.ticket:
                    exit_mgr = ExitManager(pos)
                    # Cancel any remaining pending order from the straddle
                    cancel_all_bot_orders()
                    straddle_tickets.clear()

                reason = exit_mgr.update()
                if reason:
                    logger.info("Position closed – reason=%s", reason)
                    exit_mgr = None
                    # After close, make sure no stale pending orders linger
                    cancel_all_bot_orders()
                    straddle_tickets.clear()

            else:
                # No open position
                exit_mgr = None

                # If we have straddle tickets, check if they are still alive
                if straddle_tickets:
                    live = get_bot_pending_orders()
                    live_tickets = {o.ticket for o in live}

                    # If one filled (became a position), the position branch
                    # above handles it on the next iteration.
                    # If candle changed, cancel leftover pending orders.
                    if bar_time != last_candle_placed:
                        logger.info("Candle changed – cancelling stale pending orders.")
                        cancel_all_bot_orders()
                        straddle_tickets.clear()
                    else:
                        # Keep only tickets still alive
                        straddle_tickets = [
                            t for t in straddle_tickets if t in live_tickets
                        ]

                # ── Place new straddle if in window ─────────────────────
                if (in_window
                        and bar_time != last_candle_placed
                        and not straddle_tickets
                        and not _daily_limit_hit()):

                    props = get_symbol_props()
                    if props is None:
                        logger.warning("Cannot read symbol props – skipping.")
                    elif not spread_ok(props):
                        pass  # logged inside spread_ok
                    else:
                        vol_ok, offset = volatility_filter(props)
                        if not vol_ok:
                            pass  # logged inside
                        else:
                            volume = compute_volume(props)
                            if volume is None:
                                logger.info("Volume check failed – skipping.")
                            else:
                                tickets = place_straddle(props, offset, volume)
                                straddle_tickets = tickets
                                last_candle_placed = bar_time

            # ── Sleep based on activity ─────────────────────────────────
            if pos is not None or in_window:
                time.sleep(1.0 / CFG["POLL_FAST_HZ"])
            else:
                time.sleep(1.0 / CFG["POLL_SLOW_HZ"])

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down.")
    except Exception:
        logger.exception("Unhandled exception – shutting down.")
    finally:
        # Safety: cancel any remaining pending orders before exit
        logger.info("Cleaning up: cancelling all bot pending orders.")
        cancel_all_bot_orders()
        mt5.shutdown()
        logger.info("MT5 shutdown complete.")


if __name__ == "__main__":
    main()
