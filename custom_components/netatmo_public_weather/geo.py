"""Small geometry helpers (no Home Assistant imports)."""

from __future__ import annotations

import math
from typing import NamedTuple

EARTH_RADIUS_KM = 6371.0
KM_PER_DEG_LAT = 111.2


class BBox(NamedTuple):
    """A latitude/longitude bounding box as Netatmo expects it."""

    lat_ne: float
    lon_ne: float
    lat_sw: float
    lon_sw: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _deg_lon(lat: float, km: float) -> float:
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    return km / (KM_PER_DEG_LAT * cos_lat)


def bbox_from_radius(lat: float, lon: float, radius_km: float) -> BBox:
    """Return the box enclosing a circle of radius_km around a point."""
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = _deg_lon(lat, radius_km)
    return BBox(lat + dlat, lon + dlon, lat - dlat, lon - dlon)


def bbox_around(points: list[tuple[float, float]], margin_km: float = 0.3) -> BBox:
    """Return the smallest box containing all points, plus a margin."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    dlat = margin_km / KM_PER_DEG_LAT
    dlon = _deg_lon(max(abs(x) for x in lats), margin_km)
    return BBox(max(lats) + dlat, max(lons) + dlon, min(lats) - dlat, min(lons) - dlon)
