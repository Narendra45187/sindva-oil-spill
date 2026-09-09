"""
Oil-spill ORIGIN ESTIMATION (back-drift): a probability ZONE + a release
TIME WINDOW, not a single point/second.

Oil drifts after release, so the SAR-detected spill sits downstream of
where it was actually released. This module produces a rough, clearly
labeled ESTIMATE of that release location and time by back-tracking the
spill centroid against a simplified net wind+current drift vector -- not
for one assumed drift duration, but across a RANGE of plausible drift
durations (min / nominal / max), matching how real oil-spill hindcasting
reports a region and a time range rather than an exact point and second.

Standard simple oil-drift approximation used here:

    surface_drift_velocity ~= 3% of wind velocity + 100% of surface current velocity

(the "3% wind factor" is a widely used rule-of-thumb for how much of the
wind's push is transferred to a floating oil slick at the surface; the
ocean current is assumed to carry the slick at its own full speed.)

This is a first-order, single-vector model -- it ignores slick spreading,
Coriolis deflection (Ekman spiral), shoreline interaction, and evaporation/
weathering effects, and treats wind+current as constant over the whole
drift window. It exists to point response assets toward a plausible
upstream search AREA over a plausible release TIME RANGE, not to pinpoint
an exact release site or second. Every result this module returns must be
presented as an ESTIMATE, never a fact.

origin_confidence computed here is the SINGLE source of truth for how
confident the origin stage is -- fusion/evidence_fusion.py reads this same
number for its "Origin Reconstruction" stage rather than deriving its own.
"""

import math
from datetime import datetime, timedelta, timezone

EARTH_RADIUS_M = 6371008.8

WIND_DRIFT_FACTOR = 0.03  # ~3% of wind speed is transferred to surface drift
CURRENT_DRIFT_FACTOR = 1.0  # slick assumed to ride the surface current at its own speed

# Nominal assumed drift time (still the value the frontend's drift-time
# selector controls, and still what nominal_origin/origin_lat/origin_lon
# are placed at); min/max bracket it by drift_range_half_width_min on
# either side, forming the candidate range this module hindcasts across.
DEFAULT_DRIFT_MINUTES = 30.0
DRIFT_RANGE_HALF_WIDTH_MIN = 15.0
MIN_DRIFT_FLOOR_MIN = 5.0  # never let the near end of the range collapse below this

# origin_zone radius = a fixed minimum (an estimate is never a literal
# point) + half the min/max candidate spread + a weather-completeness term.
ZONE_MIN_RADIUS_KM = 0.15
ZONE_WEATHER_UNCERTAINTY_KM = 1.5

# origin_confidence: weather-completeness score, discounted by how much the
# min/max candidates disagree with each other (a wide spread means the
# drift-time assumption matters a lot -- itself a sign of more uncertainty).
CONF_WEATHER_BOTH = 0.85
CONF_WEATHER_ONE = 0.55
CONF_WEATHER_NONE = 0.20
CONF_SPREAD_DECAY_KM = 1.5
CONF_SPREAD_WEIGHT = 0.4  # how much a wide spread can further discount weather-completeness (0-40%)


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
    # Normalize longitude to [-180, 180].
    lon2_deg = (math.degrees(lon2) + 540) % 360 - 180
    return math.degrees(lat2), lon2_deg


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp (with or without a trailing 'Z') as UTC.
    Self-contained rather than imported from ais/geo.py -- see this
    backend's convention of each module owning its own small geodesy/time
    helpers (ais/geo.py, detection/cv_detect.py, origin/forecast_drift.py)."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _weather_completeness(weather: dict) -> tuple[bool, bool, float]:
    wind_present = weather.get("wind_speed_ms") is not None and weather.get("wind_direction") is not None
    current_present = weather.get("current_velocity_ms") is not None and weather.get("current_direction") is not None
    if wind_present and current_present:
        score = CONF_WEATHER_BOTH
    elif wind_present or current_present:
        score = CONF_WEATHER_ONE
    else:
        score = CONF_WEATHER_NONE
    return wind_present, current_present, score


def _release_window(scene_timestamp: str | None, min_drift_min: float, max_drift_min: float) -> dict | None:
    """The release happened somewhere between (detection time - max_drift)
    and (detection time - min_drift) -- the longer the assumed drift, the
    earlier the release; the shorter, the more recent. Both ends are
    necessarily before the detection time itself."""
    if not scene_timestamp:
        return None
    scene_dt = _parse_iso(scene_timestamp)
    start_dt = scene_dt - timedelta(minutes=max_drift_min)
    end_dt = scene_dt - timedelta(minutes=min_drift_min)

    if start_dt.date() == end_dt.date():
        display = f"{start_dt.strftime('%Y-%m-%d %H:%M')} – {end_dt.strftime('%H:%M')} UTC"
    else:
        display = f"{start_dt.strftime('%Y-%m-%d %H:%M')} – {end_dt.strftime('%Y-%m-%d %H:%M')} UTC"

    return {
        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "display": display,
    }


def estimate_origin(
    spill_centroid_latlon: dict | None,
    weather: dict | None,
    drift_minutes: float = DEFAULT_DRIFT_MINUTES,
    scene_timestamp: str | None = None,
    drift_range_half_width_min: float = DRIFT_RANGE_HALF_WIDTH_MIN,
) -> dict:
    """Back-track the spill centroid against the net wind+current drift to
    estimate an upstream release ZONE and TIME WINDOW.

    spill_centroid_latlon: {"lat": float, "lon": float}
    weather: {"wind_speed_ms", "wind_direction", "current_velocity_ms", "current_direction"}
        wind_direction is meteorological -- the direction the wind blows FROM.
        current_direction is oceanographic -- the direction the current flows TOWARDS.
        Either pair may be missing/None; a missing pair simply contributes
        nothing to the drift vector rather than failing.
    drift_minutes: the NOMINAL assumed elapsed time since release (still
        what nominal_origin is placed at, and still user-adjustable, e.g.
        via the frontend's drift-time selector). Purely an assumption.
    scene_timestamp: the scene's detection/pass time (ISO 8601), used to
        turn the drift-time range into an actual release_window. If not
        given, release_window is omitted (None) rather than guessed.
    drift_range_half_width_min: the candidate range brackets
        [drift_minutes - this, drift_minutes + this] (floored at
        MIN_DRIFT_FLOOR_MIN) -- at the default drift_minutes=30 and
        half-width=15, that's the min=15 / nominal=30 / max=45 example.

    Returns {"available": False, "message": ...} when there isn't a
    centroid to back-track from, or not enough wind/current data to compute
    any drift direction. Otherwise:
        {
            "available": True,
            # Backward-compatible fields (unchanged meaning/shape from the
            # single-point version -- always the NOMINAL candidate):
            "origin_lat", "origin_lon", "drift_distance_km",
            "drift_bearing_deg", "drift_minutes", "net_drift_speed_ms",
            "method_note",
            # New: zone, window, confidence, and the candidates behind them.
            "nominal_origin": {"lat", "lon"},
            "origin_zone": {"center_lat", "center_lon", "radius_km"},
            "release_window": {"start_time", "end_time", "display"} | None,
            "origin_confidence": float,  # 0-100 -- also what evidence
                                          # fusion's Origin Reconstruction
                                          # stage reads, unchanged
            "min_drift_minutes", "max_drift_minutes",
            "candidates": [{"label", "drift_minutes", "lat", "lon", "distance_km"}, ...],
        }
    """
    if not spill_centroid_latlon or spill_centroid_latlon.get("lat") is None or spill_centroid_latlon.get("lon") is None:
        return {"available": False, "message": "No spill centroid to back-track from -- run detection first."}

    weather = weather or {}
    wind_speed = weather.get("wind_speed_ms")
    wind_dir_from = weather.get("wind_direction")
    current_speed = weather.get("current_velocity_ms")
    current_dir_to = weather.get("current_direction")

    north = 0.0
    east = 0.0
    have_component = False

    if wind_speed is not None and wind_dir_from is not None:
        # Wind direction is reported as where it blows FROM; it pushes the
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
        return {
            "available": False,
            "message": "Wind and current data are both unavailable -- cannot estimate a drift direction.",
        }

    drift_bearing_deg, net_drift_speed_ms = _vector_to_bearing_speed(north, east)

    if net_drift_speed_ms <= 1e-6:
        return {
            "available": False,
            "message": "Wind and current are effectively calm -- no meaningful drift direction to back-track.",
        }

    min_drift_minutes = max(MIN_DRIFT_FLOOR_MIN, drift_minutes - drift_range_half_width_min)
    max_drift_minutes = drift_minutes + drift_range_half_width_min

    # Origin is UPSTREAM: walk backward from the spill, i.e. along the
    # reverse of the drift-TO bearing -- same reversed bearing for every
    # candidate, only the distance (via drift time) differs, so all
    # candidates fall on the same line back from the spill.
    origin_bearing_deg = (drift_bearing_deg + 180) % 360

    candidate_specs = [
        ("min", min_drift_minutes),
        ("nominal", drift_minutes),
        ("max", max_drift_minutes),
    ]
    candidates = []
    for label, dm in candidate_specs:
        distance_m = net_drift_speed_ms * (dm * 60.0)
        lat, lon = _destination_point(
            spill_centroid_latlon["lat"], spill_centroid_latlon["lon"], origin_bearing_deg, distance_m
        )
        candidates.append(
            {
                "label": label,
                "drift_minutes": round(dm, 1),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "distance_km": round(distance_m / 1000.0, 4),
            }
        )

    nominal = next(c for c in candidates if c["label"] == "nominal")
    near = next(c for c in candidates if c["label"] == "min")
    far = next(c for c in candidates if c["label"] == "max")

    # All candidates are collinear (same bearing, different distance), so
    # the spread between the nearest and farthest is exactly the
    # difference in their back-track distances -- no need for a second
    # haversine call.
    spread_km = far["distance_km"] - near["distance_km"]

    _, _, weather_score = _weather_completeness(weather)
    spread_score = math.exp(-spread_km / CONF_SPREAD_DECAY_KM)
    origin_confidence = round(
        min(100.0, max(0.0, weather_score * (1 - CONF_SPREAD_WEIGHT * (1 - spread_score)) * 100.0)), 1
    )

    radius_km = round(ZONE_MIN_RADIUS_KM + spread_km / 2.0 + (1 - weather_score) * ZONE_WEATHER_UNCERTAINTY_KM, 3)

    release_window = _release_window(scene_timestamp, min_drift_minutes, max_drift_minutes)

    return {
        "available": True,
        # Backward-compatible fields -- always the nominal candidate.
        "origin_lat": nominal["lat"],
        "origin_lon": nominal["lon"],
        "drift_distance_km": nominal["distance_km"],
        "drift_bearing_deg": round(drift_bearing_deg, 1),
        "drift_minutes": drift_minutes,
        "net_drift_speed_ms": round(net_drift_speed_ms, 4),
        "method_note": (
            f"Estimated via wind (3% factor) + surface-current back-drift across a "
            f"{min_drift_minutes:g}-{max_drift_minutes:g} min assumed range (nominal "
            f"{drift_minutes:g} min); simplified single-vector model -- ignores slick "
            f"spreading, Coriolis deflection, and shoreline effects. Origin is a "
            f"probability zone with a release time window, not an exact point or second."
        ),
        # New: zone, window, confidence, candidates.
        "nominal_origin": {"lat": nominal["lat"], "lon": nominal["lon"]},
        "origin_zone": {
            "center_lat": nominal["lat"],
            "center_lon": nominal["lon"],
            "radius_km": radius_km,
        },
        "release_window": release_window,
        "origin_confidence": origin_confidence,
        "min_drift_minutes": round(min_drift_minutes, 1),
        "max_drift_minutes": round(max_drift_minutes, 1),
        "candidates": candidates,
    }
