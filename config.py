"""
Trading Bot Configuration
─────────────────────────
All tunable parameters live here. The backtesting calibration loop
adjusts these until the 1000% profit target is met.
"""

# ── Account ──────────────────────────────────────────────────────────
INITIAL_BALANCE = 500.0          # Small account starting capital ($)
PROFIT_TARGET_PCT = 1000.0       # Target: 10x the account (1000%)

# ── Position Sizing ──────────────────────────────────────────────────
# We care about VOLUME WON per trade, not win rate.
# Aggressive sizing maximises dollar gain on winners.
RISK_PER_TRADE_PCT = 5.0         # % of equity risked per trade
MAX_POSITION_SIZE_PCT = 80.0     # Max % of equity in a single trade (aggressive)
MIN_POSITION_SIZE_PCT = 2.0      # Floor so dust trades are skipped

# ── Strategy: Momentum Breakout ──────────────────────────────────────
LOOKBACK_PERIOD = 14             # Bars for momentum calculation
BREAKOUT_THRESHOLD = 1.0         # Std-dev multiplier for entry
VOLUME_SURGE_MULT = 1.3          # Volume must exceed avg by this factor
ATR_PERIOD = 14                  # Average True Range period

# ── Risk / Reward (volume-won focus) ─────────────────────────────────
REWARD_RISK_RATIO = 3.0          # Min R:R — we want big winners
TRAILING_STOP_ATR_MULT = 1.5     # Trail stop at 1.5x ATR (tighter to lock in)
TAKE_PROFIT_ATR_MULT = 5.0       # Let winners run to 5x ATR

# ── Calibration Loop ────────────────────────────────────────────────
MAX_CALIBRATION_ROUNDS = 300     # Safety cap on optimisation passes
PARAM_STEP_SIZES = {
    "LOOKBACK_PERIOD": 2,
    "BREAKOUT_THRESHOLD": 0.1,
    "VOLUME_SURGE_MULT": 0.1,
    "TRAILING_STOP_ATR_MULT": 0.15,
    "TAKE_PROFIT_ATR_MULT": 0.5,
    "RISK_PER_TRADE_PCT": 0.5,
    "MAX_POSITION_SIZE_PCT": 5.0,
}
PARAM_BOUNDS = {
    "LOOKBACK_PERIOD": (5, 40),
    "BREAKOUT_THRESHOLD": (0.3, 3.0),
    "VOLUME_SURGE_MULT": (1.0, 3.0),
    "TRAILING_STOP_ATR_MULT": (0.3, 4.0),
    "TAKE_PROFIT_ATR_MULT": (2.0, 15.0),
    "RISK_PER_TRADE_PCT": (2.0, 15.0),
    "MAX_POSITION_SIZE_PCT": (30.0, 100.0),
}

# ── Synthetic Data (for self-contained backtesting) ──────────────────
SYNTHETIC_BARS = 8000            # Number of OHLCV bars to generate
SYNTHETIC_VOLATILITY = 0.025     # Daily vol for price generation
SYNTHETIC_DRIFT = 0.0002         # Slight upward drift
