"""Elasticsearch client for full-text search across listings and profiles.

Indexes:
  - jobsy-listings: Service listings with geo_point, categories, skills
  - jobsy-profiles: User profiles with skills, bio text

When Elasticsearch is unavailable, search falls back to basic
HTTP queries against the listings/profiles services.
"""

import logging
import os
from typing import Any

from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
ES_USERNAME = os.getenv("ELASTICSEARCH_USERNAME", "")
ES_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")

_client: AsyncElasticsearch | None = None

LISTINGS_INDEX = "jobsy-listings"
PROFILES_INDEX = "jobsy-profiles"

LISTINGS_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "poster_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard"},
            "description": {"type": "text", "analyzer": "standard"},
            "category": {"type": "keyword"},
            "skills": {"type": "keyword"},
            "parish": {"type": "keyword"},
            "location": {"type": "geo_point"},
            "listing_type": {"type": "keyword"},
            "budget_min": {"type": "float"},
            "budget_max": {"type": "float"},
            "status": {"type": "keyword"},
            "created_at": {"type": "date"},
        }
    }
}

PROFILES_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "display_name": {"type": "text"},
            "bio": {"type": "text", "analyzer": "standard"},
            "skills": {"type": "keyword"},
            "parish": {"type": "keyword"},
            "location": {"type": "geo_point"},
            "average_rating": {"type": "float"},
            "total_reviews": {"type": "integer"},
        }
    }
}


async def get_client() -> AsyncElasticsearch | None:
    """Get or create the Elasticsearch client."""
    global _client
    if _client is not None:
        return _client

    try:
        kwargs: dict[str, Any] = {"hosts": [ES_URL]}
        if ES_USERNAME:
            kwargs["basic_auth"] = (ES_USERNAME, ES_PASSWORD)

        _client = AsyncElasticsearch(**kwargs)
        info = await _client.info()
        logger.info("Connected to Elasticsearch %s", info["version"]["number"])
        return _client
    except Exception:
        logger.warning("Elasticsearch not available at %s", ES_URL)
        _client = None
        return None


async def ensure_indices() -> None:
    """Create search indices if they don't exist."""
    client = await get_client()
    if not client:
        return

    for index, mapping in [(LISTINGS_INDEX, LISTINGS_MAPPING), (PROFILES_INDEX, PROFILES_MAPPING)]:
        if not await client.indices.exists(index=index):
            await client.indices.create(index=index, body=mapping)
            logger.info("Created index: %s", index)


async def index_listing(listing: dict) -> None:
    """Index or update a listing document."""
    client = await get_client()
    if not client:
        return

    doc = {
        "id": listing["id"],
        "poster_id": listing.get("poster_id"),
        "title": listing.get("title"),
        "description": listing.get("description"),
        "category": listing.get("category"),
        "skills": listing.get("skills_required", []),
        "parish": listing.get("parish"),
        "listing_type": listing.get("listing_type"),
        "budget_min": listing.get("budget_min"),
        "budget_max": listing.get("budget_max"),
        "status": listing.get("status", "active"),
        "created_at": listing.get("created_at"),
    }

    if listing.get("latitude") and listing.get("longitude"):
        doc["location"] = {"lat": listing["latitude"], "lon": listing["longitude"]}

    await client.index(index=LISTINGS_INDEX, id=listing["id"], document=doc)


async def index_profile(profile: dict) -> None:
    """Index or update a profile document."""
    client = await get_client()
    if not client:
        return

    doc = {
        "id": profile["id"],
        "display_name": profile.get("display_name"),
        "bio": profile.get("bio"),
        "skills": profile.get("skills", []),
        "parish": profile.get("parish"),
        "average_rating": profile.get("average_rating"),
        "total_reviews": profile.get("total_reviews"),
    }

    if profile.get("latitude") and profile.get("longitude"):
        doc["location"] = {"lat": profile["latitude"], "lon": profile["longitude"]}

    await client.index(index=PROFILES_INDEX, id=profile["id"], document=doc)


async def search_listings(
    query: str,
    parish: str | None = None,
    category: str | None = None,
    listing_type: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 25.0,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Full-text search across listings with geo and facet filtering."""
    client = await get_client()
    if not client:
        return {"hits": [], "total": 0, "source": "unavailable"}

    must = []
    filter_clauses = []

    if query:
        must.append({
            "multi_match": {
                "query": query,
                "fields": ["title^3", "description", "skills^2"],
                "fuzziness": "AUTO",
            }
        })

    filter_clauses.append({"term": {"status": "active"}})

    if parish:
        filter_clauses.append({"term": {"parish": parish}})
    if category:
        filter_clauses.append({"term": {"category": category}})
    if listing_type:
        filter_clauses.append({"term": {"listing_type": listing_type}})

    if lat is not None and lon is not None:
        filter_clauses.append({
            "geo_distance": {
                "distance": f"{radius_km}km",
                "location": {"lat": lat, "lon": lon},
            }
        })

    body: dict[str, Any] = {
        "query": {
            "bool": {
                "must": must or [{"match_all": {}}],
                "filter": filter_clauses,
            }
        },
        "from": offset,
        "size": limit,
        "sort": [{"_score": "desc"}, {"created_at": "desc"}],
    }

    # Add distance sort if geo query
    if lat is not None and lon is not None:
        body["sort"].insert(0, {
            "_geo_distance": {
                "location": {"lat": lat, "lon": lon},
                "order": "asc",
                "unit": "km",
            }
        })

    result = await client.search(index=LISTINGS_INDEX, body=body)

    hits = [
        {**hit["_source"], "_score": hit["_score"]}
        for hit in result["hits"]["hits"]
    ]

    return {
        "hits": hits,
        "total": result["hits"]["total"]["value"],
        "source": "elasticsearch",
    }


async def search_profiles(
    query: str,
    parish: str | None = None,
    skills: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Full-text search across user profiles."""
    client = await get_client()
    if not client:
        return {"hits": [], "total": 0, "source": "unavailable"}

    must = []
    filter_clauses = []

    if query:
        must.append({
            "multi_match": {
                "query": query,
                "fields": ["display_name^2", "bio", "skills^3"],
                "fuzziness": "AUTO",
            }
        })

    if parish:
        filter_clauses.append({"term": {"parish": parish}})
    if skills:
        for skill in skills:
            filter_clauses.append({"term": {"skills": skill}})

    body = {
        "query": {
            "bool": {
                "must": must or [{"match_all": {}}],
                "filter": filter_clauses,
            }
        },
        "from": offset,
        "size": limit,
        "sort": [
            {"_score": "desc"},
            {"average_rating": {"order": "desc", "missing": "_last"}},
        ],
    }

    result = await client.search(index=PROFILES_INDEX, body=body)

    hits = [
        {**hit["_source"], "_score": hit["_score"]}
        for hit in result["hits"]["hits"]
    ]

    return {
        "hits": hits,
        "total": result["hits"]["total"]["value"],
        "source": "elasticsearch",
    }


async def close_client() -> None:
    """Close the Elasticsearch client."""
    global _client
    if _client:
        await _client.close()
        _client = None
