"""
Oil-spill DRIFT FORECAST (forward projection).

The forward counterpart to origin/estimate_origin.py's back-drift: instead
of tracking backward from the spill to estimate where it came from, this
module projects FORWARD from the current spill centroid to predict where
it is headed over the next few hours, using the exact same simple
wind+current surface-drift model.

Standard simple oil-drift approximation used here (identical to
origin/estimate_origin.py's):

    surface_drift_velocity ~= 3% of wind velocity + 100% of surface current velocity

This file intentionally does NOT import from origin/estimate_origin.py --
each module in this backend owns its own self-contained geodesy (see
ais/geo.py, detection/cv_detect.py, origin/estimate_origin.py), so this
duplicates the same small vector-combination and destination-point math
rather than reaching into a sibling module's internals or risking a change
to it. The formulas are identical by design; only the direction of travel
differs (forward here, reversed 180° there for the backward origin point).

Every prediction from this module is an ESTIMATE with GROWING uncertainty
over time -- never presented as a certain future position.
"""

import math

EARTH_RADIUS_M = 6371008.8

WIND_DRIFT_FACTOR = 0.03  # ~3% of wind speed is transferred to surface drift
CURRENT_DRIFT_FACTOR = 1.0  # slick assumed to ride the surface current at its own speed

DEFAULT_HORIZON_HOURS = 6.0
DEFAULT_STEP_MINUTES = 30.0
MAX_HORIZON_HOURS = 24.0
MIN_STEP_MINUTES = 5.0

# Uncertainty growth: a simple, documented linear model -- the predicted
# radius grows with lead time, plus a small fixed base so even the very
# first step isn't presented as an exact point.
UNCERTAINTY_BASE_KM = 0.05
UNCERTAINTY_GROWTH_KM_PER_HOUR = 0.15


def _to_vector(speed: float, bearing_to_deg: float) -> tuple[float, float]:
    """speed + compass bearing (deg, 0=N, clockwise, direction the vector
    POINTS TO) -> (north_component, east_component), same units as speed."""
    theta = math.radians(bearing_to_deg)
    return speed * math.cos(theta), speed * math.sin(theta)


def _vector_to_bearing_speed(north: float, east: float) -> tuple[float, float]:
    speed = math.hypot(north, east)
    bearing = math.degrees(math.atan2(east, north)) % 360
    return bearing, speed


def _destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Geodesic destination point (spherical-earth formula), given a start
    point, a bearing (deg, 0=N clockwise), and a distance (m)."""
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    lon2_deg = (math.degrees(lon2) + 540) % 360 - 180
    return math.degrees(lat2), lon2_deg


def _net_drift_vector(weather: dict) -> tuple[float, float, bool]:
    """Combines wind + current into one net drift vector, same as
    origin/estimate_origin.py. Returns (drift_bearing_deg, net_drift_speed_ms,
    have_component) -- drift_bearing_deg is the direction the slick is
    drifting TOWARDS (downstream)."""
    wind_speed = weather.get("wind_speed_ms")
    wind_dir_from = weather.get("wind_direction")
    current_speed = weather.get("current_velocity_ms")
    current_dir_to = weather.get("current_direction")

    north = 0.0
    east = 0.0
    have_component = False

    if wind_speed is not None and wind_dir_from is not None:
        # Wind is reported as the direction it blows FROM; it pushes the
        # slick the opposite way (TOWARD wind_dir_from + 180).
        wind_dir_to = (wind_dir_from + 180) % 360
        n, e = _to_vector(WIND_DRIFT_FACTOR * wind_speed, wind_dir_to)
        north += n
        east += e
        have_component = True

    if current_speed is not None and current_dir_to is not None:
        # Ocean current direction is already the direction the water is
        # flowing TOWARDS.
        n, e = _to_vector(CURRENT_DRIFT_FACTOR * current_speed, current_dir_to)
        north += n
        east += e
        have_component = True

    if not have_component:
        return 0.0, 0.0, False

    bearing, speed = _vector_to_bearing_speed(north, east)
    return bearing, speed, True


def forecast_drift(
    spill_centroid_latlon: dict | None,
    weather: dict | None,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    step_minutes: float = DEFAULT_STEP_MINUTES,
) -> dict:
    """Project the spill's position FORWARD along the net wind+current
    drift vector, from now out to `horizon_hours` from now.

    spill_centroid_latlon: {"lat": float, "lon": float}
    weather: {"wind_speed_ms", "wind_direction", "current_velocity_ms", "current_direction"}
        (same convention as origin/estimate_origin.py -- wind_direction is
        meteorological "blows FROM"; current_direction is oceanographic
        "flows TOWARDS")
    horizon_hours: how far ahead to project, clamped to (0, MAX_HORIZON_HOURS].
    step_minutes: spacing between predicted points, clamped to
        [MIN_STEP_MINUTES, horizon in minutes].

    Returns {"available": False, "message": ...} when there isn't a
    centroid, or not enough wind/current data to compute any drift
    direction. Otherwise:
        {
            "available": True,
            "horizon_hours", "step_minutes",
            "drift_bearing_deg",       # direction of travel (downstream)
            "net_drift_speed_ms",
            "total_displacement_km",   # straight-line distance at the horizon
            "points": [{"t_offset_min", "lat", "lon", "uncertainty_km"}, ...],
            "method_note",
        }
    """
    if not spill_centroid_latlon or spill_centroid_latlon.get("lat") is None or spill_centroid_latlon.get("lon") is None:
        return {"available": False, "message": "No spill centroid to forecast from -- run detection first."}

    weather = weather or {}
    drift_bearing_deg, net_drift_speed_ms, have_component = _net_drift_vector(weather)

    if not have_component:
        return {
            "available": False,
            "message": "Wind and current data are both unavailable -- cannot forecast a drift direction.",
        }

    if net_drift_speed_ms <= 1e-6:
        return {
            "available": False,
            "message": "Wind and current are effectively calm -- no meaningful drift direction to forecast.",
        }

    horizon_hours = max(0.5, min(horizon_hours, MAX_HORIZON_HOURS))
    total_minutes = horizon_hours * 60.0
    step_minutes = max(MIN_STEP_MINUTES, min(step_minutes, total_minutes))

    lat0, lon0 = spill_centroid_latlon["lat"], spill_centroid_latlon["lon"]

    n_steps = int(total_minutes // step_minutes)
    offsets = [i * step_minutes for i in range(n_steps + 1)]
    if offsets[-1] < total_minutes - 1e-6:
        offsets.append(total_minutes)

    points = []
    for t in offsets:
        distance_m = net_drift_speed_ms * (t * 60.0)
        if distance_m > 0:
            lat, lon = _destination_point(lat0, lon0, drift_bearing_deg, distance_m)
        else:
            lat, lon = lat0, lon0
        uncertainty_km = round(UNCERTAINTY_BASE_KM + UNCERTAINTY_GROWTH_KM_PER_HOUR * (t / 60.0), 3)
        points.append(
            {
                "t_offset_min": round(t, 1),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "uncertainty_km": uncertainty_km,
            }
        )

    total_distance_m = net_drift_speed_ms * (total_minutes * 60.0)

    return {
        "available": True,
        "horizon_hours": horizon_hours,
        "step_minutes": step_minutes,
        "drift_bearing_deg": round(drift_bearing_deg, 1),
        "net_drift_speed_ms": round(net_drift_speed_ms, 4),
        "total_displacement_km": round(total_distance_m / 1000.0, 4),
        "points": points,
        "method_note": (
            f"Forecast via wind (3% factor) + surface-current forward projection over "
            f"{horizon_hours:g} h; simplified single-vector model -- ignores slick spreading, "
            f"Coriolis deflection, and shoreline effects. Uncertainty grows with lead time; "
            f"treat as an approximate downstream search area, not exact future positions."
        ),
    }
