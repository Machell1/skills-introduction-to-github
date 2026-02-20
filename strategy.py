"""
Momentum-Breakout Strategy (Long + Short)
───────────────────────────────────────────
Optimised for VOLUME WON per trade, not win rate.

Core idea:
  • Enter LONG when price breaks above upper band on high volume.
  • Enter SHORT when price breaks below lower band on high volume.
  • Size positions aggressively — compound winners into bigger positions.
  • Use trailing stops + wide take-profits so winners run big.
  • Accept low win rate; each winner must pay for many losers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Add strategy indicators to the OHLCV dataframe."""
    lookback = int(params["LOOKBACK_PERIOD"])
    atr_period = int(params.get("ATR_PERIOD", 14))

    out = df.copy()

    # Momentum: rate of change over lookback
    out["momentum"] = out["close"].pct_change(lookback)

    # Rolling mean & std of close for breakout detection
    out["rolling_mean"] = out["close"].rolling(lookback).mean()
    out["rolling_std"] = out["close"].rolling(lookback).std()

    threshold = params["BREAKOUT_THRESHOLD"]

    # Upper breakout band (long entries)
    out["upper_band"] = out["rolling_mean"] + threshold * out["rolling_std"]
    # Lower breakout band (short entries)
    out["lower_band"] = out["rolling_mean"] - threshold * out["rolling_std"]

    # Average True Range
    tr = pd.DataFrame(
        {
            "hl": out["high"] - out["low"],
            "hc": (out["high"] - out["close"].shift(1)).abs(),
            "lc": (out["low"] - out["close"].shift(1)).abs(),
        }
    )
    out["atr"] = tr.max(axis=1).rolling(atr_period).mean()

    # Volume average & surge flag
    out["vol_avg"] = out["volume"].rolling(lookback).mean()

    # Detect synthetic indices with flat/meaningless tick volume.
    # If volume coefficient of variation is very low, the volume filter
    # would block ALL entries. Auto-bypass it in that case.
    vol_mean = out["volume"].mean()
    vol_std = out["volume"].std()
    vol_cv = vol_std / vol_mean if vol_mean > 0 else 0.0
    if vol_cv < 0.3:
        # Volume data is near-constant (synthetic index) — bypass filter
        out["vol_surge"] = True
    else:
        out["vol_surge"] = out["volume"] > (params["VOLUME_SURGE_MULT"] * out["vol_avg"])

    # EMA trend filter (fast/slow crossover for directional bias)
    out["ema_fast"] = out["close"].ewm(span=max(5, lookback // 2), adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=lookback * 2, adjust=False).mean()
    out["trend_up"] = out["ema_fast"] > out["ema_slow"]

    return out


def generate_signals(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Return dataframe with a `signal` column:
      +1  = long entry
       0  = no action
      -1  = short entry
    """
    ind = compute_indicators(df, params)

    # Long entry: close breaks above upper band + volume surge + trend up
    long_cond = (ind["close"] > ind["upper_band"]) & ind["vol_surge"] & ind["trend_up"]

    # Short entry: close breaks below lower band + volume surge + trend down
    short_cond = (ind["close"] < ind["lower_band"]) & ind["vol_surge"] & (~ind["trend_up"])

    ind["signal"] = 0
    ind.loc[long_cond, "signal"] = 1
    ind.loc[short_cond, "signal"] = -1

    return ind
