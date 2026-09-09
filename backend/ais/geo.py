"""Small geodesy helpers shared by the AIS generator and correlation engine."""

import math
from datetime import datetime, timezone

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float):
    """Given a start point, bearing, and distance, return the destination lat/lon."""
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), (math.degrees(lambda2) + 540) % 360 - 180


def move_along_heading(lat: float, lon: float, heading_deg: float, signed_distance_km: float):
    """Move along a fixed compass heading by a signed distance (negative = reverse course)."""
    if signed_distance_km < 0:
        heading_deg = (heading_deg + 180) % 360
        signed_distance_km = -signed_distance_km
    return destination_point(lat, lon, heading_deg, signed_distance_km)


def parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp (with or without a trailing 'Z') as UTC."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
