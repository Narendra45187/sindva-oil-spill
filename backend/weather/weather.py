"""
Weather & ocean conditions for a spill location, via the free Open-Meteo
APIs (no API key required) -- with a three-tier fallback so this module
NEVER hands back a blank value when a usable one exists anywhere:

    Tier 1 LIVE    -- the live API call succeeded just now.
    Tier 2 CACHED  -- the live call failed/timed out; fall back to the
                      last successful live read, persisted in
                      backend/data/weather_cache.json.
    Tier 3 DEFAULT -- no live data AND no cache exists yet; fall back to
                      hardcoded, realistic typical values for the
                      Visakhapatnam / Bay of Bengal region.

Two independent API calls, each falling back through the same three tiers
on its OWN (so a live main-forecast read can sit alongside a cached-marine
read in the same response, "partial live"):
  - Forecast API: wind speed/direction, air temperature, surface pressure.
  - Marine API: wave height, ocean current speed/direction. Marine data
    only exists over open water -- a request for an inland point (or one
    the marine model simply doesn't cover) returns no "current" block,
    which is treated the same as a network failure for fallback purposes.

Every response carries `source` ("live" | "cached" | "default" -- the
WEAKEST tier actually used by either group) and `fetched_at` (the time the
tier's data actually came from -- the original live read for "cached",
"now" for "live"/"default"). The frontend is expected to show this
honestly; this module's job stops at reporting it accurately.

Display-only: this module has no opinion about what the numbers mean for
detection or classification -- cv_detect.py's wind-adjustment, and the
origin/forecast drift models, simply consume whatever value comes back,
live or not, per this module's docstring above.
"""

import json
import os
from datetime import datetime, timezone

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

REQUEST_TIMEOUT_S = 5

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(BASE_DIR, "data", "weather_cache.json")

EMPTY_CONDITIONS = {
    "wind_speed_ms": None,
    "wind_direction": None,
    "wave_height_m": None,
    "current_velocity_ms": None,
    "current_direction": None,
    "temperature_c": None,
    "surface_pressure_hpa": None,
}

FORECAST_FIELDS = ("wind_speed_ms", "wind_direction", "temperature_c", "surface_pressure_hpa")
MARINE_FIELDS = ("wave_height_m", "current_velocity_ms", "current_direction")

# Tier 3 -- realistic typical conditions for the Visakhapatnam / Bay of
# Bengal region (not measured, not live -- a plausible regional backstop
# only, always labeled "default" wherever it's used).
REGIONAL_DEFAULTS = {
    "wind_speed_ms": 4.0,
    "wind_direction": 225.0,  # blowing FROM the SW, a common fair-weather pattern here
    "wave_height_m": 1.0,
    "current_velocity_ms": 0.2,
    "current_direction": 45.0,  # flowing TOWARDS the NE -- a rough regional typical, not a measurement
    "temperature_c": 29.0,
    "surface_pressure_hpa": 1008.0,
}


def _get_json(url: str, params: dict):
    """GET one Open-Meteo endpoint. Returns (json_dict, note) -- note is None
    on success, or a short human-readable reason on failure. Never raises:
    network errors, timeouts, and bad JSON are all reported, not thrown.
    """
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.Timeout:
        return None, "request timed out"
    except requests.exceptions.RequestException as exc:
        return None, f"request failed ({exc.__class__.__name__})"
    except ValueError:
        return None, "invalid response"


def _fetch_current(url: str, lat: float, lon: float, fields: str):
    """GET one Open-Meteo endpoint's "current" block. Returns (dict, note) --
    note is None on success, or a short human-readable reason on failure.
    Missing "current" blocks (e.g. marine data over land) are reported as
    unavailable, same as a network failure -- never raises either way.
    """
    payload, note = _get_json(
        url,
        {
            "latitude": lat,
            "longitude": lon,
            "current": fields,
            # Open-Meteo defaults wind/current speed to km/h; ask for
            # m/s directly so it matches this module's field names.
            "wind_speed_unit": "ms",
        },
    )
    if payload is None:
        return None, note

    current = payload.get("current")
    if not current:
        return None, "no data for this location"
    return current, None


def _fetch_hourly(url: str, lat: float, lon: float, fields: str, forecast_hours: int):
    """GET one Open-Meteo endpoint's "hourly" arrays, trimmed to the next
    `forecast_hours` hours from now. Returns (dict, note), same contract as
    _fetch_current."""
    payload, note = _get_json(
        url,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": fields,
            "forecast_hours": forecast_hours,
            "wind_speed_unit": "ms",
        },
    )
    if payload is None:
        return None, note

    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        return None, "no data for this location"
    return hourly, None


def _load_cache() -> dict | None:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "conditions" not in data:
            return None
        return data
    except (ValueError, OSError):
        return None


def _save_cache_fields(fields: dict) -> None:
    """Merge newly-live field values into the cache file, leaving any
    other previously-cached fields (e.g. from the other API group) intact.
    Best-effort only -- a write failure here must never break the response
    that triggered it."""
    try:
        existing = _load_cache() or {"conditions": dict(EMPTY_CONDITIONS)}
        existing["conditions"].update(fields)
        existing["cached_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(existing, f)
    except OSError:
        pass


def _fill_group(conditions: dict, field_names: tuple, cache: dict | None, group_label: str, notes: list) -> str:
    """Fills `field_names` into `conditions` from whichever tier already
    holds a value for them (this is called AFTER a live attempt has
    already populated any it could) and returns which tier ended up
    supplying them: "live", "cached", or "default"."""
    if all(conditions.get(f) is not None for f in field_names):
        return "live"

    cached_conditions = cache.get("conditions") if cache else None
    if cached_conditions and any(cached_conditions.get(f) is not None for f in field_names):
        for f in field_names:
            if conditions.get(f) is None:
                conditions[f] = cached_conditions.get(f)
        notes.append(f"{group_label} data unavailable live — showing cached values from {cache.get('cached_at', 'an earlier fetch')}")
        return "cached"

    for f in field_names:
        if conditions.get(f) is None:
            conditions[f] = REGIONAL_DEFAULTS[f]
    notes.append(f"{group_label} data unavailable live and no cache exists — showing regional default values")
    return "default"


def get_conditions(lat: float, lon: float) -> dict:
    """Wind/wave/current/temperature/pressure for (lat, lon), with the
    three-tier LIVE -> CACHED -> DEFAULT fallback described in this
    module's docstring.

    Always returns every field populated with a usable number -- this
    function does not return blanks/None for these fields as long as
    either a live read, a cache file, or the regional defaults can supply
    one (which is always, since the regional defaults cover every field).
    `notes` explains anything that degraded; `source` is the single
    honest summary of how trustworthy the response is as a whole.
    """
    conditions = dict(EMPTY_CONDITIONS)
    notes: list[str] = []

    forecast, forecast_note = _fetch_current(
        FORECAST_URL, lat, lon, "wind_speed_10m,wind_direction_10m,temperature_2m,surface_pressure"
    )
    if forecast and not all(forecast.get(k) is None for k in ("wind_speed_10m", "wind_direction_10m", "temperature_2m", "surface_pressure")):
        conditions["wind_speed_ms"] = forecast.get("wind_speed_10m")
        conditions["wind_direction"] = forecast.get("wind_direction_10m")
        conditions["temperature_c"] = forecast.get("temperature_2m")
        conditions["surface_pressure_hpa"] = forecast.get("surface_pressure")
    else:
        notes.append(f"forecast data unavailable ({forecast_note or 'no values for this location'})")

    marine, marine_note = _fetch_current(
        MARINE_URL, lat, lon, "wave_height,ocean_current_velocity,ocean_current_direction"
    )
    if marine and not all(marine.get(k) is None for k in ("wave_height", "ocean_current_velocity", "ocean_current_direction")):
        conditions["wave_height_m"] = marine.get("wave_height")
        conditions["current_velocity_ms"] = marine.get("ocean_current_velocity")
        conditions["current_direction"] = marine.get("ocean_current_direction")
    else:
        notes.append(f"marine data unavailable ({marine_note or 'no values for this location'})")

    # Snapshot the cache's own timestamp BEFORE this call might update it
    # below -- otherwise a partial-live response (e.g. forecast live,
    # marine cached) would overwrite cached_at with "now" from the live
    # group's save, and the marine group's genuinely-older cached_at would
    # be lost.
    cache = _load_cache()
    cache_snapshot_at = cache.get("cached_at") if cache else None

    forecast_tier = _fill_group(conditions, FORECAST_FIELDS, cache, "forecast", notes)
    marine_tier = _fill_group(conditions, MARINE_FIELDS, cache, "marine", notes)

    # Persist whichever fields came from a live read just now -- merged
    # into the cache so a later outage falls back to the freshest data
    # this module has actually seen, one API group at a time.
    if forecast_tier == "live":
        _save_cache_fields({f: conditions[f] for f in FORECAST_FIELDS})
    if marine_tier == "live":
        _save_cache_fields({f: conditions[f] for f in MARINE_FIELDS})

    tier_rank = {"live": 0, "cached": 1, "default": 2}
    source = max((forecast_tier, marine_tier), key=lambda t: tier_rank[t])

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # The honest "as of" time for a cached response is the original live
    # read behind the cache, not now.
    fetched_at = cache_snapshot_at if source == "cached" and cache_snapshot_at else now_iso

    conditions["source"] = source
    conditions["fetched_at"] = fetched_at
    conditions["notes"] = notes
    return conditions


def get_forecast(lat: float, lon: float, hours: int = 24) -> dict:
    """Hourly wind-speed (and wave-height, where the marine model covers the
    point) forecast for the next `hours` hours.

    Returns { "hours": [{time, wind_speed_ms, wave_height_m}, ...], "notes": [...] }.
    The two source APIs are fetched independently and joined by timestamp
    (not by list position) so a gap in either series still lines up
    correctly rather than silently shifting; a location with no wave data
    still returns the wind-only rows with wave_height_m = null per hour.
    """
    notes: list[str] = []

    wind_hourly, wind_note = _fetch_hourly(FORECAST_URL, lat, lon, "wind_speed_10m", hours)
    wind_by_time = dict(zip(wind_hourly["time"], wind_hourly["wind_speed_10m"])) if wind_hourly else {}
    if not wind_hourly:
        notes.append(f"forecast data unavailable ({wind_note})")

    wave_hourly, wave_note = _fetch_hourly(MARINE_URL, lat, lon, "wave_height", hours)
    wave_by_time = dict(zip(wave_hourly["time"], wave_hourly["wave_height"])) if wave_hourly else {}
    if not wave_hourly:
        notes.append(f"marine forecast unavailable ({wave_note})")

    times = list(wind_by_time.keys()) or list(wave_by_time.keys())
    rows = [
        {
            "time": t,
            "wind_speed_ms": wind_by_time.get(t),
            "wave_height_m": wave_by_time.get(t),
        }
        for t in times
    ]

    return {"hours": rows, "notes": notes}
