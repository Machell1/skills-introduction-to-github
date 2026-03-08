"""S2 cell computation and geoshard utilities.

Uses s2sphere to map lat/lng coordinates to hierarchical S2 cells.
S2 cells partition the Earth's surface into a hierarchy of cells,
enabling efficient spatial indexing and neighbor queries.
"""

import math

import s2sphere

# S2 cell level 12 gives cells ~3.3km x 1.6km -- good for Jamaica's scale
DEFAULT_S2_LEVEL = 12

# Approximate km per degree at Jamaica's latitude (~18°N)
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LNG = 105.6  # cos(18°) * 111


def lat_lng_to_s2_cell_id(lat: float, lng: float, level: int = DEFAULT_S2_LEVEL) -> int:
    """Convert lat/lng to an S2 cell ID at the given level."""
    ll = s2sphere.LatLng.from_degrees(lat, lng)
    cell = s2sphere.CellId.from_lat_lng(ll).parent(level)
    return cell.id()


def get_s2_cell_token(lat: float, lng: float, level: int = DEFAULT_S2_LEVEL) -> str:
    """Get the S2 cell token string for a lat/lng."""
    ll = s2sphere.LatLng.from_degrees(lat, lng)
    cell = s2sphere.CellId.from_lat_lng(ll).parent(level)
    return cell.to_token()


def get_covering_cells(lat: float, lng: float, radius_km: float, level: int = DEFAULT_S2_LEVEL) -> list[int]:
    """Get all S2 cell IDs that cover a circle of radius_km around a point.

    This is the core of geosharding: instead of scanning all data,
    we only query cells that overlap with the search radius.
    """
    # Convert radius to degrees (approximate)
    radius_lat = radius_km / KM_PER_DEG_LAT
    radius_lng = radius_km / KM_PER_DEG_LNG

    # Create a region covering the search area
    center = s2sphere.LatLng.from_degrees(lat, lng)
    region = s2sphere.LatLngRect(
        s2sphere.LatLng.from_degrees(lat - radius_lat, lng - radius_lng),
        s2sphere.LatLng.from_degrees(lat + radius_lat, lng + radius_lng),
    )

    # Get covering cells
    coverer = s2sphere.RegionCoverer()
    coverer.min_level = level
    coverer.max_level = level
    coverer.max_cells = 50  # cap for performance

    covering = coverer.get_covering(region)
    return [cell.id() for cell in covering]


def get_neighbor_cells(cell_id: int, level: int = DEFAULT_S2_LEVEL) -> list[int]:
    """Get the immediate neighbor cell IDs for a given S2 cell."""
    cell = s2sphere.CellId(cell_id)
    neighbors = []
    for edge in range(4):
        neighbor_cells = cell.get_edge_neighbors()
        for n in neighbor_cells:
            if n.id() not in neighbors:
                neighbors.append(n.id())
    return neighbors


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
