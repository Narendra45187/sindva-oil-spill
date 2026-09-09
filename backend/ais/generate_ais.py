"""
Synthetic AIS track generator for the Visakhapatnam scene (MarineCadastre.gov
column format). Run this once to produce backend/data/ais/ais_vizag.csv;
backend/app.py reads that file on every /api/correlate call rather than
regenerating it.

    py -3.12 backend/ais/generate_ais.py

Each vessel gets a short, straight-line track that passes closest to the
spill centroid at a chosen (time offset, distance) pair. The track's course
is set perpendicular to the centroid bearing at that point, which makes the
chosen point the true closest-approach point of the whole line -- so the
correlation engine's "shortest distance from any point on the track" lines
up with the distance this script was told to place the vessel at.

Vessel 1 ("MV COASTAL PIONEER") genuinely passes through the spill: within
~150 m of the spill centroid, about 28 minutes before the scene's pass time
(inside the correlation engine's 300 m intersection radius and its 20-40 min
"shortly before" window). The other five are a deliberate spread, including
one near-miss vessel that is closer in time than vessel 1 but never comes
within the intersection radius -- a stress test for the correlation engine's
tiered scoring, which must rank a true intersection above any near-miss
regardless of timing. This file never marks a vessel as "the suspect" in the
data; which one ranks #1 is entirely up to backend/ais/correlate.py.

This generator requires a real detection to have been run first: it reads
the spill centroid and scene pass-time from
backend/data/outputs/spill_metadata.json (written by POST /api/detect) and
refuses to run without it, rather than falling back to a hardcoded point.
"""

import csv
import json
import math
import os
import random
import sys
from datetime import timedelta

# Make `ais` importable as a package regardless of how this file is invoked
# (as `py -3.12 backend/ais/generate_ais.py` from the repo root, or as
# `py -3.12 -m uvicorn app:app` from inside backend/ importing ais.correlate).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ais.geo import destination_point, move_along_heading, parse_iso  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AIS_DIR = os.path.join(BASE_DIR, "data", "ais")
AIS_CSV_PATH = os.path.join(AIS_DIR, "ais_vizag.csv")
SPILL_METADATA_PATH = os.path.join(BASE_DIR, "data", "outputs", "spill_metadata.json")

CSV_COLUMNS = [
    "MMSI",
    "BaseDateTime",
    "LAT",
    "LON",
    "SOG",
    "COG",
    "Heading",
    "VesselName",
    "VesselType",
    "Length",
    "Width",
    "Draft",
]

KNOTS_TO_KMH = 1.852

# (mmsi, name, vessel_type, length_m, width_m, draft_m,
#  closest_distance_km, closest_time_offset_min, speed_knots, has_slowdown,
#  gap_spec)
#
# Positive time offset = vessel closest-approach happens AFTER the scene's
# pass time; negative = BEFORE it (the physically suspicious direction,
# since a spill drifts after the release).
#
# Vessel 1 is the only one inside the correlation engine's 300 m
# intersection radius. Vessel 2 is a deliberate near-miss: closer in time
# than vessel 1 (15 min vs 28 min before) and only 450 m out, but that's
# still past the intersection radius -- it must NOT outrank vessel 1.
#
# has_slowdown=True (vessel 1 only) layers a subtle, reported-SOG-only dip
# around its closest-approach point -- realistic behavior for the AIS
# Investigation page's speed-profile analysis to detect. It does NOT alter
# the vessel's actual track geometry (still computed from its constant
# nominal speed, same as every other vessel here) and has no effect on
# correlation confidence, which never looks at SOG.
#
# gap_spec (None, or a tuple) drops real AIS points to create a true
# transmission gap -- see _apply_gap() below:
#   ("suspect_dark", start_offset_min, end_offset_min) -- vessel 1 only:
#       goes dark shortly AFTER its closest-approach point (which is always
#       kept, so the intersection/confidence geometry above is untouched)
#       for ~30 min, overlapping the scene's detection time -- the "dark
#       vessel" scenario for ais/gap_detect.py to find.
#   ("tail_benign", duration_min) -- an optional short, ordinary-looking
#       gap far from its own closest approach and from the scene time, on
#       one other vessel, so gap detection isn't trivially unique to the
#       suspect.
VESSELS = [
    (419123456, "MV COASTAL PIONEER", "Tanker", 182, 32, 11.5, 0.15, -28, 9.5, True, ("suspect_dark", 3, 35)),
    (419988771, "SEA GLORY", "Bulk Carrier", 190, 34, 12.0, 0.45, -15, 11.0, False, None),
    (636204591, "PACIFIC TRADER", "Cargo", 140, 23, 8.5, 3.6, 35, 13.0, False, ("tail_benign", 18)),
    (419556230, "BLUE HORIZON", "Fishing Vessel", 28, 7, 3.2, 8.0, -9, 7.0, False, None),
    (563812004, "NAVI STAR", "Container Ship", 210, 34, 13.0, 15.0, -63, 15.0, False, None),
    (419001122, "PORT GUARDIAN", "Tug", 24, 8, 3.6, 23.0, 71, 4.0, False, None),
]

# Slowdown-dip shape (reported SOG only -- see has_slowdown above): a
# Gaussian trough centered on the closest-approach moment (offset 0 min),
# easing back to normal speed within roughly its own width either side.
SLOWDOWN_DIP_SIGMA_MIN = 7.0
SLOWDOWN_DIP_DEPTH = 0.62  # fraction of nominal speed shed at the trough


def _apply_gap(offsets: list, gap_spec, half_span_min: float) -> list:
    """Drop offsets that fall inside the vessel's transmission-gap window
    (a real absence of data, not a flagged/interpolated point) -- see
    gap_spec's shape documented above VESSELS."""
    if gap_spec is None:
        return offsets

    kind = gap_spec[0]
    if kind == "suspect_dark":
        _, gap_start, gap_end = gap_spec
        return [o for o in offsets if not (gap_start < o < gap_end)]
    if kind == "tail_benign":
        _, duration = gap_spec
        tail_end = half_span_min - 4
        tail_start = tail_end - duration
        return [o for o in offsets if not (tail_start < o < tail_end)]
    return offsets


def _reported_sog(rng, speed_knots: float, offset_min: float, has_slowdown: bool) -> float:
    if not has_slowdown:
        return max(0.0, speed_knots + rng.uniform(-1.0, 1.0))
    dip = SLOWDOWN_DIP_DEPTH * math.exp(-(offset_min**2) / (2 * SLOWDOWN_DIP_SIGMA_MIN**2))
    slowed = speed_knots * (1 - dip)
    # Less noise while it's slowed (a vessel loitering/discharging holds a
    # steadier low speed than one running at normal transit speed).
    noise = rng.uniform(-1.0, 1.0) * (1 - dip) + rng.uniform(-0.3, 0.3) * dip
    return max(0.0, slowed + noise)


def _load_spill_context():
    """Read the real detected centroid/scene-time. Requires detection to have
    been run at least once -- refuses to fall back to a hardcoded point."""
    if not os.path.exists(SPILL_METADATA_PATH):
        raise SystemExit(
            "No detection has been run yet, so there's no real spill centroid to "
            "anchor the AIS scenario to.\n"
            "Run detection first -- POST /api/detect, or open the dashboard and "
            "click 'Analyze Visakhapatnam Scene' -- then re-run this generator."
        )

    with open(SPILL_METADATA_PATH, "r") as f:
        meta = json.load(f)

    centroid = meta.get("centroid")
    scene_ts = meta.get("scene_timestamp")
    if not centroid or not scene_ts:
        raise SystemExit(
            "The last detection found no spill (empty centroid), so there's "
            "nothing to anchor the AIS scenario to. Run detection against a "
            "scene with a real spill, then re-run this generator."
        )
    return centroid, scene_ts


def _build_track(rng, spec, centroid, scene_dt):
    (
        mmsi,
        name,
        vtype,
        length,
        width,
        draft,
        d_closest_km,
        t_closest_min,
        speed_knots,
        has_slowdown,
        gap_spec,
    ) = spec

    bearing_at_closest = rng.uniform(0, 360)
    closest_lat, closest_lon = destination_point(
        centroid["lat"], centroid["lon"], bearing_at_closest, d_closest_km
    )
    # Perpendicular course => the closest-approach point is the true minimum
    # of the whole line, not just of the sampled points.
    heading_deg = (bearing_at_closest + rng.choice([90, -90])) % 360

    half_span_min = min(rng.uniform(25, 80), 90 - abs(t_closest_min))
    half_span_min = max(half_span_min, 8)

    # Regular ~5-7 min reporting interval (small jitter, like real AIS) --
    # a well-defined, dense baseline so an injected gap (see gap_spec) reads
    # as a clear anomaly against it, rather than blending into already-
    # sparse random sampling. The grid always includes offset 0 exactly
    # (the closest-approach moment), so distance/time targets are still hit
    # exactly, not approximately.
    report_interval_min = rng.uniform(5.0, 7.0)
    n_each_side = max(1, int(half_span_min / report_interval_min))
    offsets = [i * report_interval_min for i in range(-n_each_side, n_each_side + 1)]
    offsets = _apply_gap(offsets, gap_spec, half_span_min)

    rows = []
    for offset_min in offsets:
        abs_offset_min = t_closest_min + offset_min
        timestamp = scene_dt + timedelta(minutes=abs_offset_min)

        distance_along_km = speed_knots * KNOTS_TO_KMH * (offset_min / 60.0)
        lat, lon = move_along_heading(closest_lat, closest_lon, heading_deg, distance_along_km)

        cog = (heading_deg + rng.uniform(-4, 4)) % 360
        heading_reported = (cog + rng.uniform(-3, 3)) % 360
        sog = _reported_sog(rng, speed_knots, offset_min, has_slowdown)

        rows.append(
            {
                "MMSI": mmsi,
                "BaseDateTime": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "LAT": round(lat, 5),
                "LON": round(lon, 5),
                "SOG": round(sog, 1),
                "COG": round(cog, 1),
                "Heading": int(round(heading_reported)) % 360,
                "VesselName": name,
                "VesselType": vtype,
                "Length": length,
                "Width": width,
                "Draft": draft,
            }
        )

    rows.sort(key=lambda r: r["BaseDateTime"])
    return rows


def generate(seed: int = 42) -> str:
    rng = random.Random(seed)
    centroid, scene_ts = _load_spill_context()
    scene_dt = parse_iso(scene_ts)

    os.makedirs(AIS_DIR, exist_ok=True)

    all_rows = []
    for spec in VESSELS:
        all_rows.extend(_build_track(rng, spec, centroid, scene_dt))

    with open(AIS_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    return AIS_CSV_PATH


if __name__ == "__main__":
    path = generate()
    print(f"Wrote {sum(1 for _ in open(path)) - 1} AIS points for {len(VESSELS)} vessels to {path}")
