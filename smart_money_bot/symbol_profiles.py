"""
Per-symbol parameter profiles for ICT/SMC strategy tuning.

Each profile contains the parameters that differ from the base config.py
defaults. When a bot starts for a given symbol, the profile is merged
on top of the base config BEFORE settings.json user overrides.

Profiles are tuned for Deriv MT5 spreads and ICT/SMC characteristics:
- Kill zone timing aligned to each pair's primary session(s)
- Displacement thresholds calibrated to each pair's ATR behavior
- Spread limits set to Deriv's typical spreads per pair
- Swing/OB parameters tuned to pair-specific structure clarity
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import BotConfig

logger = logging.getLogger(__name__)

# ── Magic Number Assignments ──────────────────────────────────────
# Each symbol gets a unique magic number to isolate position queries
# when running multiple symbols on the same MT5 account.
SYMBOL_MAGIC_NUMBERS: dict[str, int] = {
    "XAUUSD": 20240101,
    "EURUSD": 20240102,
    "GBPUSD": 20240103,
    "USDJPY": 20240104,
    "GBPJPY": 20240105,
    "EURJPY": 20240106,
}


# ── Per-Symbol Profiles ──────────────────────────────────────────
# Structure mirrors settings.json sections so merge logic is uniform.

SYMBOL_PROFILES: dict[str, dict] = {

    # ── XAUUSD (Gold) ─────────────────────────────────────────────
    # Current production tuning — kept as-is.
    # Explicitly listed so the profile system documents all pairs.
    "XAUUSD": {
        "mt5": {"magic_number": 20240101},
        "displacement": {"body_atr_multiplier": 0.3},
        "order_block": {
            "min_sweep_depth_atr": 0.10,
            "max_mss_candles": 15,
            "entry_expiry_candles": 36,
        },
        "stop": {"atr_buffer_multiplier": 0.25},
        "execution": {"max_spread_points": 50.0, "paper_spread_points": 30.0},
        "kill_zone": {
            "hourly_quality": {
                0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5, 6: 0.5,
                7: 0.5, 8: 0.6, 9: 0.7, 10: 0.8, 11: 0.8, 12: 0.85,
                13: 1.0, 14: 1.0, 15: 1.0, 16: 0.9,   # London/NY overlap
                17: 0.8, 18: 0.75, 19: 0.7, 20: 0.5,
                21: 0.5, 22: 0.5, 23: 0.5,
            },
            "low_quality_min_r": 1.8,
        },
        "trade_mgmt": {"max_hold_candles": 72, "urgency_candles": 24},
        "bias_filter": {"counter_bias_min_r": 2.0},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── EURUSD ────────────────────────────────────────────────────
    # #1 ICT pair — highest liquidity, cleanest OBs, reliable sweeps.
    # Tighter spreads on Deriv (~0.5 pips). Needs larger body for
    # displacement detection (forex bodies proportionally larger vs ATR).
    "EURUSD": {
        "mt5": {"magic_number": 20240102},
        "displacement": {"body_atr_multiplier": 0.5},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 12,
            "entry_expiry_candles": 24,
        },
        "stop": {"atr_buffer_multiplier": 0.40},
        "execution": {
            "max_spread_points": 8.0,
            "paper_spread_points": 5.0,
            "session_start_utc": 7,
            "session_end_utc": 17,
        },
        "kill_zone": {
            "hourly_quality": {
                0: 0.3, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.3, 6: 0.5,
                7: 0.8, 8: 0.9, 9: 1.0, 10: 1.0, 11: 0.9, 12: 0.85,
                13: 1.0, 14: 1.0, 15: 1.0, 16: 0.9,   # London/NY overlap
                17: 0.7, 18: 0.6, 19: 0.5, 20: 0.5,
                21: 0.3, 22: 0.3, 23: 0.3,
            },
            "low_quality_min_r": 2.0,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 2.5},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── GBPUSD ────────────────────────────────────────────────────
    # #2 ICT pair — volatile "Cable", explosive London session moves.
    # Slightly easier displacement detection than EURUSD.
    # Wider spreads on Deriv (~1.0-1.5 pips).
    "GBPUSD": {
        "mt5": {"magic_number": 20240103},
        "displacement": {"body_atr_multiplier": 0.45},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 12,
            "entry_expiry_candles": 24,
        },
        "stop": {"atr_buffer_multiplier": 0.35},
        "execution": {
            "max_spread_points": 12.0,
            "paper_spread_points": 8.0,
            "session_start_utc": 7,
            "session_end_utc": 17,
        },
        "kill_zone": {
            "hourly_quality": {
                0: 0.3, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.3, 6: 0.5,
                7: 0.9, 8: 1.0, 9: 1.0, 10: 0.9, 11: 0.85, 12: 0.8,
                13: 1.0, 14: 1.0, 15: 1.0, 16: 0.9,   # London/NY overlap
                17: 0.7, 18: 0.6, 19: 0.5, 20: 0.5,
                21: 0.3, 22: 0.3, 23: 0.3,
            },
            "low_quality_min_r": 2.0,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 2.5},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── USDJPY ────────────────────────────────────────────────────
    # #3 ICT pair — clean structure, respects daily/weekly levels.
    # Dual session peaks: Tokyo (00-03 UTC) + NY (13-16 UTC).
    # Tight spreads on Deriv (~0.5-1.0 pips).
    "USDJPY": {
        "mt5": {"magic_number": 20240104},
        "displacement": {"body_atr_multiplier": 0.5},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 12,
            "entry_expiry_candles": 24,
        },
        "stop": {"atr_buffer_multiplier": 0.40},
        "execution": {
            "max_spread_points": 8.0,
            "paper_spread_points": 5.0,
            "session_start_utc": 0,
            "session_end_utc": 17,
        },
        "kill_zone": {
            "hourly_quality": {
                0: 0.9, 1: 1.0, 2: 1.0, 3: 0.9,      # Tokyo session
                4: 0.7, 5: 0.5, 6: 0.5,
                7: 0.7, 8: 0.7, 9: 0.6, 10: 0.5, 11: 0.5, 12: 0.6,
                13: 1.0, 14: 1.0, 15: 1.0, 16: 0.9,   # NY session
                17: 0.7, 18: 0.6, 19: 0.5, 20: 0.5,
                21: 0.5, 22: 0.5, 23: 0.7,
            },
            "low_quality_min_r": 2.0,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 2.5},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── GBPJPY ────────────────────────────────────────────────────
    # Cross pair — massive volatility, clear BOS/sweep patterns.
    # Explosive sweeps but needs careful risk control.
    # Wider spreads (~2-3 pips), shorter hold times.
    # swing_length=3 filters noisy pivots from extreme volatility.
    # Risk reduced to 0.25% per trade to compensate for wider swings.
    "GBPJPY": {
        "mt5": {"magic_number": 20240105},
        "displacement": {"body_atr_multiplier": 0.4},
        "order_block": {
            "min_sweep_depth_atr": 0.10,
            "max_mss_candles": 14,
            "entry_expiry_candles": 18,
        },
        "stop": {"atr_buffer_multiplier": 0.30},
        "risk": {"risk_per_trade_pct": 0.25},
        "execution": {
            "max_spread_points": 20.0,
            "paper_spread_points": 15.0,
            "session_start_utc": 0,
            "session_end_utc": 11,
        },
        "kill_zone": {
            "hourly_quality": {
                0: 0.8, 1: 0.9, 2: 1.0, 3: 0.9,      # Tokyo session
                4: 0.6, 5: 0.5, 6: 0.5,
                7: 0.9, 8: 1.0, 9: 1.0, 10: 0.9,      # London open
                11: 0.8, 12: 0.7,
                13: 0.8, 14: 0.8, 15: 0.7, 16: 0.6,
                17: 0.5, 18: 0.5, 19: 0.5, 20: 0.5,
                21: 0.5, 22: 0.5, 23: 0.6,
            },
            "low_quality_min_r": 2.2,
        },
        "trade_mgmt": {"max_hold_candles": 36, "urgency_candles": 12},
        "bias_filter": {"counter_bias_min_r": 2.5},
        "swing": {"swing_length": 3},
        "sentiment": {"enabled": False},
    },

    # ── EURJPY ────────────────────────────────────────────────────
    # Cross pair — Tokyo/London overlap, clear structural moves.
    # Moderate volatility between EURUSD and GBPJPY.
    # Spreads ~1.5-2.0 pips on Deriv.
    "EURJPY": {
        "mt5": {"magic_number": 20240106},
        "displacement": {"body_atr_multiplier": 0.45},
        "order_block": {
            "min_sweep_depth_atr": 0.09,
            "max_mss_candles": 13,
            "entry_expiry_candles": 20,
        },
        "stop": {"atr_buffer_multiplier": 0.35},
        "execution": {
            "max_spread_points": 15.0,
            "paper_spread_points": 10.0,
            "session_start_utc": 0,
            "session_end_utc": 11,
        },
        "kill_zone": {
            "hourly_quality": {
                0: 0.8, 1: 0.9, 2: 1.0, 3: 0.9,      # Tokyo session
                4: 0.6, 5: 0.5, 6: 0.5,
                7: 0.9, 8: 1.0, 9: 1.0, 10: 0.9,      # London open
                11: 0.8, 12: 0.7,
                13: 0.8, 14: 0.8, 15: 0.7, 16: 0.6,
                17: 0.5, 18: 0.5, 19: 0.5, 20: 0.5,
                21: 0.5, 22: 0.5, 23: 0.6,
            },
            "low_quality_min_r": 2.0,
        },
        "trade_mgmt": {"max_hold_candles": 42, "urgency_candles": 14},
        "bias_filter": {"counter_bias_min_r": 2.5},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },
}


# ── Public API ────────────────────────────────────────────────────

def get_profile(symbol: str) -> dict:
    """Return the parameter override profile for *symbol*, or {} if unknown."""
    return SYMBOL_PROFILES.get(symbol, {})


def get_supported_symbols() -> list[str]:
    """Return list of all symbols with defined profiles."""
    return list(SYMBOL_PROFILES.keys())


def apply_profile(config: "BotConfig") -> None:
    """
    Merge per-symbol overrides into an already-constructed *config*.

    Call this AFTER building from defaults but BEFORE applying settings.json
    user overrides, so the priority order is:

        config.py defaults  <  symbol_profile  <  settings.json

    Does NOT call ``config.validate()`` — caller should validate afterwards.
    """
    from .config import TargetMode

    symbol = config.mt5.symbol
    profile = get_profile(symbol)
    if not profile:
        logger.debug("No symbol profile for %s — using base config", symbol)
        return

    logger.info("Applying symbol profile for %s", symbol)

    # Section mapping: profile key → config attribute
    section_map = {
        "mt5": config.mt5,
        "swing": config.swing,
        "displacement": config.displacement,
        "order_block": config.order_block,
        "stop": config.stop,
        "target": config.target,
        "trade_mgmt": config.trade_mgmt,
        "risk": config.risk,
        "bias_filter": config.bias_filter,
        "continuation": config.continuation,
        "execution": config.execution,
    }

    for section_name, section_obj in section_map.items():
        if section_name not in profile:
            continue
        for key, value in profile[section_name].items():
            if hasattr(section_obj, key):
                # Handle TargetMode enum
                if key == "mode" and section_name == "target":
                    value = TargetMode(value)
                setattr(section_obj, key, value)

    # Kill zone requires special handling (int keys for hourly_quality)
    if "kill_zone" in profile:
        kz = profile["kill_zone"]
        for key, value in kz.items():
            if key == "hourly_quality" and isinstance(value, dict):
                config.kill_zone.hourly_quality = {
                    int(h): float(q) for h, q in value.items()
                }
            elif hasattr(config.kill_zone, key):
                setattr(config.kill_zone, key, value)

    # Sentiment top-level fields
    if "sentiment" in profile:
        for key, value in profile["sentiment"].items():
            if hasattr(config.sentiment, key) and not isinstance(value, dict):
                setattr(config.sentiment, key, value)
