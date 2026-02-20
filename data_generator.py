"""
Synthetic OHLCV Data Generator
───────────────────────────────
Generates realistic-looking market data so the bot can backtest
without external data dependencies.
"""

import numpy as np
import pandas as pd
from config import SYNTHETIC_BARS, SYNTHETIC_VOLATILITY, SYNTHETIC_DRIFT


def generate_ohlcv(
    bars: int = SYNTHETIC_BARS,
    volatility: float = SYNTHETIC_VOLATILITY,
    drift: float = SYNTHETIC_DRIFT,
    seed: int | None = None,
) -> pd.DataFrame:
    """Return a DataFrame with columns: open, high, low, close, volume."""
    rng = np.random.default_rng(seed)

    # Log-normal price walk
    returns = rng.normal(loc=drift, scale=volatility, size=bars)
    close = 100.0 * np.exp(np.cumsum(returns))

    # Build OHLC from close
    intraday_range = rng.uniform(0.002, 0.025, size=bars)
    high = close * (1 + intraday_range * rng.uniform(0.3, 1.0, size=bars))
    low = close * (1 - intraday_range * rng.uniform(0.3, 1.0, size=bars))
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, size=bars)

    # Volume with occasional surges (important for our strategy)
    base_vol = rng.integers(500_000, 3_000_000, size=bars).astype(float)
    surge_mask = rng.random(size=bars) < 0.12  # ~12% of bars get a surge
    base_vol[surge_mask] *= rng.uniform(2.0, 5.0, size=surge_mask.sum())

    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=bars, freq="h")

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": base_vol},
        index=dates,
    )
    return df
