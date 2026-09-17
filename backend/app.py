import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ais.correlate import correlate as run_correlation
from ais.correlate import load_tracks as load_ais_tracks
from ais.investigate import investigate as run_investigation
from detection import cv_detect
from detection.cv_detect import HIGH_WIND_THRESHOLD_MS
from fusion.evidence_fusion import fuse_evidence
from origin.estimate_origin import DEFAULT_DRIFT_MINUTES, estimate_origin
from origin.forecast_drift import DEFAULT_HORIZON_HOURS, forecast_drift
from weather.weather import get_conditions, get_forecast

# ml_detect imports torch, which on some machines (this one, currently)
# gets blocked at DLL-load time by Windows Smart App Control -- the same
# class of issue this project already hit with rasterio (see
# requirements.txt's comment on the pinned version). That's an OS security
# policy blocking an unrecognized-reputation DLL, not a bug in ml_detect.py
# itself (it has run real inference successfully on this same machine
# before). Importing it defensively means a torch load failure only takes
# down /api/detect_ml -- every other endpoint (classic-CV detection, AIS,
# weather, origin, forecast, fusion, ...) has zero dependency on torch and
# must keep working regardless.
try:
    from detection import ml_detect

    ML_DETECT_IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 -- deliberately broad: any import-time
    # failure here (DLL block, missing weights file, etc.) must degrade to
    # "/api/detect_ml unavailable", never crash the whole app.
    ml_detect = None
    ML_DETECT_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "data", "images")
OUTPUTS_DIR = os.path.join(BASE_DIR, "data", "outputs")
AIS_DIR = os.path.join(BASE_DIR, "data", "ais")
INCIDENTS_DIR = os.path.join(BASE_DIR, "data", "incidents")
# Default scene for the "Analyze Visakhapatnam Scene" button: the synthetic
# open-water demo scene (see backend/make_synthetic.py), whose spill sits out
# in the bay where a vessel track can realistically pass through it -- unlike
# the real Sentinel-1 scene's coastline spill, which no AIS track can
# genuinely intersect. Upload a real GeoTIFF (e.g. vizag.tiff) via the
# dashboard's "Upload SAR GeoTIFF" control to analyze that instead.
DEFAULT_IMAGE = os.path.join(IMAGES_DIR, "vizag_synthetic.tiff")
AIS_CSV_PATH = os.path.join(AIS_DIR, "ais_vizag.csv")
SPILL_METADATA_PATH = os.path.join(OUTPUTS_DIR, "spill_metadata.json")
LATEST_CORRELATION_PATH = os.path.join(OUTPUTS_DIR, "latest_correlation.json")
LATEST_WEATHER_PATH = os.path.join(OUTPUTS_DIR, "latest_weather.json")
INCIDENTS_PATH = os.path.join(INCIDENTS_DIR, "incidents.json")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(AIS_DIR, exist_ok=True)
os.makedirs(INCIDENTS_DIR, exist_ok=True)

ALLOWED_INCIDENT_STATUSES = ("New", "Reviewed", "Under Investigation")

SCENE = {
    "name": "Visakhapatnam Port, Bay of Bengal",
    "sensor": "Sentinel-1 IW GRD (VV)",
    "timestamp": "2026-09-05T00:21:39Z",
    "center": {"lat": 17.68, "lon": 83.33},
}

app = FastAPI(title="SINDVA Marine Watch — Detection Service")

# Deployment note: the frontend isn't on a fixed domain yet (local dev on
# localhost:3000, plus a future Netlify deploy), and this API carries no
# cookies/session auth for any request -- so the simplest correct config
# for the prototype is to allow every origin. Wildcard "*" and
# allow_credentials=True are mutually exclusive per the CORS spec (browsers
# reject that combination outright); since nothing here relies on
# credentialed requests, allow_credentials stays False rather than pinning
# this to a single origin. Tighten to an explicit origin list once the
# Netlify domain is known, if that matters later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/detect")
async def detect(file: UploadFile | None = File(default=None)):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    tmp_path = None
    if file is not None:
        suffix = os.path.splitext(file.filename or "")[1] or ".tiff"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=IMAGES_DIR)
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
        image_path = tmp_path
    else:
        if not os.path.exists(DEFAULT_IMAGE):
            raise HTTPException(
                status_code=404,
                detail=(
                    "Default scene not found. Generate it with "
                    "`py -3.12 backend/make_synthetic.py`, or upload a GeoTIFF."
                ),
            )
        image_path = DEFAULT_IMAGE

    try:
        result = cv_detect.run(image_path, OUTPUTS_DIR, timestamp)
        bounds = cv_detect.image_bounds(image_path)
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)

    meta = {
        "detected": result["detected"],
        "centroid": result["centroid"],
        "area_km2": result["area_km2"],
        "region_count": result["region_count"],
        "regions": result["regions"],
        "timestamp": timestamp,
        # Additive field, does not change this endpoint's existing shape:
        # lets the frontend label which detector produced a result, now
        # that /api/detect_ml exists as an alternative.
        "detection_method": "Classic CV",
    }

    overlay_url = f"/outputs/{result['overlay_filename']}"
    mask_url = f"/outputs/{result['mask_filename']}"

    # Side effect only (does not change this endpoint's response shape):
    # persist the latest spill so /api/correlate and /api/report/latest have
    # something to read. scene_timestamp (the SAR pass-time) is what AIS
    # correlation measures "before/after" against -- not this wall-clock run
    # timestamp. overlay_url/mask_url are persisted here (in addition to
    # being returned below, unchanged) purely so the report endpoint can
    # find them later without re-running detection.
    with open(SPILL_METADATA_PATH, "w") as f:
        json.dump(
            {**meta, "scene_timestamp": SCENE["timestamp"], "overlay_url": overlay_url, "mask_url": mask_url},
            f,
        )
    # A fresh detection makes any prior correlation stale (it was measured
    # against the previous spill's centroid) -- clear it so the report
    # endpoint doesn't attribute a new spill to an old suspect list.
    if os.path.exists(LATEST_CORRELATION_PATH):
        os.remove(LATEST_CORRELATION_PATH)

    return {
        "meta": meta,
        "bounds": bounds,
        "scene": SCENE,
        "overlay_url": overlay_url,
        "mask_url": mask_url,
    }


@app.post("/api/detect_ml")
async def detect_ml_endpoint(file: UploadFile | None = File(default=None)):
    """AI/U-Net detection -- an ALTERNATIVE to /api/detect (Classic CV),
    which is completely untouched by this endpoint. Mirrors /api/detect's
    structure and response shape exactly (same meta fields plus
    detection_method, same side-effect persistence to SPILL_METADATA_PATH
    so /api/correlate and the rest of the pipeline work identically
    afterward, regardless of which detector produced the spill), just
    calling ml_detect.detect_ml() instead of cv_detect.run()."""
    if ml_detect is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI/U-Net detection is unavailable on this server: torch failed to load "
                f"({ML_DETECT_IMPORT_ERROR}). Classic-CV detection (/api/detect) is unaffected."
            ),
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    tmp_path = None
    if file is not None:
        suffix = os.path.splitext(file.filename or "")[1].lower() or ".tiff"
        if suffix not in ml_detect.ACCEPTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type '{suffix}' for AI detection -- "
                    f"accepts {', '.join(ml_detect.ACCEPTED_EXTENSIONS)}."
                ),
            )
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=IMAGES_DIR)
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
        image_path = tmp_path
    else:
        if not os.path.exists(DEFAULT_IMAGE):
            raise HTTPException(
                status_code=404,
                detail=(
                    "Default scene not found. Generate it with "
                    "`py -3.12 backend/make_synthetic.py`, or upload a GeoTIFF."
                ),
            )
        image_path = DEFAULT_IMAGE

    try:
        result = ml_detect.detect_ml(image_path, OUTPUTS_DIR, timestamp)
        # ml_detect's own bounds helper (not cv_detect's): falls back to a
        # synthetic Visakhapatnam-bay box instead of raising when the
        # upload (e.g. a plain PNG/JPG) has no real georeferencing.
        bounds = ml_detect.image_bounds(image_path)
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)

    meta = {
        "detected": result["detected"],
        "centroid": result["centroid"],
        "area_km2": result["area_km2"],
        "region_count": result["region_count"],
        "regions": result["regions"],
        "timestamp": timestamp,
        "detection_method": ml_detect.DETECTION_METHOD_ML,
    }

    overlay_url = f"/outputs/{result['overlay_filename']}"
    mask_url = f"/outputs/{result['mask_filename']}"

    with open(SPILL_METADATA_PATH, "w") as f:
        json.dump(
            {**meta, "scene_timestamp": SCENE["timestamp"], "overlay_url": overlay_url, "mask_url": mask_url},
            f,
        )
    if os.path.exists(LATEST_CORRELATION_PATH):
        os.remove(LATEST_CORRELATION_PATH)

    return {
        "meta": meta,
        "bounds": bounds,
        "scene": SCENE,
        "overlay_url": overlay_url,
        "mask_url": mask_url,
    }


@app.post("/api/correlate")
def correlate_endpoint():
    if not os.path.exists(SPILL_METADATA_PATH):
        raise HTTPException(status_code=400, detail="Run detection first.")

    with open(SPILL_METADATA_PATH, "r") as f:
        spill_metadata = json.load(f)

    if not spill_metadata.get("centroid"):
        raise HTTPException(status_code=400, detail="Run detection first.")

    if not os.path.exists(AIS_CSV_PATH):
        raise HTTPException(
            status_code=400,
            detail=(
                "AIS data not found. Generate it with "
                "`py -3.12 backend/ais/generate_ais.py` first."
            ),
        )

    suspects = run_correlation(spill_metadata, AIS_CSV_PATH)
    tracks = load_ais_tracks(AIS_CSV_PATH)

    # Side effect only (does not change this endpoint's response shape):
    # persist the latest ranking so /api/report/latest has something to
    # read. Tracks aren't needed for the report, so only suspects are kept.
    with open(LATEST_CORRELATION_PATH, "w") as f:
        json.dump({"suspects": suspects}, f)

    # Side effect only, and deliberately isolated: log this completed
    # detection+correlation to the incident history for the Alerts page.
    # Wrapped so a logging failure (disk full, bad permissions, whatever)
    # can never fail or slow down a correlation that otherwise succeeded.
    try:
        _log_incident(spill_metadata, {"suspects": suspects})
    except Exception:
        pass

    return {"suspects": suspects, "ais_tracks": tracks}


def _resolve_latlon(lat: float | None, lon: float | None) -> tuple[float, float]:
    # Default to the current spill centroid when lat/lon aren't given; fall
    # back to the scene's own center if no detection has been run yet
    # either, so weather endpoints stay usable (display-only, never error)
    # rather than requiring detection first the way /api/correlate does.
    if lat is None or lon is None:
        centroid = None
        if os.path.exists(SPILL_METADATA_PATH):
            with open(SPILL_METADATA_PATH, "r") as f:
                centroid = json.load(f).get("centroid")
        fallback = centroid or SCENE["center"]
        if lat is None:
            lat = fallback["lat"]
        if lon is None:
            lon = fallback["lon"]
    return lat, lon


@app.get("/api/weather")
def weather_endpoint(lat: float | None = None, lon: float | None = None):
    lat, lon = _resolve_latlon(lat, lon)
    conditions = get_conditions(lat, lon)

    # Side effect only (does not change this endpoint's response shape):
    # persist the latest reading so /api/report/latest has a weather
    # snapshot to include. The dashboard calls this endpoint automatically
    # right after each detection, so this naturally captures "the
    # conditions shown to the user for the latest spill."
    with open(LATEST_WEATHER_PATH, "w") as f:
        json.dump(conditions, f)

    return conditions


@app.get("/api/weather/forecast")
def weather_forecast_endpoint(lat: float | None = None, lon: float | None = None, hours: int = 24):
    lat, lon = _resolve_latlon(lat, lon)
    hours = max(1, min(hours, 48))
    return get_forecast(lat, lon, hours=hours)


@app.get("/api/origin")
def origin_endpoint(minutes: float = DEFAULT_DRIFT_MINUTES):
    """Back-track the latest spill centroid against the latest wind+current
    reading to estimate an upstream release ZONE and TIME WINDOW (not a
    single point/second -- see origin/estimate_origin.py). Display-only,
    additive: reads spill_metadata.json / latest_weather.json but never
    writes them, and never raises -- an unready or unavailable state comes
    back as {"available": False, "message": ...} for the frontend to show
    as-is."""
    not_ready = {"available": False, "message": "Run detection first."}

    if not os.path.exists(SPILL_METADATA_PATH):
        return not_ready

    with open(SPILL_METADATA_PATH, "r") as f:
        spill_metadata = json.load(f)

    centroid = spill_metadata.get("centroid")
    if not centroid:
        return not_ready

    weather = None
    if os.path.exists(LATEST_WEATHER_PATH):
        with open(LATEST_WEATHER_PATH, "r") as f:
            weather = json.load(f)

    drift_minutes = max(1.0, min(minutes, 720.0))
    return estimate_origin(centroid, weather, drift_minutes, spill_metadata.get("scene_timestamp"))


@app.get("/api/forecast")
def forecast_endpoint(hours: float = DEFAULT_HORIZON_HOURS):
    """Project the latest spill centroid FORWARD against the latest
    wind+current reading to predict its drift path over the next `hours`.
    The forward counterpart to /api/origin's backward hindcast -- entirely
    separate, does not read or write anything /api/origin touches beyond
    the same two read-only inputs. Display-only, additive: never writes
    spill_metadata.json / latest_weather.json, and never raises -- an
    unready or unavailable state comes back as
    {"available": False, "message": ...}."""
    not_ready = {"available": False, "message": "Run detection first."}

    if not os.path.exists(SPILL_METADATA_PATH):
        return not_ready

    with open(SPILL_METADATA_PATH, "r") as f:
        spill_metadata = json.load(f)

    centroid = spill_metadata.get("centroid")
    if not centroid:
        return not_ready

    weather = None
    if os.path.exists(LATEST_WEATHER_PATH):
        with open(LATEST_WEATHER_PATH, "r") as f:
            weather = json.load(f)

    return forecast_drift(centroid, weather, hours)


@app.get("/api/investigation")
def investigation_endpoint():
    """AIS behavioral case file for the current #1 suspect. Display-only,
    additive: reads spill_metadata.json / latest_correlation.json / the AIS
    CSV but never writes them, and never raises -- an unready state comes
    back as {"available": False, "message": ...}."""
    not_ready = {"available": False, "message": "Run detection and AIS correlation on the Dashboard first."}

    if not os.path.exists(SPILL_METADATA_PATH) or not os.path.exists(LATEST_CORRELATION_PATH):
        return not_ready

    with open(SPILL_METADATA_PATH, "r") as f:
        spill_metadata = json.load(f)
    with open(LATEST_CORRELATION_PATH, "r") as f:
        correlation = json.load(f)

    suspects = correlation.get("suspects") or []
    if not spill_metadata.get("centroid") or not suspects:
        return not_ready

    if not os.path.exists(AIS_CSV_PATH):
        return not_ready

    result = run_investigation(spill_metadata, suspects[0], AIS_CSV_PATH)

    # Endpoint-level composition only (not part of ais/investigate.py's own
    # analysis): the focused map needs the spill's own centroid/area to draw
    # alongside the vessel's track, so pass it through unchanged here.
    if result.get("available"):
        regions = spill_metadata.get("regions") or []
        primary = regions[0] if regions else None
        result = {
            **result,
            "spill": {
                "centroid": spill_metadata.get("centroid"),
                "area_km2": primary["area_km2"] if primary else None,
                "classification": primary["classification"] if primary else None,
            },
        }

    return result


@app.get("/api/fusion")
def fusion_endpoint():
    """Uncertainty-aware evidence fusion across the three pipeline stages
    (oil detection, origin reconstruction, vessel attribution/CCI).
    Display-only, additive: reads the same persisted results the other
    endpoints already read, and calls origin.estimate_origin.estimate_origin()
    exactly as /api/origin does -- never a second, different computation.
    Never raises -- an unready/partial state degrades gracefully (see
    fusion.evidence_fusion.fuse_evidence)."""
    detection_conf = None
    spill_metadata = None
    if os.path.exists(SPILL_METADATA_PATH):
        with open(SPILL_METADATA_PATH, "r") as f:
            spill_metadata = json.load(f)
        regions = spill_metadata.get("regions") or []
        if regions:
            detection_conf = regions[0].get("oil_confidence")

    weather = None
    if os.path.exists(LATEST_WEATHER_PATH):
        with open(LATEST_WEATHER_PATH, "r") as f:
            weather = json.load(f)

    origin_result = None
    if spill_metadata and spill_metadata.get("centroid"):
        origin_result = estimate_origin(
            spill_metadata["centroid"], weather, DEFAULT_DRIFT_MINUTES, spill_metadata.get("scene_timestamp")
        )

    attribution_cci = None
    if os.path.exists(LATEST_CORRELATION_PATH):
        with open(LATEST_CORRELATION_PATH, "r") as f:
            correlation = json.load(f)
        suspects = correlation.get("suspects") or []
        if suspects:
            attribution_cci = suspects[0].get("cci")

    return fuse_evidence(detection_conf, origin_result, attribution_cci)


def _severity_from_area(area_km2: float) -> str:
    # Mirrors frontend/lib/severity.ts's getSeverity() thresholds exactly,
    # so the report's severity always matches what the dashboard's map
    # chip shows for the same spill.
    if area_km2 <= 0:
        return "None"
    if area_km2 < 1:
        return "Minor"
    if area_km2 < 5:
        return "Moderate"
    return "Severe"


def _wind_context_note(wind_speed_ms: float | None, low_wind_caution: bool) -> str:
    # Mirrors frontend/components/ScenePanel.tsx's windContext() phrasing,
    # so the report reads the same as the dashboard's own wind-context line.
    if wind_speed_ms is None:
        return "Wind data unavailable — classification uses image features only."
    speed = f"{wind_speed_ms:.1f}"
    if low_wind_caution:
        return f"Wind {speed} m/s (low) — calm-water look-alikes considered; classification wind-adjusted."
    if wind_speed_ms > HIGH_WIND_THRESHOLD_MS:
        return f"Wind {speed} m/s (high) — supports oil evidence; classification wind-adjusted."
    return f"Wind {speed} m/s (moderate) — no adjustment applied."


def _suspect_for_report(suspect: dict) -> dict:
    return {
        "name": suspect["vessel_name"],
        "mmsi": suspect["mmsi"],
        "type": suspect["vessel_type"],
        "confidence": suspect["confidence"],
        "distance_km": suspect["min_distance_km"],
        "time_before_min": suspect["time_gap_min"],
        "intersects": suspect["intersects"],
    }


def _assemble_report_data(spill_metadata: dict, correlation: dict) -> dict | None:
    """The consolidated {scene, spill, weather, attribution, overlay_url}
    used by both /api/report/latest and incident logging -- one place that
    defines what a "report" or "incident" actually contains, so the two
    can never drift apart. Returns None if there isn't enough data yet
    (no centroid, no regions, or no suspects)."""
    regions = spill_metadata.get("regions") or []
    suspects = correlation.get("suspects") or []
    if not spill_metadata.get("centroid") or not regions or not suspects:
        return None

    primary = regions[0]  # regions are already ranked by oil_confidence, highest first

    weather = None
    if os.path.exists(LATEST_WEATHER_PATH):
        with open(LATEST_WEATHER_PATH, "r") as f:
            raw_weather = json.load(f)
        weather = {
            "wind_speed_ms": raw_weather.get("wind_speed_ms"),
            "wind_direction": raw_weather.get("wind_direction"),
            "wave_height_m": raw_weather.get("wave_height_m"),
            "current_velocity_ms": raw_weather.get("current_velocity_ms"),
            "temperature_c": raw_weather.get("temperature_c"),
            "pressure_hpa": raw_weather.get("surface_pressure_hpa"),
        }

    return {
        "scene": SCENE,
        "spill": {
            "classification": primary["classification"],
            "oil_confidence": primary["oil_confidence"],
            "area_km2": primary["area_km2"],
            "length_km": primary["length_km"],
            "width_km": primary["width_km"],
            "centroid": primary["centroid"],
            "severity": _severity_from_area(primary["area_km2"]),
            "regions": regions,
            "wind_context": _wind_context_note(
                primary.get("wind_speed_ms"), primary.get("low_wind_caution", False)
            ),
        },
        "weather": weather,
        "attribution": {
            "likely_offender": _suspect_for_report(suspects[0]),
            "ranking": [_suspect_for_report(s) for s in suspects[:3]],
        },
        "overlay_url": spill_metadata.get("overlay_url"),
    }


@app.get("/api/report/latest")
def report_latest_endpoint():
    not_ready = {
        "available": False,
        "message": "Run detection and AIS correlation on the Dashboard first.",
    }

    if not os.path.exists(SPILL_METADATA_PATH) or not os.path.exists(LATEST_CORRELATION_PATH):
        return not_ready

    with open(SPILL_METADATA_PATH, "r") as f:
        spill_metadata = json.load(f)
    with open(LATEST_CORRELATION_PATH, "r") as f:
        correlation = json.load(f)

    data = _assemble_report_data(spill_metadata, correlation)
    if data is None:
        return not_ready

    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **data,
    }


# --- Incident history (Alerts page) ---


def _load_incidents() -> list:
    if not os.path.exists(INCIDENTS_PATH):
        return []
    try:
        with open(INCIDENTS_PATH, "r") as f:
            return json.load(f)
    except (ValueError, OSError):
        return []


def _save_incidents(incidents: list) -> None:
    with open(INCIDENTS_PATH, "w") as f:
        json.dump(incidents, f)


def _log_incident(spill_metadata: dict, correlation: dict) -> None:
    """Append a full incident record for the Alerts page. Called from
    /api/correlate as a best-effort side effect -- see the try/except at
    the call site, which is what actually guarantees this never breaks
    correlation."""
    data = _assemble_report_data(spill_metadata, correlation)
    if data is None:
        return

    now = datetime.now(timezone.utc)
    incidents = _load_incidents()
    incidents.append(
        {
            "incident_id": f"SINDVA-{now.strftime('%Y%m%d-%H%M%S')}",
            "logged_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "New",
            **data,
        }
    )
    _save_incidents(incidents)


class StatusUpdate(BaseModel):
    status: str


@app.get("/api/incidents")
def list_incidents():
    incidents = _load_incidents()
    summaries = [
        {
            "incident_id": inc["incident_id"],
            "logged_at": inc["logged_at"],
            "region": inc["scene"]["name"],
            "centroid": inc["spill"]["centroid"],
            "severity": inc["spill"]["severity"],
            "classification": inc["spill"]["classification"],
            "oil_confidence": inc["spill"]["oil_confidence"],
            "likely_offender_name": inc["attribution"]["likely_offender"]["name"],
            "attribution_confidence": inc["attribution"]["likely_offender"]["confidence"],
            "status": inc["status"],
        }
        for inc in incidents
    ]
    summaries.sort(key=lambda s: s["logged_at"], reverse=True)
    return summaries


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    for inc in _load_incidents():
        if inc["incident_id"] == incident_id:
            return inc
    raise HTTPException(status_code=404, detail="Incident not found.")


@app.post("/api/incidents/{incident_id}/status")
def update_incident_status(incident_id: str, payload: StatusUpdate):
    if payload.status not in ALLOWED_INCIDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(ALLOWED_INCIDENT_STATUSES)}",
        )

    incidents = _load_incidents()
    for inc in incidents:
        if inc["incident_id"] == incident_id:
            inc["status"] = payload.status
            _save_incidents(incidents)
            return {"incident_id": incident_id, "status": payload.status}

    raise HTTPException(status_code=404, detail="Incident not found.")
