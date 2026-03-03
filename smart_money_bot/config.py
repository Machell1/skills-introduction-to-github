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
    entry_timeframes: list = field(default_factory=lambda: ["M15", "M30"])  # Lower TFs for entry detection
    magic_number: int = 20240101
    deviation: int = 20  # Max slippage in points
    fill_type: str = "IOC"  # IOC for Deriv


@dataclass
class SwingConfig:
    """Fractal pivot / swing detection parameters."""
    swing_length: int = 2  # L bars left and right for swing detection (range: 2-6)


@dataclass
class DisplacementConfig:
    """Displacement candle detection parameters."""
    atr_period: int = 14
    body_atr_multiplier: float = 0.3  # k: body >= k * ATR (range: 0.3-2.0); 0.3 captures XAUUSD displacement without excessive near-misses


@dataclass
class OrderBlockConfig:
    """Order block entry parameters."""
    entry_fraction: float = 0.50  # f: entry at OB_low + f*(OB_high - OB_low) (range: 0.30-0.70)
    entry_expiry_candles: int = 36  # M: cancel if not filled within M candles (range: 24-96)
    max_mss_candles: int = 15  # N: max candles after sweep to confirm MSS (range: 6-40)
    ob_lookback: int = 20  # How many candles back to search for the OB (range: 10-50)
    equal_level_atr_fraction: float = 0.1  # Equal highs/lows tolerance as fraction of ATR
    require_fvg_confluence: bool = True  # Require FVG overlapping OB for institutional confirmation
    min_ob_body_range_ratio: float = 0.5  # Min body/range ratio for OB candle quality (0.5 = strong body)
    use_fibonacci_entry: bool = True  # Use OTE (62-79% retracement) instead of fixed fraction
    fib_entry_level: float = 0.705  # Fibonacci retracement level for OTE (70.5% = midpoint of 62-79%)
    fvg_max_age_candles: int = 30  # FVGs older than this get reduced weight
    min_sweep_depth_atr: float = 0.10  # Min sweep depth as fraction of ATR to filter inducements


@dataclass
class StopConfig:
    """Stop loss parameters."""
    atr_buffer_multiplier: float = 0.25  # b: stop buffer = b * ATR (range: 0.10-0.50)


@dataclass
class TargetConfig:
    """Take profit / target parameters."""
    mode: TargetMode = TargetMode.LIQUIDITY
    fixed_r_multiple: float = 2.5  # R_target for fixed-R mode / fallback (range: 1.3-3.0)
    liquidity_min_r: float = 2.0  # Minimum acceptable R for liquidity target (tightened from 1.5)
    liquidity_max_r: float = 5.0  # Cap R for liquidity target (range: 3.0-6.0)


@dataclass
class TradeManagementConfig:
    """Trade management parameters."""
    max_hold_candles: int = 72  # H: time stop in candles (range: 48-288)
    breakeven_enabled: bool = True
    trailing_stop_levels: list = field(default_factory=lambda: [
        [1.0, 0.5], [1.5, 0.75], [2.0, 1.25],
        [2.5, 1.5], [3.0, 2.0], [4.0, 3.0],  # Extended levels for runners
    ])
    partial_close_enabled: bool = True  # Close fraction at first target
    partial_close_fraction: float = 0.4  # Close this fraction at trigger
    partial_close_r_trigger: float = 1.0  # Trigger partial close at this R
    urgency_candles: int = 24  # Close trade if < 0.5R profit after this many candles
    multi_partial_schedule: list = field(default_factory=lambda: [
        [1.0, 0.40],   # At 1.0R, close 40% of position
        [2.5, 0.25],   # At 2.5R, close 25% of remaining
        [4.0, 0.50],   # At 4.0R, close 50% of remaining
    ])


@dataclass
class KillZoneConfig:
    """Session quality matrix — trade intensity by hour."""
    enabled: bool = True
    # Quality score (0.0-1.0) per UTC hour. 0.0 = no trade, 1.0 = best session.
    hourly_quality: dict = field(default_factory=lambda: {
        0: 0.3, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.3, 6: 0.3,  # Asian session (low quality, high-R only)
        7: 0.5, 8: 0.6, 9: 0.7, 10: 0.8, 11: 0.8, 12: 0.85,
        13: 1.0, 14: 1.0, 15: 1.0, 16: 0.9,  # London/NY overlap
        17: 0.8, 18: 0.75, 19: 0.7, 20: 0.5,
        21: 0.3, 22: 0.3, 23: 0.3,  # Late session (low quality, high-R only)
    })
    min_quality: float = 0.7  # Skip hours below this quality (tightened: blocks off-peak completely)
    low_quality_min_r: float = 2.5  # Require higher R during quality 0.7-0.8 hours (tightened from 1.8)


@dataclass
class RiskConfig:
    """Risk management and position sizing parameters."""
    risk_per_trade_pct: float = 0.35  # r: fraction of equity risked per trade (range: 0.10-1.0%)
    max_positions: int = 2  # Max concurrent positions (tightened from 3 — concentrate on best setups)
    daily_loss_limit_pct: float = 1.5  # L%: stop trading after this daily loss
    weekly_drawdown_brake_pct: float = 3.0  # Reduce risk by half after this rolling drawdown
    rolling_trade_window: int = 10  # Number of trades for rolling drawdown check
    risk_reduction_factor: float = 0.5  # Multiply risk by this when drawdown brake triggers
    max_total_open_risk_pct: float = 1.0  # Cap on total open risk across all positions (tightened from 1.5)
    max_drawdown_halt_pct: float = 4.5  # HARD HALT: stop all trading at this drawdown from peak
    hard_drawdown_resume_pct: float = 3.0  # Resume trading when drawdown recovers to this level
    multi_pair_max_total_positions: int = 8  # Max positions across ALL symbols (0 = disabled)


@dataclass
class BiasFilterConfig:
    """Higher-timeframe bias filter."""
    enabled: bool = True
    ema_period: int = 20  # Daily EMA period for directional bias
    require_alignment: bool = True  # Require bias alignment for reversals (higher win rate)
    premium_discount_enabled: bool = True  # Only long in discount, short in premium
    counter_bias_min_r: float = 3.0  # Allow counter-bias trades if sweep quality >= 0.90 and R >= this value (tightened from 2.0)


@dataclass
class ContinuationConfig:
    """Continuation template specific parameters."""
    fixed_r_multiple: float = 2.0  # Typically 1.8-3.0 for continuation
    min_r_multiple: float = 1.2  # Minimum R for liquidity-based targets
    max_r_multiple: float = 4.0  # Cap R for liquidity-based targets


@dataclass
class SentimentSourceConfig:
    """Configuration for a single sentiment data source."""
    enabled: bool = False
    weight: float = 1.0
    api_url: str = ""
    api_key: str = ""
    fallback_file: str = ""
    cache_ttl_seconds: int = 3600  # Default 1 hour


@dataclass
class SentimentEngineConfig:
    """Sentiment aggregation engine configuration."""
    enabled: bool = False
    mode: str = "augment"  # augment | replace | confirm
    min_confidence: float = 0.4  # Discard readings below this confidence
    high_confidence: float = 0.7  # Threshold for sentiment to override EMA in augment mode
    smart_money_weight: float = 0.45
    social_sentiment_weight: float = 0.25
    bet_predictions_weight: float = 0.30
    bullish_threshold: float = 0.15  # net_score > this → bullish
    bearish_threshold: float = -0.15  # net_score < this → bearish
    stale_weight_factor: float = 0.3  # Multiply weight by this for stale data
    log_readings: bool = True  # Log individual source readings
    cot_data: Optional[SentimentSourceConfig] = None
    fear_greed_index: Optional[SentimentSourceConfig] = None
    news_sentiment: Optional[SentimentSourceConfig] = None
    put_call_ratio: Optional[SentimentSourceConfig] = None
    gold_etf_flows: Optional[SentimentSourceConfig] = None

    def __post_init__(self):
        if self.cot_data is None:
            self.cot_data = SentimentSourceConfig(
                enabled=True,
                api_url="https://publicreporting.cftc.gov/resource/6dca-aqc2.json",
                cache_ttl_seconds=604800,
            )
        if self.fear_greed_index is None:
            self.fear_greed_index = SentimentSourceConfig(
                enabled=True,
                api_url="https://api.alternative.me/fng/",
                cache_ttl_seconds=3600,
            )
        if self.news_sentiment is None:
            self.news_sentiment = SentimentSourceConfig(
                enabled=True,
                api_url="https://www.alphavantage.co/query",
                cache_ttl_seconds=1800,
            )
        if self.put_call_ratio is None:
            self.put_call_ratio = SentimentSourceConfig(
                enabled=True,
                api_url="https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv",
                fallback_file="sentiment_data/put_call.json",
                cache_ttl_seconds=3600,
            )
        if self.gold_etf_flows is None:
            self.gold_etf_flows = SentimentSourceConfig(
                enabled=False,  # SPDR has blocked direct CSV access; enable with valid URL or fallback file
                api_url="",
                fallback_file="sentiment_data/etf_flows.json",
                cache_ttl_seconds=86400,
            )


@dataclass
class ExecutionConfig:
    """Execution and monitoring parameters."""
    check_interval_seconds: int = 60  # How often to check for signals
    max_spread_points: float = 50.0  # Max acceptable spread in points
    paper_spread_points: float = 30.0  # Simulated spread for paper mode
    volatility_filter_enabled: bool = True
    volatility_filter_atr_percentile: float = 90.0  # Skip trades when ATR > 90th percentile
    log_level: str = "INFO"
    log_file: str = "smc_bot.log"
    paper_trading: bool = True  # Start in paper mode for safety
    close_positions_on_shutdown: bool = False  # Close all positions on bot stop
    trade_journal_path: str = "trade_journal.csv"  # CSV journal export path
    reconnect_attempts: int = 3  # Number of reconnect attempts before exit
    dedup_atr_fraction: float = 0.5  # Dedup radius: skip new setups within this fraction of ATR from existing entries
    session_filter_enabled: bool = True
    session_start_utc: int = 7  # Trading session start hour UTC (London open)
    session_end_utc: int = 20  # Trading session end hour UTC (NY close)


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
    kill_zone: KillZoneConfig = field(default_factory=KillZoneConfig)
    sentiment: SentimentEngineConfig = field(default_factory=SentimentEngineConfig)
    active_templates: list = field(default_factory=lambda: [
        TemplateType.REVERSAL,
        TemplateType.CONTINUATION,
    ])

    @classmethod
    def from_dict(cls, d: dict) -> "BotConfig":
        """Build config from a flat or nested dictionary.

        Priority order: config.py defaults < settings.json < symbol_profile.
        Settings.json provides shared values (credentials, general prefs),
        then the symbol profile layers on top with parameters specifically
        tuned for the active symbol's ICT/SMC characteristics.
        """
        cfg = cls()

        # ── Step 1: Apply settings.json user values ──
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
        # Handle kill_zone config (dict values need special handling for hourly_quality)
        if "kill_zone" in d:
            kz = d["kill_zone"]
            for k, v in kz.items():
                if k == "hourly_quality" and isinstance(v, dict):
                    # JSON keys are strings; convert to int
                    cfg.kill_zone.hourly_quality = {int(h): q for h, q in v.items()}
                elif hasattr(cfg.kill_zone, k):
                    setattr(cfg.kill_zone, k, v)
        # Handle sentiment config separately (nested sub-configs)
        if "sentiment" in d:
            s = d["sentiment"]
            for k, v in s.items():
                if hasattr(cfg.sentiment, k) and not isinstance(v, dict):
                    setattr(cfg.sentiment, k, v)
            # Parse nested source configs
            source_fields = [
                "cot_data", "fear_greed_index", "news_sentiment",
                "put_call_ratio", "gold_etf_flows",
            ]
            for sf in source_fields:
                if sf in s and isinstance(s[sf], dict):
                    src_obj = getattr(cfg.sentiment, sf)
                    for k, v in s[sf].items():
                        if hasattr(src_obj, k):
                            setattr(src_obj, k, v)
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

        # ── Step 2: Apply symbol profile on top of settings.json ──
        # Profile overrides ensure each symbol gets its tuned parameters
        # regardless of what's in settings.json (which may have XAUUSD values).
        try:
            from .symbol_profiles import apply_profile
            apply_profile(cfg)
        except ImportError:
            pass  # symbol_profiles not yet available

        cfg.validate()
        return cfg

    def validate(self):
        """Validate config values are within sane bounds. Logs warnings and fixes critical issues."""
        import logging
        _log = logging.getLogger(__name__)
        warnings = []

        # Critical bounds — clamp to safe values
        if self.displacement.atr_period < 1:
            self.displacement.atr_period = 14
            warnings.append("atr_period was < 1, reset to 14")
        if self.risk.risk_per_trade_pct <= 0:
            self.risk.risk_per_trade_pct = 0.35
            warnings.append("risk_per_trade_pct was <= 0, reset to 0.35")
        if self.risk.risk_per_trade_pct > 5.0:
            self.risk.risk_per_trade_pct = 5.0
            warnings.append("risk_per_trade_pct was > 5%, clamped to 5%")
        if self.risk.max_positions < 1:
            self.risk.max_positions = 1
            warnings.append("max_positions was < 1, reset to 1")
        if self.swing.swing_length < 1:
            self.swing.swing_length = 2
            warnings.append("swing_length was < 1, reset to 2")

        # Advisory warnings
        if self.displacement.body_atr_multiplier < 0.1:
            warnings.append(f"body_atr_multiplier={self.displacement.body_atr_multiplier} is very low, may produce false signals")
        if self.risk.daily_loss_limit_pct > 10.0:
            warnings.append(f"daily_loss_limit_pct={self.risk.daily_loss_limit_pct}% is very high")
        if self.target.fixed_r_multiple < 1.0:
            warnings.append(f"fixed_r_multiple={self.target.fixed_r_multiple} is < 1R (negative expectancy)")

        # Partial close fraction must be 0 < f < 1
        if self.trade_mgmt.partial_close_fraction <= 0 or self.trade_mgmt.partial_close_fraction >= 1.0:
            self.trade_mgmt.partial_close_fraction = 0.5
            warnings.append("partial_close_fraction was out of (0,1) range, reset to 0.5")

        # Urgency candles must be less than max_hold_candles
        if self.trade_mgmt.urgency_candles >= self.trade_mgmt.max_hold_candles:
            self.trade_mgmt.urgency_candles = int(self.trade_mgmt.max_hold_candles * 0.67)
            warnings.append(f"urgency_candles >= max_hold_candles, reset to {self.trade_mgmt.urgency_candles}")

        # Hard drawdown halt must be > resume threshold
        if self.risk.max_drawdown_halt_pct <= self.risk.hard_drawdown_resume_pct:
            self.risk.hard_drawdown_resume_pct = round(self.risk.max_drawdown_halt_pct * 0.67, 2)
            warnings.append("hard_drawdown_resume_pct >= halt_pct, reset for hysteresis")

        # Trailing stop levels must be sorted by trigger
        if self.trade_mgmt.trailing_stop_levels:
            self.trade_mgmt.trailing_stop_levels.sort(key=lambda x: x[0])

        # Kill zone validation
        if self.kill_zone.min_quality < 0 or self.kill_zone.min_quality > 1.0:
            self.kill_zone.min_quality = 0.5
            warnings.append("kill_zone.min_quality out of [0,1], reset to 0.5")
        if self.kill_zone.low_quality_min_r < 1.0:
            self.kill_zone.low_quality_min_r = 1.8
            warnings.append("kill_zone.low_quality_min_r < 1.0, reset to 1.8")
        # Validate hourly_quality keys (0-23) and values (0.0-1.0)
        valid_hq = {}
        for h, q in self.kill_zone.hourly_quality.items():
            if not (0 <= h <= 23):
                warnings.append(f"kill_zone.hourly_quality key {h} not in 0-23, skipped")
                continue
            q = max(0.0, min(1.0, float(q)))
            valid_hq[h] = q
        self.kill_zone.hourly_quality = valid_hq

        # Counter-bias min R must be >= 1.0
        if self.bias_filter.counter_bias_min_r < 1.0:
            self.bias_filter.counter_bias_min_r = 2.0
            warnings.append("bias_filter.counter_bias_min_r < 1.0, reset to 2.0")

        # Order block entry_fraction bounds
        if self.order_block.entry_fraction < 0.1 or self.order_block.entry_fraction > 0.9:
            self.order_block.entry_fraction = 0.50
            warnings.append("order_block.entry_fraction out of [0.1,0.9], reset to 0.50")
        if self.order_block.fib_entry_level < 0.5 or self.order_block.fib_entry_level > 0.9:
            self.order_block.fib_entry_level = 0.705
            warnings.append("order_block.fib_entry_level out of [0.5,0.9], reset to 0.705")

        # Session hours bounds
        if self.execution.session_start_utc < 0 or self.execution.session_start_utc > 23:
            self.execution.session_start_utc = 7
            warnings.append("session_start_utc out of [0,23], reset to 7")
        if self.execution.session_end_utc < 0 or self.execution.session_end_utc > 23:
            self.execution.session_end_utc = 20
            warnings.append("session_end_utc out of [0,23], reset to 20")

        # Multi-partial schedule: fractions should not exceed 1.0 cumulatively
        if self.trade_mgmt.multi_partial_schedule:
            self.trade_mgmt.multi_partial_schedule.sort(key=lambda x: x[0])
            cumulative = 0.0
            for _, frac in self.trade_mgmt.multi_partial_schedule:
                remaining = 1.0 - cumulative
                cumulative += remaining * frac
            if cumulative > 0.99:
                warnings.append(f"multi_partial_schedule cumulative close ~{cumulative:.2%} — nearly all lots will be closed before final exit")

        # Sentiment engine validation
        if self.sentiment.mode not in ("augment", "replace", "confirm"):
            self.sentiment.mode = "augment"
            warnings.append(f"sentiment.mode was invalid, reset to 'augment'")
        total_weight = (self.sentiment.smart_money_weight
                        + self.sentiment.social_sentiment_weight
                        + self.sentiment.bet_predictions_weight)
        if total_weight <= 0:
            self.sentiment.smart_money_weight = 0.45
            self.sentiment.social_sentiment_weight = 0.25
            self.sentiment.bet_predictions_weight = 0.30
            warnings.append("sentiment category weights summed to 0, reset to defaults")

        for w in warnings:
            _log.warning("Config validation: %s", w)
