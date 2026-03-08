"""Ranking algorithm for the recommendation feed.

Scores listings/profiles for a given user based on multiple weighted factors.
Initial version uses a simple weighted-sum approach; can be replaced with
ML-based ranking as interaction data accumulates.

Scoring breakdown (weights sum to 1.0):
  - Proximity:      0.30  (closer = higher score)
  - Category match:  0.30  (matches user's preferred categories)
  - Budget alignment: 0.20  (listing budget fits user's range)
  - Freshness:       0.10  (newer listings rank higher)
  - Provider rating:  0.10  (higher-rated providers rank higher)
"""

import math
from datetime import datetime, timezone
from decimal import Decimal


# Maximum distance considered for scoring (beyond this, proximity score = 0)
MAX_DISTANCE_KM = 100.0

# Maximum age in days before freshness score drops to 0
MAX_AGE_DAYS = 30.0

# Weights
W_PROXIMITY = 0.30
W_CATEGORY = 0.30
W_BUDGET = 0.20
W_FRESHNESS = 0.10
W_RATING = 0.10


def compute_proximity_score(distance_km: float | None) -> float:
    """Score based on distance. 0km = 1.0, MAX_DISTANCE_KM+ = 0.0."""
    if distance_km is None:
        return 0.5  # unknown distance gets neutral score
    if distance_km <= 0:
        return 1.0
    if distance_km >= MAX_DISTANCE_KM:
        return 0.0
    # Exponential decay -- nearby entities score much higher
    return math.exp(-3.0 * distance_km / MAX_DISTANCE_KM)


def compute_category_score(
    listing_category: str | None,
    user_preferred_categories: list[str],
) -> float:
    """Score based on category match. Exact match = 1.0, no match = 0.0."""
    if not listing_category or not user_preferred_categories:
        return 0.5  # neutral if no preference set
    if listing_category in user_preferred_categories:
        return 1.0
    return 0.0


def compute_budget_score(
    listing_budget_min: Decimal | None,
    listing_budget_max: Decimal | None,
    user_budget_range: dict,
) -> float:
    """Score based on budget overlap between listing and user preference."""
    if listing_budget_min is None and listing_budget_max is None:
        return 0.5  # no budget info
    user_min = user_budget_range.get("min", 0)
    user_max = user_budget_range.get("max")
    if user_max is None:
        return 0.5  # user has no budget preference

    l_min = float(listing_budget_min or 0)
    l_max = float(listing_budget_max or l_min)
    u_min = float(user_min)
    u_max = float(user_max)

    # Calculate overlap
    overlap_start = max(l_min, u_min)
    overlap_end = min(l_max, u_max)

    if overlap_end <= overlap_start:
        return 0.0  # no overlap

    overlap = overlap_end - overlap_start
    total_range = max(l_max - l_min, u_max - u_min, 1.0)
    return min(overlap / total_range, 1.0)


def compute_freshness_score(created_at: datetime) -> float:
    """Score based on how recently the listing was created."""
    age_days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
    if age_days <= 0:
        return 1.0
    if age_days >= MAX_AGE_DAYS:
        return 0.0
    return 1.0 - (age_days / MAX_AGE_DAYS)


def compute_rating_score(rating_avg: float, rating_count: int) -> float:
    """Score based on provider rating, with Bayesian smoothing."""
    if rating_count == 0:
        return 0.5  # no ratings yet
    # Bayesian average: blend towards 3.0 (neutral) with low count
    prior_weight = 5  # equivalent to 5 reviews at 3.0
    smoothed = (rating_avg * rating_count + 3.0 * prior_weight) / (rating_count + prior_weight)
    return smoothed / 5.0  # normalize to 0-1


def rank_candidate(
    distance_km: float | None,
    listing_category: str | None,
    listing_budget_min: Decimal | None,
    listing_budget_max: Decimal | None,
    created_at: datetime,
    provider_rating_avg: float = 0.0,
    provider_rating_count: int = 0,
    user_preferred_categories: list[str] | None = None,
    user_budget_range: dict | None = None,
) -> dict:
    """Compute a composite ranking score for a candidate.

    Returns a dict with the total score and individual factor scores.
    """
    proximity = compute_proximity_score(distance_km)
    category = compute_category_score(listing_category, user_preferred_categories or [])
    budget = compute_budget_score(listing_budget_min, listing_budget_max, user_budget_range or {})
    freshness = compute_freshness_score(created_at)
    rating = compute_rating_score(provider_rating_avg, provider_rating_count)

    total = (
        W_PROXIMITY * proximity
        + W_CATEGORY * category
        + W_BUDGET * budget
        + W_FRESHNESS * freshness
        + W_RATING * rating
    )

    return {
        "total_score": round(total, 4),
        "factors": {
            "proximity": round(proximity, 4),
            "category": round(category, 4),
            "budget": round(budget, 4),
            "freshness": round(freshness, 4),
            "rating": round(rating, 4),
        },
    }
