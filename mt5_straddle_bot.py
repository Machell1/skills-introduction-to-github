#!/usr/bin/env python3
"""
==============================================================================
  MT5 XAUUSD M1 TIGHT-STRADDLE SCALP BOT  -  DERIV BROKER
  ONE-CLICK INSTALL  |  BACKTEST  |  LIVE TRADE  |  $0.50 MAX LOSS
==============================================================================

HOW TO RUN  (one click in PyCharm):
  1. Open MetaTrader 5 terminal, log into Deriv.
  2. Open this file in PyCharm -> click green Run button.  Done.

The script auto-installs dependencies, creates credentials on first run,
connects to Deriv, and shows a menu:
  [1] BACKTEST   - simulate on real historical M1 data
  [2] LIVE       - real orders, real money
  [3] DRY RUN    - live prices, zero real orders
  [4] EXIT

HARD RULE: max loss per trade = $0.50.  No exceptions.
"""

# =====================================================================
# STEP 0  -  AUTO INSTALL DEPENDENCIES (one-click, no manual pip)
# =====================================================================
import subprocess, sys, importlib

_NEED = ["MetaTrader5", "numpy", "pandas"]

def _auto_install():
    miss = []
    for p in _NEED:
        try:
            importlib.import_module(p)
        except ImportError:
            miss.append(p)
    if miss:
        print(f"[SETUP] Installing: {', '.join(miss)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + miss
        )
        print("[SETUP] Done.")

_auto_install()

# =====================================================================
# IMPORTS
# =====================================================================
import json, logging, math, os, time
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dataclasses import dataclass

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

# =====================================================================
# CONFIG  -  all tunables, Deriv-optimised, $0.50 max loss
# =====================================================================
CFG = {
    "SYMBOL":                "XAUUSD",
    # Deriv servers (wizard will also let user type custom)
    "DERIV_SERVERS":         ["Deriv-Demo", "Deriv-Server",
                              "Deriv-Server-02", "Deriv-Server-03"],
    # Volume
    "DEFAULT_VOLUME":        0.05,
    "MARGIN_MODE":           "adaptive",   # strict | adaptive
    "MIN_FREE_MARGIN_BUF":   1.00,         # USD reserve

    # Entry
    "ENTRY_OFFSET_PTS":      20,           # tight sandwich
    "SL_DISTANCE_PTS":       50,           # emergency SL on pending
    "TP_DISTANCE_PTS":       0,            # 0 = bot manages exits

    # Filters
    "MAX_SPREAD_PTS":        50,
    "MAX_CANDLE_RANGE_PTS":  400,
    "WIDEN_ON_VOL":          False,
    "VOL_WIDEN_FACTOR":      1.5,

    # === EXIT RULES (core of the $0.50 max-loss logic) ===
    "EMERGENCY_LOSS_USD":    0.50,         # HARD CAP per trade
    "BE_BUFFER_PTS":         2,            # SL = entry +/- 2 pts once green
    "SCALP_TARGET_PTS":      30,           # take profit in points
    "SCALP_TARGET_USD":      0.30,         # OR take profit in USD
    "RUNNER_THRESHOLD_PTS":  80,           # activate trail above this
    "TRAIL_DISTANCE_PTS":    25,           # trailing SL distance
    "MAX_HOLD_SEC":          90,           # force close
    "TIME_RULE_SEC":         15,           # stagnant check delay
    "TIME_RULE_MIN_PTS":     5,            # min profit after delay
    "STAGNANT_SEC":          8,            # close if still negative

    # Daily caps
    "MAX_DAILY_LOSS_USD":    3.00,
    "MAX_TRADES_DAY":        60,

    # Polling
    "POLL_FAST_HZ":          10,
    "POLL_SLOW_HZ":          2,

    # Misc
    "MAGIC":                 889900,
    "CRED_FILE":             "credentials.json",
    "LOG_FILE":              "mt5_straddle_bot.log",
    "LOG_BYTES":             5_000_000,
    "LOG_BACKUPS":           3,

    # Backtest
    "BT_DAYS":               30,
    "BT_SPREAD_PTS":         30,
}

# =====================================================================
# LOGGING
# =====================================================================
_FMT = "%(asctime)s [%(levelname)s] %(message)s"
_DFMT = "%Y-%m-%d %H:%M:%S"
log = logging.getLogger("bot")
log.setLevel(logging.DEBUG)
_fh = RotatingFileHandler(CFG["LOG_FILE"], maxBytes=CFG["LOG_BYTES"],
                           backupCount=CFG["LOG_BACKUPS"])
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(_FMT, _DFMT))
log.addHandler(_fh)
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter(_FMT, _DFMT))
log.addHandler(_ch)

# =====================================================================
# DAILY ACCOUNTING
# =====================================================================
_day = {"date": None, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}

def _reset_day():
    today = datetime.now(timezone.utc).date()
    if _day["date"] != today:
        if _day["date"]:
            log.info("DAY END pnl=$%.2f trades=%d W=%d L=%d",
                     _day["pnl"], _day["trades"], _day["wins"], _day["losses"])
        _day.update(date=today, pnl=0.0, trades=0, wins=0, losses=0)

def _day_limit() -> bool:
    _reset_day()
    if _day["pnl"] <= -abs(CFG["MAX_DAILY_LOSS_USD"]):
        log.warning("DAILY LOSS CAP $%.2f HIT", CFG["MAX_DAILY_LOSS_USD"])
        return True
    if _day["trades"] >= CFG["MAX_TRADES_DAY"]:
        log.warning("DAILY TRADE CAP %d HIT", CFG["MAX_TRADES_DAY"])
        return True
    return False

def _record(pnl: float):
    _day["pnl"] += pnl
    _day["trades"] += 1
    if pnl >= 0:
        _day["wins"] += 1
    else:
        _day["losses"] += 1

# =====================================================================
# CREDENTIALS  -  auto-wizard on first run
# =====================================================================
def _cred_path() -> Path:
    return Path(__file__).with_name(CFG["CRED_FILE"])

def _wizard():
    print("\n" + "=" * 55)
    print("  FIRST-RUN SETUP  -  Deriv MT5 Credentials")
    print("=" * 55 + "\n")
    login = input("  MT5 account number: ").strip()
    pwd   = input("  MT5 password:       ").strip()
    print("\n  Deriv servers:")
    for i, s in enumerate(CFG["DERIV_SERVERS"], 1):
        print(f"    [{i}] {s}")
    print(f"    [{len(CFG['DERIV_SERVERS'])+1}] Other")
    ch = input("  Pick server: ").strip()
    try:
        idx = int(ch) - 1
        srv = CFG["DERIV_SERVERS"][idx] if 0 <= idx < len(CFG["DERIV_SERVERS"]) \
              else input("  Type server: ").strip()
    except (ValueError, IndexError):
        srv = input("  Type server: ").strip()
    c = {"login": int(login), "password": pwd, "server": srv}
    with open(_cred_path(), "w") as f:
        json.dump(c, f, indent=2)
    print(f"\n  Saved -> {_cred_path()}\n")
    return c

def load_creds() -> dict:
    p = _cred_path()
    if not p.exists():
        return _wizard()
    with open(p) as f:
        c = json.load(f)
    for k in ("login", "password", "server"):
        if k not in c:
            return _wizard()
    c["login"] = int(c["login"])
    return c

# =====================================================================
# MT5 CONNECTION
# =====================================================================
def connect(creds) -> bool:
    if not mt5.initialize():
        log.error("mt5.initialize() FAILED: %s", mt5.last_error())
        print("\n  ERROR: Cannot start MT5. Is the terminal open?\n")
        return False
    if not mt5.login(creds["login"], password=creds["password"],
                     server=creds["server"]):
        log.error("mt5.login() FAILED: %s", mt5.last_error())
        print(f"\n  ERROR: Login failed for {creds['login']} @ {creds['server']}\n")
        mt5.shutdown()
        return False
    a = mt5.account_info()
    log.info("CONNECTED acct=%d srv=%s bal=$%.2f lev=1:%d",
             a.login, creds["server"], a.balance, a.leverage)
    return True

def ensure_sym() -> bool:
    info = mt5.symbol_info(CFG["SYMBOL"])
    if info is None:
        log.error("%s not found", CFG["SYMBOL"]); return False
    if not info.visible:
        if not mt5.symbol_select(CFG["SYMBOL"], True):
            log.error("Cannot select %s", CFG["SYMBOL"]); return False
    return True

# =====================================================================
# SYMBOL PROPERTIES
# =====================================================================
def sym_props() -> dict | None:
    i = mt5.symbol_info(CFG["SYMBOL"])
    if i is None: return None
    return dict(point=i.point, digits=i.digits, stops=i.trade_stops_level,
                freeze=i.trade_freeze_level, vmin=i.volume_min,
                vmax=i.volume_max, vstep=i.volume_step,
                fill=i.filling_mode, spread=i.spread,
                ask=i.ask, bid=i.bid)

def best_fill(p) -> int:
    if p["fill"] & 1: return mt5.ORDER_FILLING_FOK
    if p["fill"] & 2: return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

# =====================================================================
# CANDLE TIMING  -  server time only, never local clock
# =====================================================================
def candle_info():
    r = mt5.copy_rates_from_pos(CFG["SYMBOL"], mt5.TIMEFRAME_M1, 0, 2)
    if r is None or len(r) < 1: return None, None
    tk = mt5.symbol_info_tick(CFG["SYMBOL"])
    if tk is None: return None, None
    return int(r[-1]["time"]), int(tk.time)

def in_window(bar, now) -> bool:
    """Last 20 seconds of M1 candle: [bar+40 .. bar+60)."""
    return 40 <= (now - bar) < 60

# =====================================================================
# VOLUME  -  margin-safe for $15 accounts
# =====================================================================
def _rvol(v, p):
    return round(math.floor(v / p["vstep"]) * p["vstep"], 8)

def calc_vol(p) -> float | None:
    v = max(CFG["DEFAULT_VOLUME"], p["vmin"])
    v = min(v, p["vmax"])
    v = _rvol(v, p)
    mg = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, CFG["SYMBOL"], v, p["ask"])
    if mg is None: return None
    a = mt5.account_info()
    avail = a.margin_free - CFG["MIN_FREE_MARGIN_BUF"]
    if avail <= 0: return None
    if mg <= avail: return v
    if CFG["MARGIN_MODE"] == "strict": return None
    rv = _rvol(v * (avail / mg), p)
    return rv if rv >= p["vmin"] else None

# =====================================================================
# FILTERS
# =====================================================================
def spread_ok(p) -> bool:
    if p["spread"] > CFG["MAX_SPREAD_PTS"]:
        log.info("Spread %d > %d SKIP", p["spread"], CFG["MAX_SPREAD_PTS"])
        return False
    return True

def vol_filter(p):
    r = mt5.copy_rates_from_pos(CFG["SYMBOL"], mt5.TIMEFRAME_M1, 0, 2)
    off = CFG["ENTRY_OFFSET_PTS"]
    if r is None or len(r) < 2: return True, off
    rng = round((r[-2]["high"] - r[-2]["low"]) / p["point"])
    if rng > CFG["MAX_CANDLE_RANGE_PTS"]:
        if CFG["WIDEN_ON_VOL"]:
            off = int(off * CFG["VOL_WIDEN_FACTOR"])
            log.info("Volatile %dpts widen->%d", rng, off)
        else:
            log.info("Volatile %dpts SKIP", rng); return False, off
    return True, off

# =====================================================================
# ORDER PLACEMENT
# =====================================================================
def _clamp(price, sl, tp, otype, p):
    md = p["stops"] * p["point"]; d = p["digits"]
    if otype in (mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY):
        if price - sl < md: sl = round(price - md, d)
        if tp > 0 and tp - price < md: tp = round(price + md, d)
    else:
        if sl - price < md: sl = round(price + md, d)
        if tp > 0 and price - tp < md: tp = round(price - md, d)
    return round(sl, d), round(tp, d)

def place_straddle(p, off_pts, vol, dry=False):
    pt, d = p["point"], p["digits"]
    ask, bid = p["ask"], p["bid"]
    fl = best_fill(p)
    off = off_pts * pt
    sld = CFG["SL_DISTANCE_PTS"] * pt
    tpd = CFG["TP_DISTANCE_PTS"] * pt
    tickets = []

    # Buy Stop
    bp = round(ask + off, d)
    bsl = round(bp - sld, d)
    btp = round(bp + tpd, d) if tpd > 0 else 0.0
    bsl, btp = _clamp(bp, bsl, btp, mt5.ORDER_TYPE_BUY_STOP, p)
    breq = {"action": mt5.TRADE_ACTION_PENDING, "symbol": CFG["SYMBOL"],
            "volume": vol, "type": mt5.ORDER_TYPE_BUY_STOP,
            "price": bp, "sl": bsl, "tp": btp, "deviation": 20,
            "magic": CFG["MAGIC"], "comment": "strd_buy",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": fl}

    # Sell Stop
    sp = round(bid - off, d)
    ssl = round(sp + sld, d)
    stp = round(sp - tpd, d) if tpd > 0 else 0.0
    ssl, stp = _clamp(sp, ssl, stp, mt5.ORDER_TYPE_SELL_STOP, p)
    sreq = {"action": mt5.TRADE_ACTION_PENDING, "symbol": CFG["SYMBOL"],
            "volume": vol, "type": mt5.ORDER_TYPE_SELL_STOP,
            "price": sp, "sl": ssl, "tp": stp, "deviation": 20,
            "magic": CFG["MAGIC"], "comment": "strd_sell",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": fl}

    for lbl, rq in [("BUY_STOP", breq), ("SELL_STOP", sreq)]:
        log.info("PLACE %s px=%.*f sl=%.*f vol=%.2f spd=%d",
                 lbl, d, rq["price"], d, rq["sl"], vol, p["spread"])
        if dry:
            log.info("[DRY] %s skipped", lbl); tickets.append(0); continue
        res = mt5.order_send(rq)
        if res is None:
            log.error("%s send=None %s", lbl, mt5.last_error()); continue
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            log.error("%s REJECT %d '%s'", lbl, res.retcode, res.comment); continue
        log.info("%s OK ticket=%d", lbl, res.order)
        tickets.append(res.order)
    return tickets

# =====================================================================
# ORDER / POSITION HELPERS
# =====================================================================
def bot_orders():
    o = mt5.orders_get(symbol=CFG["SYMBOL"])
    return [x for x in (o or []) if x.magic == CFG["MAGIC"]]

def cancel(ticket, dry=False):
    if dry: return True
    r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
    ok = r and r.retcode == mt5.TRADE_RETCODE_DONE
    if ok: log.info("CANCEL %d", ticket)
    else:  log.error("CANCEL %d FAIL %s", ticket, r)
    return ok

def cancel_all(dry=False):
    for o in bot_orders(): cancel(o.ticket, dry)

def bot_pos():
    ps = mt5.positions_get(symbol=CFG["SYMBOL"])
    if ps is None: return None
    for x in ps:
        if x.magic == CFG["MAGIC"]: return x
    return None

def close_pos(pos, dry=False):
    if dry: log.info("[DRY] close %d", pos.ticket); return True
    p = sym_props()
    if p is None: return False
    is_buy = pos.type == mt5.POSITION_TYPE_BUY
    ct = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    px = p["bid"] if is_buy else p["ask"]
    rq = {"action": mt5.TRADE_ACTION_DEAL, "symbol": CFG["SYMBOL"],
          "volume": pos.volume, "type": ct, "position": pos.ticket,
          "price": px, "deviation": 30, "magic": CFG["MAGIC"],
          "comment": "strd_exit", "type_filling": best_fill(p)}
    r = mt5.order_send(rq)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE:
        log.info("CLOSED %d px=%.2f pnl=$%.2f", pos.ticket, px, pos.profit)
        return True
    log.error("CLOSE %d FAIL %s", pos.ticket, r); return False

def mod_sl(pos, sl, dry=False):
    if dry: return True
    rq = {"action": mt5.TRADE_ACTION_SLTP, "symbol": CFG["SYMBOL"],
          "position": pos.ticket, "sl": sl, "tp": pos.tp, "magic": CFG["MAGIC"]}
    r = mt5.order_send(rq)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE: return True
    log.error("MOD_SL %d FAIL %s", pos.ticket, r); return False

# =====================================================================
# EXIT MANAGER  -  keeps every trade under $0.50 loss
#
# Tick-by-tick priority:
#   1. Emergency $0.50 hard stop
#   2. Negative after 8s -> close (cut fast)
#   3. Any positive tick -> SL to break-even + 2pt
#   4. Scalp target 30pts / $0.30 -> bank it
#   5. Runner 80pts -> trailing stop 25pts
#   6. Stagnant after 15s with <5pts -> close
#   7. Max hold 90s -> force close
# =====================================================================
class ExitMgr:
    def __init__(self, pos):
        self.ticket = pos.ticket
        self.entry = pos.price_open
        self.is_buy = pos.type == mt5.POSITION_TYPE_BUY
        self.t0 = time.time()
        self.be_done = False
        self.trailing = False
        self.trail_sl = 0.0
        p = sym_props()
        log.info("EXIT_MGR tk=%d entry=%.5f %s spd=%s",
                 self.ticket, self.entry,
                 "BUY" if self.is_buy else "SELL",
                 p["spread"] if p else "?")

    def tick(self, dry=False):
        pos = bot_pos()
        if pos is None or pos.ticket != self.ticket:
            return "sl_tp_hit"
        p = sym_props()
        if p is None: return None
        pt, d = p["point"], p["digits"]
        pnl = pos.profit
        age = time.time() - self.t0
        if self.is_buy:
            cur = p["bid"]; ppts = (cur - self.entry) / pt
        else:
            cur = p["ask"]; ppts = (self.entry - cur) / pt

        # 1. EMERGENCY $0.50
        if pnl < 0 and abs(pnl) >= CFG["EMERGENCY_LOSS_USD"]:
            log.warning("EMERGENCY $%.2f >= $%.2f", pnl, CFG["EMERGENCY_LOSS_USD"])
            if close_pos(pos, dry): _record(pnl); return "emergency"

        # 2. NEGATIVE after 8s
        if age >= CFG["STAGNANT_SEC"] and pnl <= 0:
            log.info("NEG %ds $%.2f -> close", int(age), pnl)
            if close_pos(pos, dry): _record(pnl); return "neg_stagnant"

        # 3. BREAK-EVEN
        if not self.be_done and ppts > 0:
            buf = CFG["BE_BUFFER_PTS"] * pt
            nsl = round(self.entry + buf, d) if self.is_buy \
                  else round(self.entry - buf, d)
            if mod_sl(pos, nsl, dry):
                self.be_done = True
                log.info("BE SL->%.5f", nsl)

        # 4. SCALP
        scalp = False
        if CFG["SCALP_TARGET_PTS"] > 0 and ppts >= CFG["SCALP_TARGET_PTS"]:
            scalp = True
        if CFG["SCALP_TARGET_USD"] > 0 and pnl >= CFG["SCALP_TARGET_USD"]:
            scalp = True
        if scalp and not self.trailing:
            if ppts < CFG["RUNNER_THRESHOLD_PTS"]:
                log.info("SCALP %.0fpts $%.2f", ppts, pnl)
                if close_pos(pos, dry): _record(pnl); return "scalp"

        # 5. RUNNER
        if ppts >= CFG["RUNNER_THRESHOLD_PTS"]:
            tr = CFG["TRAIL_DISTANCE_PTS"] * pt
            if self.is_buy:
                ideal = round(cur - tr, d)
                if not self.trailing or ideal > self.trail_sl:
                    self.trail_sl = ideal; self.trailing = True
                    mod_sl(pos, ideal, dry)
            else:
                ideal = round(cur + tr, d)
                if not self.trailing or ideal < self.trail_sl:
                    self.trail_sl = ideal; self.trailing = True
                    mod_sl(pos, ideal, dry)

        # 6. TIME RULE
        if age >= CFG["TIME_RULE_SEC"] and ppts < CFG["TIME_RULE_MIN_PTS"] \
                and not self.trailing:
            log.info("TIME %ds %.0fpts<%d", int(age), ppts, CFG["TIME_RULE_MIN_PTS"])
            if close_pos(pos, dry): _record(pnl); return "time_rule"

        # 7. MAX HOLD
        if age >= CFG["MAX_HOLD_SEC"]:
            log.info("MAX HOLD %ds $%.2f", int(age), pnl)
            if close_pos(pos, dry): _record(pnl); return "max_hold"

        return None

# =====================================================================
#
#   B A C K T E S T E R
#
# =====================================================================
@dataclass
class BTrade:
    idx: int; etime: object; side: str; epx: float; sl: float
    xpx: float = 0.0; xtime: object = None
    ppts: float = 0.0; pusd: float = 0.0; reason: str = ""

def run_backtest():
    print("\n" + "=" * 60)
    print("  BACKTEST  -  XAUUSD M1 Straddle")
    print("=" * 60)
    p = sym_props()
    if p is None: print("  ERROR: no symbol props"); return
    pt, d = p["point"], p["digits"]
    vol = CFG["DEFAULT_VOLUME"]

    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(days=CFG["BT_DAYS"])
    rates = mt5.copy_rates_range(CFG["SYMBOL"], mt5.TIMEFRAME_M1, start, now_utc)
    if rates is None or len(rates) < 100:
        print(f"  ERROR: not enough data ({len(rates) if rates is not None else 0} bars)")
        return
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    print(f"  {len(df)} bars  {df['time'].iloc[0]}  ->  {df['time'].iloc[-1]}")

    sp_price = CFG["BT_SPREAD_PTS"] * pt
    off_price = CFG["ENTRY_OFFSET_PTS"] * pt
    sl_d = CFG["SL_DISTANCE_PTS"] * pt
    usd_pt = vol * 100 * pt  # USD per point for XAUUSD

    trades = []
    i = 1
    scalp_pts = CFG["SCALP_TARGET_PTS"]
    runner_pts = CFG["RUNNER_THRESHOLD_PTS"]
    trail_pts = CFG["TRAIL_DISTANCE_PTS"]
    be_buf = CFG["BE_BUFFER_PTS"]
    eloss = CFG["EMERGENCY_LOSS_USD"]
    stag_bars = max(1, CFG["STAGNANT_SEC"] // 60)
    time_bars = max(1, CFG["TIME_RULE_SEC"] // 60)
    max_bars = max(1, CFG["MAX_HOLD_SEC"] // 60)

    while i < len(df) - max_bars - 2:
        prev = df.iloc[i - 1]
        bar = df.iloc[i]

        # Volatility filter
        if round((prev["high"] - prev["low"]) / pt) > CFG["MAX_CANDLE_RANGE_PTS"]:
            i += 1; continue

        mid = bar["close"]
        ask = mid + sp_price / 2
        bid = mid - sp_price / 2
        buy_px = round(ask + off_price, d)
        sell_px = round(bid - off_price, d)
        buy_sl = round(buy_px - sl_d, d)
        sell_sl = round(sell_px + sl_d, d)

        nxt = df.iloc[i + 1]
        b_trig = nxt["high"] >= buy_px
        s_trig = nxt["low"] <= sell_px

        if b_trig and s_trig:
            triggered = "BUY" if nxt["open"] >= mid else "SELL"
        elif b_trig:
            triggered = "BUY"
        elif s_trig:
            triggered = "SELL"
        else:
            i += 1; continue

        epx = buy_px if triggered == "BUY" else sell_px
        sl_px = buy_sl if triggered == "BUY" else sell_sl

        t = BTrade(idx=i+1, etime=nxt["time"], side=triggered, epx=epx, sl=sl_px)
        be_set = False; trl_active = False; trl_sl = 0.0

        for j in range(i + 1, min(i + 1 + max_bars + 1, len(df))):
            bj = df.iloc[j]; held = j - (i + 1)
            if triggered == "BUY":
                worst = (bj["low"] - epx) / pt
                best = (bj["high"] - epx) / pt
                exit_c = bj["close"] - sp_price / 2
                pc = (exit_c - epx) / pt
            else:
                worst = (epx - bj["high"]) / pt
                best = (epx - bj["low"]) / pt
                exit_c = bj["close"] + sp_price / 2
                pc = (epx - exit_c) / pt

            # Emergency
            if worst * usd_pt <= -eloss:
                t.ppts = -eloss / usd_pt; t.pusd = -eloss
                t.reason = "emergency"; t.xtime = bj["time"]; break

            # SL hit
            if triggered == "BUY" and bj["low"] <= sl_px:
                t.ppts = (sl_px - epx) / pt; t.pusd = t.ppts * usd_pt
                t.reason = "sl_hit"; t.xtime = bj["time"]; break
            if triggered == "SELL" and bj["high"] >= sl_px:
                t.ppts = (epx - sl_px) / pt; t.pusd = t.ppts * usd_pt
                t.reason = "sl_hit"; t.xtime = bj["time"]; break

            # BE
            if not be_set and best > 0:
                if triggered == "BUY": sl_px = epx + be_buf * pt
                else: sl_px = epx - be_buf * pt
                be_set = True

            # Stagnant negative
            if held >= stag_bars and pc <= 0:
                t.ppts = pc; t.pusd = pc * usd_pt
                t.reason = "stagnant"; t.xtime = bj["time"]; break

            # Scalp
            if best >= scalp_pts and best < runner_pts:
                t.ppts = scalp_pts; t.pusd = scalp_pts * usd_pt
                t.reason = "scalp"; t.xtime = bj["time"]; break

            # Runner
            if best >= runner_pts:
                trl_active = True
                if triggered == "BUY":
                    ideal = bj["high"] - trail_pts * pt
                    if ideal > trl_sl: trl_sl = ideal
                    if bj["low"] <= trl_sl:
                        t.ppts = (trl_sl - epx) / pt; t.pusd = t.ppts * usd_pt
                        t.reason = "trail"; t.xtime = bj["time"]; break
                else:
                    ideal = bj["low"] + trail_pts * pt
                    if trl_sl == 0 or ideal < trl_sl: trl_sl = ideal
                    if bj["high"] >= trl_sl:
                        t.ppts = (epx - trl_sl) / pt; t.pusd = t.ppts * usd_pt
                        t.reason = "trail"; t.xtime = bj["time"]; break

            # Time rule
            if held >= time_bars and pc < CFG["TIME_RULE_MIN_PTS"] and not trl_active:
                t.ppts = pc; t.pusd = pc * usd_pt
                t.reason = "time"; t.xtime = bj["time"]; break

            # Max hold
            if held >= max_bars:
                t.ppts = pc; t.pusd = pc * usd_pt
                t.reason = "max_hold"; t.xtime = bj["time"]; break
        else:
            t.ppts = pc; t.pusd = pc * usd_pt
            t.reason = "end_data"; t.xtime = bj["time"]

        # Hard cap loss
        if t.pusd < -eloss: t.pusd = -eloss
        trades.append(t)
        i += max(2, j - i + 1)

    # ── REPORT ──────────────────────────────────────────────────────
    if not trades:
        print("  No trades. Increase BT_DAYS."); return

    tot = len(trades)
    wins = sum(1 for x in trades if x.pusd >= 0)
    losses = tot - wins
    wr = wins / tot * 100
    tpnl = sum(x.pusd for x in trades)
    aw = np.mean([x.pusd for x in trades if x.pusd >= 0]) if wins else 0
    al = np.mean([x.pusd for x in trades if x.pusd < 0]) if losses else 0
    bw = max(x.pusd for x in trades)
    bl = min(x.pusd for x in trades)

    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in trades:
        eq += x.pusd
        if eq > peak: peak = eq
        dd = peak - eq
        if dd > mdd: mdd = dd

    reasons = {}
    for x in trades:
        reasons[x.reason] = reasons.get(x.reason, 0) + 1

    print("\n" + "-" * 55)
    print(f"  RESULTS  ({CFG['BT_DAYS']} days, {len(df)} bars)")
    print("-" * 55)
    print(f"  Total trades:    {tot}")
    print(f"  Wins:            {wins}")
    print(f"  Losses:          {losses}")
    print(f"  WIN RATE:        {wr:.1f}%")
    print(f"  Total PnL:       ${tpnl:.2f}")
    print(f"  Avg win:         ${aw:.3f}")
    print(f"  Avg loss:        ${al:.3f}")
    print(f"  Biggest win:     ${bw:.2f}")
    print(f"  Biggest loss:    ${bl:.2f}  (capped at $0.50)")
    print(f"  Max drawdown:    ${mdd:.2f}")
    print()
    print("  Exit reasons:")
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {r:<16s} {c:>5d}  ({c/tot*100:.1f}%)")

    # Equity curve
    print("\n  EQUITY CURVE:")
    eq = 0.0; step = max(1, tot // 20)
    for idx, x in enumerate(trades):
        eq += x.pusd
        if idx % step == 0 or idx == tot - 1:
            bar = "#" * max(0, min(int(eq * 10), 50))
            print(f"    {idx+1:>5d}  ${eq:>8.2f}  {bar}")
    print("-" * 55)
    print("  Backtest done. Review before going live.\n")

# =====================================================================
#
#   L I V E   T R A D I N G
#
# =====================================================================
def run_live(dry=False):
    tag = "DRY RUN" if dry else "LIVE"
    print(f"\n{'='*60}")
    print(f"  {tag}  -  XAUUSD M1 Straddle on Deriv")
    print(f"{'='*60}")
    print(f"  Max loss/trade: ${CFG['EMERGENCY_LOSS_USD']:.2f}")
    print(f"  Volume: {CFG['DEFAULT_VOLUME']}  Daily cap: ${CFG['MAX_DAILY_LOSS_USD']:.2f}")
    if dry: print("  *** NO REAL ORDERS ***")
    print()

    emgr = None; last_bar = 0; tix = []
    log.info("START mode=%s magic=%d", tag, CFG["MAGIC"])

    try:
        while True:
            bt, now = candle_info()
            if bt is None:
                log.warning("No data - cancel all")
                cancel_all(dry); tix.clear(); time.sleep(2); continue

            iw = in_window(bt, now); _reset_day()
            pos = bot_pos()

            if pos is not None:
                if emgr is None or emgr.ticket != pos.ticket:
                    emgr = ExitMgr(pos); cancel_all(dry); tix.clear()
                reason = emgr.tick(dry)
                if reason:
                    log.info("CLOSED %s daily=$%.2f W=%d L=%d",
                             reason, _day["pnl"], _day["wins"], _day["losses"])
                    emgr = None; cancel_all(dry); tix.clear()
            else:
                emgr = None
                if tix and bt != last_bar:
                    cancel_all(dry); tix.clear()
                if iw and bt != last_bar and not tix and not _day_limit():
                    p = sym_props()
                    if p and spread_ok(p):
                        ok, off = vol_filter(p)
                        if ok:
                            v = calc_vol(p)
                            if v:
                                tix = place_straddle(p, off, v, dry)
                                last_bar = bt

            time.sleep(1.0 / (CFG["POLL_FAST_HZ"] if pos or iw
                              else CFG["POLL_SLOW_HZ"]))

    except KeyboardInterrupt:
        log.info("Ctrl+C")
    except Exception:
        log.exception("FATAL")
    finally:
        cancel_all(dry)
        print(f"\n  Stopped. PnL=${_day['pnl']:.2f} Trades={_day['trades']}"
              f" W={_day['wins']} L={_day['losses']}")
        mt5.shutdown()
        log.info("SHUTDOWN")

# =====================================================================
#
#   M A I N   M E N U
#
# =====================================================================
def main():
    print()
    print("=" * 60)
    print("   XAUUSD M1 TIGHT-STRADDLE SCALP BOT")
    print("   Broker: DERIV  |  Max Loss: $0.50/trade")
    print("=" * 60)
    print()
    print("   Make sure MetaTrader 5 terminal is OPEN and")
    print("   logged into your Deriv account.")
    print()

    creds = load_creds()
    if not connect(creds): sys.exit(1)
    if not ensure_sym(): mt5.shutdown(); sys.exit(1)

    a = mt5.account_info()
    print(f"   Account:  {a.login}")
    print(f"   Server:   {creds['server']}")
    print(f"   Balance:  ${a.balance:.2f}")
    print(f"   Leverage: 1:{a.leverage}")
    print()
    print("   [1] BACKTEST   - simulate on historical data")
    print("   [2] LIVE       - real trading (REAL MONEY)")
    print("   [3] DRY RUN    - live feed, no real orders")
    print("   [4] EXIT")
    print()

    ch = input("   Select (1/2/3/4): ").strip()
    if ch == "1":
        run_backtest()
    elif ch == "2":
        print()
        ok = input("   TYPE 'YES' TO CONFIRM REAL TRADING: ").strip()
        if ok.upper() == "YES":
            run_live(dry=False)
        else:
            print("   Aborted.")
    elif ch == "3":
        run_live(dry=True)
    else:
        print("   Goodbye.")
    mt5.shutdown()


if __name__ == "__main__":
    main()
