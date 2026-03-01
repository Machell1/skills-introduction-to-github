"""
Sentiment Engine Data Models.

Defines the data structures used by the sentiment aggregation engine:
- SourceReading: individual reading from a data source
- SentimentSignal: aggregated output signal
- Enums for direction and source category
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SentimentDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SourceCategory(Enum):
    SMART_MONEY = "smart_money"
    SOCIAL_SENTIMENT = "social_sentiment"
    BET_PREDICTIONS = "bet_predictions"


@dataclass
class SourceReading:
    """A single reading from one sentiment data source."""

    source_name: str
    category: SourceCategory
    direction: SentimentDirection
    confidence: float  # 0.0 to 1.0
    raw_value: float = 0.0  # Source-specific numeric value
    timestamp: Optional[datetime] = None
    is_stale: bool = False  # True if serving from expired cache

    def score(self) -> float:
        """Convert direction to numeric: bullish=+1, bearish=-1, neutral=0."""
        if self.direction == SentimentDirection.BULLISH:
            return 1.0
        elif self.direction == SentimentDirection.BEARISH:
            return -1.0
        return 0.0


@dataclass
class SentimentSignal:
    """Aggregated sentiment output from all sources."""

    direction: Optional[SentimentDirection] = None
    net_score: float = 0.0  # Range [-1.0, +1.0]
    confidence: float = 0.0  # Aggregated confidence [0.0, 1.0]
    active_sources: int = 0  # Number of sources that contributed
    readings: list[SourceReading] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    def bias_string(self) -> Optional[str]:
        """Return the same interface as get_daily_bias(): 'bullish', 'bearish', or None."""
        if self.direction is None or self.direction == SentimentDirection.NEUTRAL:
            return None
        return self.direction.value
