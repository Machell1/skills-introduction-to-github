"""Search service API routes -- full-text search for listings and profiles."""

from fastapi import APIRouter, Query, Request

from app.elasticsearch_client import search_listings, search_profiles

router = APIRouter(tags=["search"])


@router.get("/listings")
async def search_listings_endpoint(
    request: Request,
    q: str = Query(default="", description="Search query"),
    parish: str | None = None,
    category: str | None = None,
    listing_type: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = Query(default=25.0, le=100.0),
    limit: int = Query(default=20, le=100),
    offset: int = 0,
):
    """Search service listings with full-text, geo, and facet filtering.

    Supports:
    - Full-text search across title, description, skills (with fuzzy matching)
    - Parish and category facet filtering
    - Geo-distance filtering by lat/lon + radius
    - Listing type filtering (offer/request)
    """
    return await search_listings(
        query=q,
        parish=parish,
        category=category,
        listing_type=listing_type,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=limit,
        offset=offset,
    )


@router.get("/profiles")
async def search_profiles_endpoint(
    request: Request,
    q: str = Query(default="", description="Search query"),
    parish: str | None = None,
    skills: str | None = Query(default=None, description="Comma-separated skills"),
    limit: int = Query(default=20, le=100),
    offset: int = 0,
):
    """Search user profiles by skills, name, bio text, and parish.

    Skills are matched exactly; name and bio use fuzzy full-text search.
    Results are ranked by relevance score then average rating.
    """
    skill_list = [s.strip() for s in skills.split(",")] if skills else None
    return await search_profiles(
        query=q,
        parish=parish,
        skills=skill_list,
        limit=limit,
        offset=offset,
    )


@router.get("/suggest")
async def suggest(
    request: Request,
    q: str = Query(..., min_length=2, description="Autocomplete query"),
    type: str = Query(default="listings", pattern=r"^(listings|profiles)$"),
    limit: int = Query(default=5, le=10),
):
    """Autocomplete suggestions for the search bar."""
    if type == "listings":
        results = await search_listings(query=q, limit=limit)
    else:
        results = await search_profiles(query=q, limit=limit)

    suggestions = []
    for hit in results.get("hits", []):
        if type == "listings":
            suggestions.append({
                "id": hit.get("id"),
                "text": hit.get("title"),
                "category": hit.get("category"),
            })
        else:
            suggestions.append({
                "id": hit.get("id"),
                "text": hit.get("display_name"),
                "skills": hit.get("skills", [])[:3],
            })

    return {"suggestions": suggestions, "query": q}
