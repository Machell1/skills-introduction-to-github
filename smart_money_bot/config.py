"""
Configuration module for the SMC Trading Bot.
All parameters are expressed as open parameters for calibration.
Capital size, leverage, and performance horizon remain open.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TargetMode(Enum):
    FIXED_R = "fixed_r"
    LIQUIDITY = "liquidity"


class TemplateType(Enum):
    REVERSAL = "reversal"
    CONTINUATION = "continuation"


class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class MT5Config:
    """MT5 connection configuration for Deriv broker."""
    login: int = 0
    password: str = ""
    server: str = "Deriv-Demo"
    path: str = ""  # Path to MT5 terminal executable
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    timeframe_daily: str = "D1"
    magic_number: int = 20240101
    deviation: int = 20  # Max slippage in points
    fill_type: str = "IOC"  # IOC for Deriv


@dataclass
class SwingConfig:
    """Fractal pivot / swing detection parameters."""
    swing_length: int = 3  # L bars left and right for swing detection (range: 2-6)


@dataclass
class DisplacementConfig:
    """Displacement candle detection parameters."""
    atr_period: int = 14
    body_atr_multiplier: float = 1.0  # k: body >= k * ATR (range: 0.5-2.0)


@dataclass
class OrderBlockConfig:
    """Order block entry parameters."""
    entry_fraction: float = 0.50  # f: entry at OB_low + f*(OB_high - OB_low) (range: 0.30-0.70)
    entry_expiry_candles: int = 48  # M: cancel if not filled within M candles (range: 24-96)


@dataclass
class StopConfig:
    """Stop loss parameters."""
    atr_buffer_multiplier: float = 0.25  # b: stop buffer = b * ATR (range: 0.10-0.50)


@dataclass
class TargetConfig:
    """Take profit / target parameters."""
    mode: TargetMode = TargetMode.FIXED_R
    fixed_r_multiple: float = 1.8  # R_target for fixed-R mode (range: 1.3-3.0)
    liquidity_min_r: float = 1.2  # Minimum acceptable R for liquidity target (range: 1.0-1.8)
    liquidity_max_r: float = 4.0  # Cap R for liquidity target (range: 3.0-6.0)


@dataclass
class TradeManagementConfig:
    """Trade management parameters."""
    max_hold_candles: int = 192  # H: time stop in candles (range: 72-288)
    breakeven_enabled: bool = True
    breakeven_trigger_r: float = 1.0  # Move to BE after +1R
    breakeven_offset_r: float = 0.1  # BE offset (entry + 0.1R)


@dataclass
class RiskConfig:
    """Risk management and position sizing parameters."""
    risk_per_trade_pct: float = 0.35  # r: fraction of equity risked per trade (range: 0.10-0.60%)
    max_positions: int = 1  # Single-position rule per template
    daily_loss_limit_pct: float = 1.0  # L%: stop trading after this daily loss
    weekly_drawdown_brake_pct: float = 3.0  # Reduce risk by half after this rolling drawdown
    rolling_trade_window: int = 10  # Number of trades for rolling drawdown check
    risk_reduction_factor: float = 0.5  # Multiply risk by this when drawdown brake triggers
    max_total_open_risk_pct: float = 1.5  # Cap on total open risk across all positions


@dataclass
class BiasFilterConfig:
    """Higher-timeframe bias filter."""
    enabled: bool = True
    ema_period: int = 50  # Daily EMA period for directional bias
    require_alignment: bool = True  # Only trade in direction of daily bias


@dataclass
class ContinuationConfig:
    """Continuation template specific parameters."""
    fixed_r_multiple: float = 2.0  # Typically 1.8-3.0 for continuation


@dataclass
class ExecutionConfig:
    """Execution and monitoring parameters."""
    check_interval_seconds: int = 60  # How often to check for signals
    max_spread_points: float = 50.0  # Max acceptable spread in points
    volatility_filter_enabled: bool = True
    volatility_filter_atr_percentile: float = 95.0  # Skip trades when ATR > 95th percentile
    no_trade_minutes_before_news: int = 30
    log_level: str = "INFO"
    log_file: str = "smc_bot.log"
    paper_trading: bool = True  # Start in paper mode for safety


@dataclass
class BotConfig:
    """Master configuration aggregating all sub-configs."""
    mt5: MT5Config = field(default_factory=MT5Config)
    swing: SwingConfig = field(default_factory=SwingConfig)
    displacement: DisplacementConfig = field(default_factory=DisplacementConfig)
    order_block: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    stop: StopConfig = field(default_factory=StopConfig)
    target: TargetConfig = field(default_factory=TargetConfig)
    trade_mgmt: TradeManagementConfig = field(default_factory=TradeManagementConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    bias_filter: BiasFilterConfig = field(default_factory=BiasFilterConfig)
    continuation: ContinuationConfig = field(default_factory=ContinuationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    active_templates: list = field(default_factory=lambda: [
        TemplateType.REVERSAL,
        TemplateType.CONTINUATION,
    ])

    @classmethod
    def from_dict(cls, d: dict) -> "BotConfig":
        """Build config from a flat or nested dictionary."""
        cfg = cls()
        section_map = {
            "mt5": (cfg.mt5, MT5Config),
            "swing": (cfg.swing, SwingConfig),
            "displacement": (cfg.displacement, DisplacementConfig),
            "order_block": (cfg.order_block, OrderBlockConfig),
            "stop": (cfg.stop, StopConfig),
            "target": (cfg.target, TargetConfig),
            "trade_mgmt": (cfg.trade_mgmt, TradeManagementConfig),
            "risk": (cfg.risk, RiskConfig),
            "bias_filter": (cfg.bias_filter, BiasFilterConfig),
            "continuation": (cfg.continuation, ContinuationConfig),
            "execution": (cfg.execution, ExecutionConfig),
        }
        for section_name, (section_obj, section_cls) in section_map.items():
            if section_name in d:
                for k, v in d[section_name].items():
                    if hasattr(section_obj, k):
                        field_type = section_cls.__dataclass_fields__[k].type
                        if field_type == "TargetMode" or field_type is TargetMode:
                            v = TargetMode(v)
                        setattr(section_obj, k, v)
        if "active_templates" in d:
            cfg.active_templates = [TemplateType(t) for t in d["active_templates"]]
        return cfg
