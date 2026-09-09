"""
AIS-to-spill correlation engine (classic geometry, no ML).

Every vessel in the AIS CSV is scored with a Culprit Correlation Index
(CCI) -- an explicit, transparent weighted sum of six named factors, each
0-100, each independently shown alongside its weight and its weighted
contribution:

    D  Distance correlation        25%  -- closeness of nearest approach
    T  Temporal correlation        25%  -- timing vs. the spill window
    R  Trajectory correlation      20%  -- does the track intersect the spill
    A  Behavioral/kinematic        15%  -- speed/heading anomaly (e.g. a
       anomaly                            slowdown) near the spill
    G  AIS gap anomaly             10%  -- a "dark vessel" gap overlapping
                                            the spill window (ais/gap_detect.py)
    V  Vessel context               5%  -- vessel-class relevance (tanker,
                                            chemical carrier, etc.)

    CCI = 0.25*D + 0.25*T + 0.20*R + 0.15*A + 0.10*G + 0.05*V   (weights sum to 1.0)

CCI is a CORRELATION score, not a probability and never proof of guilt --
it says which vessel's own data (position, timing, track shape, speed
behavior, and transponder history) lines up most strongly with the spill
event. `confidence` is kept as an alias of `cci` for callers/pages written
before this factor breakdown existed; every ranking decision in this
module is made on `cci`.

Every contribution below is computed as round(subscore * weight, 2), and
the displayed CCI is the sum of those same rounded contributions (not an
independently-rounded total) -- so the number shown can never fail to
equal the sum of the factors shown next to it.
"""

import os
import sys
from math import exp

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ais.anomaly import anomaly_score  # noqa: E402
from ais.gap_detect import summarize_gaps  # noqa: E402
from ais.geo import haversine_km, parse_iso  # noqa: E402

# A track within this radius of the centroid counts as intersecting the spill.
INTERSECT_RADIUS_KM = 0.3

# D -- distance correlation: full marks out to this radius, then a sharp
# Gaussian falloff.
PROXIMITY_PLATEAU_KM = 0.2
PROXIMITY_DECAY_KM = 0.25

# T -- temporal correlation: how soon before the spill's detection time the
# track's closest approach happened (oil drifts and spreads *after*
# release, so passing shortly before is far more suspicious than long
# before, or after, detection).
TEMPORAL_DECAY_BEFORE_MIN = 45.0
TEMPORAL_DECAY_AFTER_MIN = 30.0
AFTER_DETECTION_PENALTY = 0.5  # vessels seen only *after* detection are inherently less suspicious

# R -- trajectory correlation: intersecting tracks always score in the
# upper band; near-misses are graded down from a lower ceiling by how far
# past the intersection radius they got.
TRAJECTORY_INTERSECT_BASE = 80.0
TRAJECTORY_INTERSECT_SPAN = 20.0
TRAJECTORY_NEAR_MISS_BASE = 60.0
TRAJECTORY_NEAR_MISS_DECAY_KM = 1.5

# G -- AIS gap anomaly: a gap overlapping the spill window gets a strong
# base score that scales up with how long the vessel was dark; a gap that
# exists but doesn't overlap the window is scored low (a gap in general is
# a much weaker signal than a suspiciously-timed one); no gap at all is 0.
GAP_OVERLAP_BASE = 50.0
GAP_NO_OVERLAP_CAP = 25.0
GAP_NO_OVERLAP_SCALE = 0.3

# V -- vessel context: vessel-class relevance to an oil spill. Keyword
# match against VesselType (case-insensitive substring); first match wins.
VESSEL_RELEVANCE = {
    "tanker": 100.0,
    "chemical": 100.0,
    "oil": 95.0,
    "bulk carrier": 55.0,
    "cargo": 50.0,
    "container": 45.0,
    "tug": 30.0,
    "fishing": 20.0,
}
DEFAULT_VESSEL_RELEVANCE = 40.0

# CCI factor weights -- named, tunable, and must sum to 1.0 (checked below
# at import time so a typo here fails loudly, not silently).
CCI_WEIGHTS = {
    "D": 0.25,
    "T": 0.25,
    "R": 0.20,
    "A": 0.15,
    "G": 0.10,
    "V": 0.05,
}
CCI_FACTOR_LABELS = {
    "D": "Distance correlation",
    "T": "Temporal correlation",
    "R": "Trajectory correlation",
    "A": "Behavioral/kinematic anomaly",
    "G": "AIS gap anomaly",
    "V": "Vessel context",
}
assert abs(sum(CCI_WEIGHTS.values()) - 1.0) < 1e-9, "CCI_WEIGHTS must sum to 1.0"

CCI_NOTE = "Correlation-based evidence score — indicates strongest correlation with the spill event, not proof of guilt."


def _load_grouped(ais_csv_path: str) -> dict:
    """Group the AIS CSV into per-vessel tracks, sorted by time."""
    df = pd.read_csv(ais_csv_path)

    grouped = {}
    for mmsi, rows in df.groupby("MMSI"):
        rows = rows.sort_values("BaseDateTime")
        points = [
            {
                "lat": float(r.LAT),
                "lon": float(r.LON),
                "time": parse_iso(str(r.BaseDateTime).replace(" ", "T")),
                "sog": float(r.SOG) if not pd.isna(r.SOG) else None,
                "cog": float(r.COG) if not pd.isna(r.COG) else None,
                "heading": float(r.Heading) if not pd.isna(r.Heading) else None,
            }
            for r in rows.itertuples(index=False)
        ]
        first = rows.iloc[0]
        grouped[int(mmsi)] = {
            "name": str(first["VesselName"]),
            "type": str(first["VesselType"]),
            "length_m": float(first["Length"]) if not pd.isna(first["Length"]) else None,
            "width_m": float(first["Width"]) if not pd.isna(first["Width"]) else None,
            "draft_m": float(first["Draft"]) if not pd.isna(first["Draft"]) else None,
            "points": points,
        }
    return grouped


def load_tracks(ais_csv_path: str) -> list:
    """Return AIS tracks in the shape the frontend map needs (JSON-safe)."""
    grouped = _load_grouped(ais_csv_path)
    tracks = []
    for mmsi, vessel in grouped.items():
        tracks.append(
            {
                "mmsi": mmsi,
                "name": vessel["name"],
                "type": vessel["type"],
                "points": [
                    {
                        "lat": p["lat"],
                        "lon": p["lon"],
                        "time": p["time"].isoformat(),
                        "sog": p["sog"],
                        "cog": p["cog"],
                        "heading": p["heading"],
                    }
                    for p in vessel["points"]
                ],
            }
        )
    return tracks


def _proximity_score(min_distance_km: float) -> float:
    """Sharp, continuous closeness score -- full marks near the centroid,
    steep Gaussian falloff beyond. Feeds both D directly and R's
    within-intersection grading."""
    if min_distance_km <= PROXIMITY_PLATEAU_KM:
        return 1.0
    overshoot = min_distance_km - PROXIMITY_PLATEAU_KM
    return exp(-((overshoot / PROXIMITY_DECAY_KM) ** 2))


def _temporal_score(time_gap_min: float) -> float:
    """time_gap_min > 0 means the closest approach was BEFORE detection."""
    if time_gap_min >= 0:
        return exp(-time_gap_min / TEMPORAL_DECAY_BEFORE_MIN)
    return AFTER_DETECTION_PENALTY * exp(-abs(time_gap_min) / TEMPORAL_DECAY_AFTER_MIN)


def _trajectory_score(min_distance_km: float, intersects: bool) -> float:
    """R: intersecting tracks always land in [80, 100]; near-misses are
    graded down from a 60-point ceiling by how far past the intersection
    radius they got -- always below the intersecting band."""
    if intersects:
        return round(TRAJECTORY_INTERSECT_BASE + TRAJECTORY_INTERSECT_SPAN * _proximity_score(min_distance_km), 1)
    overshoot = max(0.0, min_distance_km - INTERSECT_RADIUS_KM)
    return round(TRAJECTORY_NEAR_MISS_BASE * exp(-overshoot / TRAJECTORY_NEAR_MISS_DECAY_KM), 1)


def _gap_anomaly_score(gap_summary: dict) -> float:
    """G: a gap overlapping the spill window scores strongly, scaling with
    how long the vessel was dark; a non-overlapping gap is a much weaker
    signal (long gaps far from the spill window are common and mundane);
    no gap at all scores 0."""
    if gap_summary["dark_vessel_flag"]:
        return round(min(100.0, GAP_OVERLAP_BASE + gap_summary["total_dark_minutes"]), 1)
    if gap_summary["ais_gaps"]:
        return round(min(GAP_NO_OVERLAP_CAP, gap_summary["total_dark_minutes"] * GAP_NO_OVERLAP_SCALE), 1)
    return 0.0


def _vessel_relevance_score(vessel_type: str) -> float:
    """V: vessel-class relevance to an oil spill -- a CONTEXT feature only
    (5% weight), never a substitute for the evidence factors above it."""
    vt = (vessel_type or "").lower()
    for keyword, score in VESSEL_RELEVANCE.items():
        if keyword in vt:
            return score
    return DEFAULT_VESSEL_RELEVANCE


def _cci(min_distance_km: float, time_gap_min: float, intersects: bool, vessel_type: str, gap_summary: dict, points: list):
    """The full CCI breakdown for one vessel: (cci_total, breakdown_list).
    breakdown_list has one entry per factor -- {factor, label, subscore,
    weight, contribution} -- and cci_total is defined as the sum of the
    already-rounded contributions, so the displayed total can never
    diverge from the displayed factors that make it up."""
    subscores = {
        "D": round(100.0 * _proximity_score(min_distance_km), 1),
        "T": round(100.0 * _temporal_score(time_gap_min), 1),
        "R": _trajectory_score(min_distance_km, intersects),
        "A": anomaly_score(points),
        "G": _gap_anomaly_score(gap_summary),
        "V": _vessel_relevance_score(vessel_type),
    }

    breakdown = []
    for factor in ("D", "T", "R", "A", "G", "V"):
        weight = CCI_WEIGHTS[factor]
        subscore = subscores[factor]
        contribution = round(subscore * weight, 2)
        breakdown.append(
            {
                "factor": factor,
                "label": CCI_FACTOR_LABELS[factor],
                "subscore": subscore,
                "weight": weight,
                "contribution": contribution,
            }
        )

    cci = round(min(100.0, max(0.0, sum(b["contribution"] for b in breakdown))), 1)
    return cci, breakdown


def correlate(spill_metadata: dict, ais_csv_path: str) -> list:
    """Rank every vessel in the AIS CSV by Culprit Correlation Index (CCI)."""
    centroid = spill_metadata["centroid"]
    scene_dt = parse_iso(spill_metadata["scene_timestamp"])

    grouped = _load_grouped(ais_csv_path)

    ranked = []
    for mmsi, vessel in grouped.items():
        best_distance_km = None
        best_time_gap_min = None
        best_point = None

        for point in vessel["points"]:
            distance_km = haversine_km(
                centroid["lat"], centroid["lon"], point["lat"], point["lon"]
            )
            if best_distance_km is None or distance_km < best_distance_km:
                best_distance_km = distance_km
                time_gap_min = (scene_dt - point["time"]).total_seconds() / 60.0
                best_time_gap_min = time_gap_min
                best_point = point

        intersects = best_distance_km <= INTERSECT_RADIUS_KM

        # AIS transmission-gap ("dark vessel") analysis -- feeds the G
        # factor below, and is also returned in full for display.
        gap_summary = summarize_gaps(vessel["points"], scene_dt)

        cci, cci_breakdown = _cci(
            best_distance_km, best_time_gap_min, intersects, vessel["type"], gap_summary, vessel["points"]
        )

        ranked.append(
            {
                "mmsi": mmsi,
                "vessel_name": vessel["name"],
                "vessel_type": vessel["type"],
                # `confidence` is kept as an alias of `cci` for backward
                # compatibility with pages/fields written before the CCI
                # breakdown existed -- they are always numerically equal.
                "confidence": cci,
                "cci": cci,
                "cci_breakdown": cci_breakdown,
                "cci_note": CCI_NOTE,
                "min_distance_km": round(best_distance_km, 3),
                "time_gap_min": round(best_time_gap_min, 1),
                "before_detection": bool(best_time_gap_min >= 0),
                "intersects": bool(intersects),
                # AIS-derived vessel parameters (static fields from the CSV,
                # dynamic fields taken at this vessel's nearest-approach
                # point to the spill centroid) -- display-only additions,
                # do not feed into the CCI factors above except via V
                # (vessel_type) and A/G (which read the track, not these
                # fields directly).
                "length_m": vessel["length_m"],
                "width_m": vessel["width_m"],
                "draft_m": vessel["draft_m"],
                "speed_sog": best_point["sog"],
                "course_cog": best_point["cog"],
                "heading": best_point["heading"],
                # AIS gap ("dark vessel") analysis -- see ais/gap_detect.py.
                # An anomaly signal only, never proof of intent.
                "ais_gaps": gap_summary["ais_gaps"],
                "dark_vessel_flag": gap_summary["dark_vessel_flag"],
                "total_dark_minutes": gap_summary["total_dark_minutes"],
            }
        )

    ranked.sort(key=lambda v: v["cci"], reverse=True)
    return ranked
