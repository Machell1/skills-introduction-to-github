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
    # TIGHTENED: Off-peak hours blocked (0.0), FVG required, higher OB quality.
    # Only trades London build-up (9-12) and London/NY overlap (13-16).
    "XAUUSD": {
        "mt5": {"magic_number": 20240101},
        "displacement": {"body_atr_multiplier": 0.3},
        "order_block": {
            "min_sweep_depth_atr": 0.10,
            "max_mss_candles": 10,
            "entry_expiry_candles": 24,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
        },
        "stop": {"atr_buffer_multiplier": 0.25},
        "execution": {"max_spread_points": 50.0, "paper_spread_points": 30.0},
        "kill_zone": {
            "hourly_quality": {
                0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0,   # Asian — BLOCKED
                6: 0.0, 7: 0.0, 8: 0.0,                              # pre-London — BLOCKED
                9: 0.7, 10: 0.7, 11: 0.7,                            # London building
                12: 0.8,                                               # pre-overlap
                13: 1.0, 14: 1.0, 15: 1.0,                           # London/NY overlap — PEAK
                16: 0.9,                                               # NY afternoon
                17: 0.7, 18: 0.7,                                     # NY wind-down
                19: 0.0, 20: 0.0, 21: 0.0, 22: 0.0, 23: 0.0,       # off-hours — BLOCKED
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 72, "urgency_candles": 24},
        "bias_filter": {"counter_bias_min_r": 3.0},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── EURUSD ────────────────────────────────────────────────────
    # TIGHTENED: Only London open (8-10) and London/NY overlap (13-15).
    # Asian/late-NY fully blocked. FVG required, higher OB quality.
    "EURUSD": {
        "mt5": {"magic_number": 20240102},
        "displacement": {"body_atr_multiplier": 0.5},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 8,
            "entry_expiry_candles": 16,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
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
                0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0,  # Asian — BLOCKED
                7: 0.7,                                                # London pre-open
                8: 1.0, 9: 1.0, 10: 1.0,                             # London PEAK
                11: 0.8,
                12: 0.7,
                13: 1.0, 14: 1.0, 15: 1.0,                           # London/NY overlap — PEAK
                16: 0.8,
                17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0,                 # off-hours — BLOCKED
                21: 0.0, 22: 0.0, 23: 0.0,
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 3.0},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── GBPUSD ────────────────────────────────────────────────────
    # TIGHTENED: Same structure as EURUSD but London open peaks at 7-9.
    "GBPUSD": {
        "mt5": {"magic_number": 20240103},
        "displacement": {"body_atr_multiplier": 0.45},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 8,
            "entry_expiry_candles": 16,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
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
                0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0,  # Asian — BLOCKED
                7: 0.7,
                8: 1.0, 9: 1.0, 10: 1.0,                             # London PEAK
                11: 0.8,
                12: 0.7,
                13: 1.0, 14: 1.0, 15: 1.0,                           # London/NY overlap — PEAK
                16: 0.8,
                17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0,                 # off-hours — BLOCKED
                21: 0.0, 22: 0.0, 23: 0.0,
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 3.0},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── USDJPY ────────────────────────────────────────────────────
    # TIGHTENED: Only Tokyo peak (0-2) and NY peak (13-15). Dead zone blocked.
    "USDJPY": {
        "mt5": {"magic_number": 20240104},
        "displacement": {"body_atr_multiplier": 0.5},
        "order_block": {
            "min_sweep_depth_atr": 0.08,
            "max_mss_candles": 8,
            "entry_expiry_candles": 16,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
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
                0: 1.0, 1: 1.0, 2: 1.0,                             # Tokyo PEAK
                3: 0.8,
                4: 0.0, 5: 0.0, 6: 0.0,                              # dead zone — BLOCKED
                7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 0.0, 12: 0.0, # London — BLOCKED for JPY
                13: 1.0, 14: 1.0, 15: 1.0,                           # NY PEAK
                16: 0.8,
                17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0,                 # off-hours — BLOCKED
                21: 0.0, 22: 0.0, 23: 0.0,
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 48, "urgency_candles": 16},
        "bias_filter": {"counter_bias_min_r": 3.0},
        "swing": {"swing_length": 2},
        "sentiment": {"enabled": False},
    },

    # ── GBPJPY ────────────────────────────────────────────────────
    # TIGHTENED: Only Tokyo (0-2) and London open (7-9). Everything else blocked.
    # Risk reduced to 0.25% per trade for volatility protection.
    "GBPJPY": {
        "mt5": {"magic_number": 20240105},
        "displacement": {"body_atr_multiplier": 0.4},
        "order_block": {
            "min_sweep_depth_atr": 0.10,
            "max_mss_candles": 10,
            "entry_expiry_candles": 12,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
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
                0: 1.0, 1: 1.0, 2: 1.0,                             # Tokyo PEAK
                3: 0.8,
                4: 0.0, 5: 0.0, 6: 0.0,                              # BLOCKED
                7: 1.0, 8: 1.0, 9: 1.0,                              # London open PEAK
                10: 0.8,
                11: 0.0, 12: 0.0, 13: 0.0, 14: 0.0, 15: 0.0,       # off-hours — BLOCKED
                16: 0.0, 17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0,
                21: 0.0, 22: 0.0, 23: 0.0,
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 36, "urgency_candles": 12},
        "bias_filter": {"counter_bias_min_r": 3.0},
        "swing": {"swing_length": 3},
        "sentiment": {"enabled": False},
    },

    # ── EURJPY ────────────────────────────────────────────────────
    # TIGHTENED: Only Tokyo (0-2) and London open (7-9). Everything else blocked.
    "EURJPY": {
        "mt5": {"magic_number": 20240106},
        "displacement": {"body_atr_multiplier": 0.45},
        "order_block": {
            "min_sweep_depth_atr": 0.09,
            "max_mss_candles": 9,
            "entry_expiry_candles": 14,
            "require_fvg_confluence": True,
            "min_ob_body_range_ratio": 0.5,
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
                0: 1.0, 1: 1.0, 2: 1.0,                             # Tokyo PEAK
                3: 0.8,
                4: 0.0, 5: 0.0, 6: 0.0,                              # BLOCKED
                7: 1.0, 8: 1.0, 9: 1.0,                              # London open PEAK
                10: 0.8,
                11: 0.0, 12: 0.0, 13: 0.0, 14: 0.0, 15: 0.0,       # off-hours — BLOCKED
                16: 0.0, 17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0,
                21: 0.0, 22: 0.0, 23: 0.0,
            },
            "min_quality": 0.7,
            "low_quality_min_r": 2.5,
        },
        "trade_mgmt": {"max_hold_candles": 42, "urgency_candles": 14},
        "bias_filter": {"counter_bias_min_r": 3.0},
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
