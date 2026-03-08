"""Geoshard Indexer API routes -- spatial queries for nearby entities."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db

from app.models import GeoshardEntry
from app.s2_utils import get_covering_cells, haversine_km

router = APIRouter(tags=["geo"])


@router.get("/nearby")
async def find_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=25.0, ge=0.5, le=200),
    entity_type: str | None = Query(default=None, pattern=r"^(profile|listing)$"),
    category: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Find entities near a location using S2 cell covering.

    Instead of scanning every record, we compute which S2 cells
    overlap the search radius and only query those cells -- this is
    the geosharding optimization.
    """
    # Get S2 cells that cover the search area
    covering_cell_ids = get_covering_cells(lat, lng, radius_km)

    # Query only entries in those cells
    query = select(GeoshardEntry).where(
        GeoshardEntry.s2_cell_id.in_(covering_cell_ids),
        GeoshardEntry.is_active == "true",
    )
    if entity_type:
        query = query.where(GeoshardEntry.entity_type == entity_type)

    result = await db.execute(query)
    entries = result.scalars().all()

    # Post-filter by exact distance (S2 covering is an approximation)
    nearby = []
    for entry in entries:
        dist = haversine_km(lat, lng, float(entry.latitude), float(entry.longitude))
        if dist <= radius_km:
            nearby.append({
                "entity_id": entry.entity_id,
                "entity_type": entry.entity_type,
                "parish": entry.parish,
                "distance_km": round(dist, 2),
                "latitude": float(entry.latitude),
                "longitude": float(entry.longitude),
            })

    # Sort by distance and apply limit
    nearby.sort(key=lambda x: x["distance_km"])
    return nearby[:limit]


@router.get("/parish/{parish_name}")
async def find_by_parish(
    parish_name: str,
    entity_type: str | None = Query(default=None, pattern=r"^(profile|listing)$"),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Find all entities in a specific Jamaican parish."""
    query = select(GeoshardEntry).where(
        GeoshardEntry.parish == parish_name,
        GeoshardEntry.is_active == "true",
    )
    if entity_type:
        query = query.where(GeoshardEntry.entity_type == entity_type)
    query = query.limit(limit)

    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        {
            "entity_id": e.entity_id,
            "entity_type": e.entity_type,
            "parish": e.parish,
            "latitude": float(e.latitude),
            "longitude": float(e.longitude),
        }
        for e in entries
    ]


@router.get("/stats")
async def geoshard_stats(db: AsyncSession = Depends(get_db)):
    """Get distribution statistics of entities across parishes."""
    from sqlalchemy import func

    result = await db.execute(
        select(
            GeoshardEntry.parish,
            GeoshardEntry.entity_type,
            func.count().label("count"),
        )
        .where(GeoshardEntry.is_active == "true")
        .group_by(GeoshardEntry.parish, GeoshardEntry.entity_type)
        .order_by(GeoshardEntry.parish)
    )
    rows = result.all()

    stats = {}
    for parish, entity_type, count in rows:
        if parish not in stats:
            stats[parish] = {"profiles": 0, "listings": 0}
        stats[parish][f"{entity_type}s"] = count

    return {"parishes": stats, "total_entries": sum(r[2] for r in rows)}
