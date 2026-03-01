"""
Sentiment & Smart Money Aggregation Engine.

Fetches, caches, and aggregates external sentiment data from multiple sources:
- Smart Money: COT data (CFTC), Gold ETF flows
- Social Sentiment: Fear & Greed Index, News headlines (AlphaVantage)
- Bet Predictions: Put/Call ratio (CBOE)

Produces a unified bullish/bearish/neutral signal that integrates with
the existing bias filter in bot.py.
"""

import csv
import io
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from .config import SentimentEngineConfig, SentimentSourceConfig
from .sentiment_models import (
    SentimentDirection,
    SentimentSignal,
    SourceCategory,
    SourceReading,
)

logger = logging.getLogger(__name__)

# Timeout for all HTTP requests (seconds)
HTTP_TIMEOUT = 15


# ── Abstract Adapter ────────────────────────────────────────────────


class SentimentAdapter(ABC):
    """Base class for all sentiment data source adapters."""

    def __init__(
        self, name: str, category: SourceCategory, source_config: SentimentSourceConfig,
    ):
        self.name = name
        self.category = category
        self.cfg = source_config
        self._cached_reading: Optional[SourceReading] = None
        self._cache_time: Optional[datetime] = None

    def get_reading(self) -> Optional[SourceReading]:
        """
        Cache-first fetch strategy:
        1. Return cached if TTL not expired
        2. Else fetch fresh
        3. On fetch failure, return stale cache with penalty flag
        """
        if not self.cfg.enabled:
            return None

        now = datetime.now(timezone.utc)

        # Check cache validity
        if self._cached_reading and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < self.cfg.cache_ttl_seconds:
                return self._cached_reading

        # Fetch fresh data
        try:
            reading = self._fetch()
            if reading:
                reading.timestamp = now
                reading.is_stale = False
                self._cached_reading = reading
                self._cache_time = now
                logger.info(
                    "[Sentiment] %s: %s (confidence: %.2f, raw: %.2f)",
                    self.name, reading.direction.value, reading.confidence, reading.raw_value,
                )
                return reading
        except Exception as e:
            logger.warning("[Sentiment] %s fetch failed: %s", self.name, e)

        # Return stale cache with penalty
        if self._cached_reading:
            stale = SourceReading(
                source_name=self._cached_reading.source_name,
                category=self._cached_reading.category,
                direction=self._cached_reading.direction,
                confidence=self._cached_reading.confidence,
                raw_value=self._cached_reading.raw_value,
                timestamp=self._cached_reading.timestamp,
                is_stale=True,
            )
            logger.info("[Sentiment] %s: serving stale cache (age: %s)", self.name,
                        now - self._cache_time if self._cache_time else "unknown")
            return stale

        return None

    @abstractmethod
    def _fetch(self) -> Optional[SourceReading]:
        """Fetch fresh data from the source. Must be implemented by subclasses."""
        ...


# ── File-Based Adapter Mixin ────────────────────────────────────────


class FileBasedAdapterMixin:
    """Mixin for adapters that read from local JSON files."""

    def _read_fallback_file(self, path: str) -> Optional[dict]:
        """Read and parse a JSON fallback file."""
        if not path:
            return None
        # Resolve relative to the package directory
        if not os.path.isabs(path):
            pkg_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(pkg_dir, path)
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.debug("[Sentiment] Fallback file not found: %s", path)
            return None
        except json.JSONDecodeError as e:
            logger.warning("[Sentiment] Invalid JSON in %s: %s", path, e)
            return None


# ── COT Data Adapter (CFTC API — Smart Money) ──────────────────────


class COTDataAdapter(SentimentAdapter):
    """
    Fetches CFTC Commitments of Traders data for gold futures.

    Looks at managed money (hedge funds) net positioning:
    - Large net long → bullish
    - Large net short → bearish
    - Neutral zone → neutral

    Free API: publicreporting.cftc.gov (Socrata)
    """

    def __init__(self, source_config: SentimentSourceConfig):
        super().__init__("COT Data (CFTC)", SourceCategory.SMART_MONEY, source_config)

    def _fetch(self) -> Optional[SourceReading]:
        url = self.cfg.api_url
        if not url:
            return None

        # Query for gold futures (commodity code 088691)
        params = {
            "$where": "commodity_name like '%GOLD%'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": 5,
        }
        resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            logger.warning("[COT] No gold data returned from CFTC API")
            return None

        latest = data[0]

        # Extract managed money positions (large speculators)
        try:
            mm_long = float(latest.get("m_money_positions_long_all", 0))
            mm_short = float(latest.get("m_money_positions_short_all", 0))
        except (ValueError, TypeError):
            logger.warning("[COT] Failed to parse managed money positions")
            return None

        net_position = mm_long - mm_short
        total = mm_long + mm_short

        if total == 0:
            return SourceReading(
                source_name=self.name, category=self.category,
                direction=SentimentDirection.NEUTRAL, confidence=0.0, raw_value=0.0,
            )

        # Net ratio: +1 = all long, -1 = all short
        net_ratio = net_position / total

        # Map to direction with confidence
        if net_ratio > 0.15:
            direction = SentimentDirection.BULLISH
            confidence = min(abs(net_ratio), 1.0)
        elif net_ratio < -0.15:
            direction = SentimentDirection.BEARISH
            confidence = min(abs(net_ratio), 1.0)
        else:
            direction = SentimentDirection.NEUTRAL
            confidence = 0.3

        return SourceReading(
            source_name=self.name, category=self.category,
            direction=direction, confidence=confidence, raw_value=net_ratio,
        )


# ── Gold ETF Flows Adapter (File-Based — Smart Money) ──────────────


class GoldETFFlowsAdapter(SentimentAdapter, FileBasedAdapterMixin):
    """
    Fetches SPDR Gold Shares (GLD) holdings data from official CSV.

    Primary: Downloads CSV from spdrgoldshares.com, computes daily tonnage change.
    Fallback: Reads from local JSON file if API fails.

    Tonnage change > 1.0 → bullish (inflows), < -1.0 → bearish (outflows).
    Source: https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv
    """

    def __init__(self, source_config: SentimentSourceConfig):
        super().__init__("Gold ETF Flows (GLD)", SourceCategory.SMART_MONEY, source_config)

    def _fetch(self) -> Optional[SourceReading]:
        # Primary: fetch SPDR CSV
        reading = self._fetch_spdr_csv()
        if reading:
            return reading

        # Fallback: local JSON file
        return self._fetch_fallback_json()

    def _fetch_spdr_csv(self) -> Optional[SourceReading]:
        """Download and parse SPDR Gold Trust CSV for tonnage change."""
        url = self.cfg.api_url
        if not url:
            return None

        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("[GLD ETF] CSV download failed: %s", e)
            return None

        try:
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)

            if len(rows) < 3:  # header + at least 2 data rows
                logger.warning("[GLD ETF] CSV has too few rows (%d)", len(rows))
                return None

            header = [h.strip().lower() for h in rows[0]]

            # Find the tonnes column (varies: "GLD Holdings in Tonnes", etc.)
            tonnes_col = None
            for i, col in enumerate(header):
                if "tonne" in col:
                    tonnes_col = i
                    break

            if tonnes_col is None:
                logger.warning("[GLD ETF] No tonnes column found in CSV header: %s", header)
                return None

            # Get last 2 valid rows (skip empty/malformed)
            valid_rows = []
            for row in reversed(rows[1:]):
                if len(row) > tonnes_col and row[tonnes_col].strip():
                    try:
                        float(row[tonnes_col].replace(",", ""))
                        valid_rows.append(row)
                    except ValueError:
                        continue
                if len(valid_rows) >= 2:
                    break

            if len(valid_rows) < 2:
                logger.warning("[GLD ETF] Not enough valid data rows for change calculation")
                return None

            today_tonnes = float(valid_rows[0][tonnes_col].replace(",", ""))
            yesterday_tonnes = float(valid_rows[1][tonnes_col].replace(",", ""))
            tonnage_change = today_tonnes - yesterday_tonnes

            logger.info(
                "[GLD ETF] Holdings: %.2f → %.2f tonnes (change: %+.2f)",
                yesterday_tonnes, today_tonnes, tonnage_change,
            )

        except Exception as e:
            logger.warning("[GLD ETF] CSV parsing failed: %s", e)
            return None

        return self._score_tonnage_change(tonnage_change)

    def _fetch_fallback_json(self) -> Optional[SourceReading]:
        """Read from local JSON fallback file."""
        data = self._read_fallback_file(self.cfg.fallback_file)
        if not data:
            return None

        if "direction" in data:
            direction = SentimentDirection(data["direction"])
            confidence = float(data.get("confidence", 0.5))
            raw_value = float(data.get("gld_tonnage_change", 0))
            return SourceReading(
                source_name=self.name, category=self.category,
                direction=direction, confidence=confidence, raw_value=raw_value,
            )

        gld = float(data.get("gld_tonnage_change", 0))
        iau = float(data.get("iau_tonnage_change", 0))
        return self._score_tonnage_change(gld + iau)

    def _score_tonnage_change(self, tonnage_change: float) -> SourceReading:
        """Convert tonnage change to directional reading."""
        if tonnage_change > 1.0:
            direction = SentimentDirection.BULLISH
            confidence = min(abs(tonnage_change) / 10.0, 0.9)
        elif tonnage_change < -1.0:
            direction = SentimentDirection.BEARISH
            confidence = min(abs(tonnage_change) / 10.0, 0.9)
        else:
            direction = SentimentDirection.NEUTRAL
            confidence = 0.3

        return SourceReading(
            source_name=self.name, category=self.category,
            direction=direction, confidence=confidence, raw_value=tonnage_change,
        )


# ── Fear & Greed Index Adapter (Free API — Social Sentiment) ───────


class FearGreedAdapter(SentimentAdapter):
    """
    Fetches the Crypto Fear & Greed Index from alternative.me.

    While primarily crypto-focused, extreme readings correlate with
    broader risk appetite which affects gold:
    - Extreme Fear (0-25) → risk-off → bullish for gold
    - Fear (25-45) → slightly bullish for gold
    - Neutral (45-55) → neutral
    - Greed (55-75) → slightly bearish for gold (risk-on)
    - Extreme Greed (75-100) → bearish for gold

    Note: Inverse relationship — fear = bullish gold, greed = bearish gold.
    """

    def __init__(self, source_config: SentimentSourceConfig):
        super().__init__("Fear & Greed Index", SourceCategory.SOCIAL_SENTIMENT, source_config)

    def _fetch(self) -> Optional[SourceReading]:
        url = self.cfg.api_url
        if not url:
            return None

        resp = requests.get(url, params={"limit": 1}, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "data" not in data or not data["data"]:
            logger.warning("[FearGreed] No data in response")
            return None

        value = int(data["data"][0]["value"])

        # Inverse mapping for gold: fear → bullish, greed → bearish
        if value <= 25:
            direction = SentimentDirection.BULLISH
            confidence = 0.8
        elif value <= 45:
            direction = SentimentDirection.BULLISH
            confidence = 0.5
        elif value <= 55:
            direction = SentimentDirection.NEUTRAL
            confidence = 0.3
        elif value <= 75:
            direction = SentimentDirection.BEARISH
            confidence = 0.5
        else:
            direction = SentimentDirection.BEARISH
            confidence = 0.8

        return SourceReading(
            source_name=self.name, category=self.category,
            direction=direction, confidence=confidence, raw_value=float(value),
        )


# ── News Sentiment Adapter (AlphaVantage — Social Sentiment) ───────


class NewsSentimentAdapter(SentimentAdapter):
    """
    Fetches gold/XAUUSD news sentiment from AlphaVantage API.

    Uses the NEWS_SENTIMENT function to get recent articles about gold
    and their sentiment scores. Requires a free API key.

    Aggregates sentiment_score across articles:
    - Mean > 0.15 → bullish
    - Mean < -0.15 → bearish
    - Otherwise → neutral
    """

    def __init__(self, source_config: SentimentSourceConfig):
        super().__init__("News Sentiment", SourceCategory.SOCIAL_SENTIMENT, source_config)

    def _fetch(self) -> Optional[SourceReading]:
        api_key = self.cfg.api_key
        if not api_key:
            logger.debug("[NewsSentiment] No API key configured, skipping")
            return None

        url = self.cfg.api_url
        if not url:
            return None

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": "FOREX:XAU",
            "topics": "financial_markets",
            "apikey": api_key,
            "limit": 50,
        }
        resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "feed" not in data:
            # May be rate-limited or invalid key
            if "Note" in data or "Information" in data:
                logger.warning("[NewsSentiment] API limit reached: %s",
                               data.get("Note", data.get("Information", "")))
            return None

        articles = data["feed"]
        if not articles:
            return SourceReading(
                source_name=self.name, category=self.category,
                direction=SentimentDirection.NEUTRAL, confidence=0.2, raw_value=0.0,
            )

        # Extract sentiment scores
        scores = []
        for article in articles:
            try:
                score = float(article.get("overall_sentiment_score", 0))
                scores.append(score)
            except (ValueError, TypeError):
                continue

        if not scores:
            return None

        mean_score = sum(scores) / len(scores)
        article_count = len(scores)

        # More articles → higher confidence (up to cap)
        base_confidence = min(article_count / 30.0, 0.8)

        if mean_score > 0.15:
            direction = SentimentDirection.BULLISH
            confidence = base_confidence * min(abs(mean_score) / 0.5, 1.0)
        elif mean_score < -0.15:
            direction = SentimentDirection.BEARISH
            confidence = base_confidence * min(abs(mean_score) / 0.5, 1.0)
        else:
            direction = SentimentDirection.NEUTRAL
            confidence = 0.3

        return SourceReading(
            source_name=self.name, category=self.category,
            direction=direction, confidence=min(confidence, 0.9), raw_value=mean_score,
        )


# ── Put/Call Ratio Adapter (File-Based — Bet Predictions) ──────────


class PutCallRatioAdapter(SentimentAdapter, FileBasedAdapterMixin):
    """
    Fetches CBOE index put/call ratio from official CSV archive.

    Primary: Downloads CSV from cdn.cboe.com, reads latest row.
    Fallback: Reads from local JSON file if API fails.

    P/C < 0.7 → bullish (more calls, expecting up)
    P/C 0.7-1.0 → neutral
    P/C > 1.0 → bearish (more puts, expecting down)

    Source: https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv
    """

    def __init__(self, source_config: SentimentSourceConfig):
        super().__init__("Put/Call Ratio (CBOE)", SourceCategory.BET_PREDICTIONS, source_config)

    def _fetch(self) -> Optional[SourceReading]:
        # Primary: fetch CBOE CSV
        reading = self._fetch_cboe_csv()
        if reading:
            return reading

        # Fallback: local JSON file
        return self._fetch_fallback_json()

    def _fetch_cboe_csv(self) -> Optional[SourceReading]:
        """Download and parse CBOE index put/call ratio CSV."""
        url = self.cfg.api_url
        if not url:
            return None

        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("[CBOE P/C] CSV download failed: %s", e)
            return None

        try:
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)

            if len(rows) < 2:  # header + at least 1 data row
                logger.warning("[CBOE P/C] CSV has too few rows (%d)", len(rows))
                return None

            header = [h.strip().upper() for h in rows[0]]

            # Find P/C ratio column
            pc_col = None
            for i, col in enumerate(header):
                if "P/C" in col or "RATIO" in col:
                    pc_col = i
                    break

            # Fallback: last column is typically the ratio
            if pc_col is None:
                pc_col = len(header) - 1

            # Get last valid row
            pc_ratio = None
            for row in reversed(rows[1:]):
                if len(row) > pc_col and row[pc_col].strip():
                    try:
                        pc_ratio = float(row[pc_col].strip())
                        date_str = row[0].strip() if row[0].strip() else "unknown"
                        break
                    except ValueError:
                        continue

            if pc_ratio is None:
                logger.warning("[CBOE P/C] No valid P/C ratio found in CSV")
                return None

            logger.info("[CBOE P/C] Latest ratio: %.3f (date: %s)", pc_ratio, date_str)

        except Exception as e:
            logger.warning("[CBOE P/C] CSV parsing failed: %s", e)
            return None

        return self._score_pc_ratio(pc_ratio)

    def _fetch_fallback_json(self) -> Optional[SourceReading]:
        """Read from local JSON fallback file."""
        data = self._read_fallback_file(self.cfg.fallback_file)
        if not data:
            return None

        pc_ratio = float(data.get("put_call_ratio", 0))

        if pc_ratio <= 0:
            put_vol = float(data.get("put_volume", 0))
            call_vol = float(data.get("call_volume", 0))
            if call_vol > 0:
                pc_ratio = put_vol / call_vol
            else:
                return None

        return self._score_pc_ratio(pc_ratio)

    def _score_pc_ratio(self, pc_ratio: float) -> SourceReading:
        """Convert put/call ratio to directional reading."""
        if pc_ratio < 0.7:
            direction = SentimentDirection.BULLISH
            confidence = min((0.7 - pc_ratio) / 0.4, 0.9)
        elif pc_ratio > 1.0:
            direction = SentimentDirection.BEARISH
            confidence = min((pc_ratio - 1.0) / 0.5, 0.9)
        else:
            direction = SentimentDirection.NEUTRAL
            confidence = 0.3

        return SourceReading(
            source_name=self.name, category=self.category,
            direction=direction, confidence=confidence, raw_value=pc_ratio,
        )


# ── Sentiment Engine (Aggregator) ──────────────────────────────────


class SentimentEngine:
    """
    Aggregates readings from all enabled sentiment adapters into a single
    directional signal with confidence score.

    Algorithm:
    1. Collect readings from all enabled adapters (cache-first)
    2. Filter by min_confidence threshold
    3. Compute weighted net score:
       weight = source_confidence * category_weight * stale_penalty
       score = direction_numeric * weight
       net_score = sum(scores) / sum(weights)
    4. Map net_score to direction via thresholds
    """

    # Map source categories to config weight attribute names
    _CATEGORY_WEIGHTS = {
        SourceCategory.SMART_MONEY: "smart_money_weight",
        SourceCategory.SOCIAL_SENTIMENT: "social_sentiment_weight",
        SourceCategory.BET_PREDICTIONS: "bet_predictions_weight",
    }

    def __init__(self, config: SentimentEngineConfig):
        self.config = config
        self._adapters: list[SentimentAdapter] = []
        self._last_signal: Optional[SentimentSignal] = None

        # Initialize adapters for enabled sources
        self._init_adapters()

        logger.info(
            "[SentimentEngine] Initialized with %d adapter(s) | mode=%s",
            len(self._adapters), config.mode,
        )

    def _init_adapters(self):
        """Create adapter instances for each enabled source."""
        adapter_map = [
            (self.config.cot_data, COTDataAdapter),
            (self.config.fear_greed_index, FearGreedAdapter),
            (self.config.news_sentiment, NewsSentimentAdapter),
            (self.config.put_call_ratio, PutCallRatioAdapter),
            (self.config.gold_etf_flows, GoldETFFlowsAdapter),
        ]
        for src_config, adapter_cls in adapter_map:
            if src_config.enabled:
                self._adapters.append(adapter_cls(src_config))

    def get_sentiment(self) -> Optional[SentimentSignal]:
        """
        Fetch and aggregate all sentiment sources.

        Returns:
            SentimentSignal with direction, net_score, confidence, readings.
            Returns None if no sources are available.
        """
        if not self._adapters:
            return None

        # Collect readings from all adapters
        readings: list[SourceReading] = []
        for adapter in self._adapters:
            reading = adapter.get_reading()
            if reading and reading.confidence >= self.config.min_confidence:
                readings.append(reading)

        if not readings:
            logger.info("[SentimentEngine] No readings above min_confidence (%.2f)",
                        self.config.min_confidence)
            return self._last_signal  # Return last known signal

        # Log individual readings
        if self.config.log_readings:
            for r in readings:
                stale_tag = " [STALE]" if r.is_stale else ""
                logger.info(
                    "  [%s] %s: %s (conf=%.2f, raw=%.2f)%s",
                    r.category.value, r.source_name,
                    r.direction.value, r.confidence, r.raw_value, stale_tag,
                )

        # Compute weighted aggregation
        total_weight = 0.0
        weighted_score = 0.0

        for reading in readings:
            category_weight_attr = self._CATEGORY_WEIGHTS.get(reading.category, "")
            category_weight = getattr(self.config, category_weight_attr, 0.33)

            stale_penalty = self.config.stale_weight_factor if reading.is_stale else 1.0
            weight = reading.confidence * category_weight * stale_penalty

            weighted_score += reading.score() * weight
            total_weight += weight

        if total_weight == 0:
            return None

        net_score = weighted_score / total_weight  # Range [-1, +1]
        avg_confidence = total_weight / len(readings)

        # Map to direction
        if net_score > self.config.bullish_threshold:
            direction = SentimentDirection.BULLISH
        elif net_score < self.config.bearish_threshold:
            direction = SentimentDirection.BEARISH
        else:
            direction = SentimentDirection.NEUTRAL

        signal = SentimentSignal(
            direction=direction,
            net_score=net_score,
            confidence=min(avg_confidence, 1.0),
            active_sources=len(readings),
            readings=readings,
            timestamp=datetime.now(timezone.utc),
        )

        logger.info(
            "[SentimentEngine] Aggregated: %s (score=%.3f, conf=%.2f, sources=%d)",
            direction.value, net_score, signal.confidence, len(readings),
        )

        self._last_signal = signal
        return signal

    @property
    def adapter_count(self) -> int:
        """Number of active adapters."""
        return len(self._adapters)

    @property
    def last_signal(self) -> Optional[SentimentSignal]:
        """Most recent aggregated signal."""
        return self._last_signal

    def get_bias_string(self) -> Optional[str]:
        """
        Convenience method: get sentiment as the same interface as get_daily_bias().
        Returns 'bullish', 'bearish', or None.
        """
        signal = self.get_sentiment()
        if signal is None:
            return None
        return signal.bias_string()
