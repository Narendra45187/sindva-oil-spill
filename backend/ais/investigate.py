"""
AIS behavioral investigation ("case file") for the likely-offender vessel.

Builds a case out of a single vessel's own AIS track: how its speed and
course behaved as it passed near the spill, whether it slowed or lingered
around the closest-approach point, and its overall time in the scene.
Every claim in the generated `investigation_summary` narrative is derived
directly from the values computed here -- nothing is asserted that the
track data doesn't actually show.

This module only reads AIS points and a spill centroid; it never touches
detection, classification, or the correlation ranking itself (that stays
entirely in ais/correlate.py -- this module reads its output, never its
inputs or scoring).
"""

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ais.correlate import load_tracks  # noqa: E402
from ais.gap_detect import DARK_VESSEL_NOTE, summarize_gaps  # noqa: E402
from ais.geo import haversine_km, parse_iso  # noqa: E402

# Thresholds below are descriptive-analysis cutoffs only -- they never feed
# back into ais/correlate.py's confidence score.
SLOWDOWN_DROP_FRACTION = 0.35  # speed must fall to <=65% of the track's max to flag a slowdown
LOITER_SPEED_KN = 3.0  # "loitering" = sustained speed at/below this
LOITER_MIN_CONSECUTIVE = 2  # need at least this many consecutive slow reports
COURSE_CHANGE_DEG = 25.0  # heading/COG change between consecutive reports worth flagging


def _track_for_mmsi(ais_csv_path: str, mmsi: int) -> dict | None:
    for track in load_tracks(ais_csv_path):
        if track["mmsi"] == mmsi:
            return track
    return None


def _angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two compass headings, 0-180."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _analyze_speed(points: list) -> dict:
    speeds = [p["sog"] for p in points if p["sog"] is not None]
    if not speeds:
        return {
            "speed_profile": [{"time": p["time"], "sog": None} for p in points],
            "min_speed_kn": None,
            "max_speed_kn": None,
            "avg_speed_kn": None,
            "slowdown_detected": False,
            "slowdown_at": None,
        }

    speed_profile = [{"time": p["time"], "sog": p["sog"]} for p in points]
    min_speed = min(speeds)
    max_speed = max(speeds)
    avg_speed = round(statistics.fmean(speeds), 2)

    slowdown_detected = False
    slowdown_at = None
    if max_speed > 0 and min_speed <= max_speed * (1 - SLOWDOWN_DROP_FRACTION):
        slow_point = min((p for p in points if p["sog"] is not None), key=lambda p: p["sog"])
        slowdown_detected = True
        slowdown_at = {
            "time": slow_point["time"],
            "lat": slow_point["lat"],
            "lon": slow_point["lon"],
            "sog": slow_point["sog"],
        }

    return {
        "speed_profile": speed_profile,
        "min_speed_kn": round(min_speed, 1),
        "max_speed_kn": round(max_speed, 1),
        "avg_speed_kn": avg_speed,
        "slowdown_detected": slowdown_detected,
        "slowdown_at": slowdown_at,
    }


def _analyze_course(points: list) -> dict:
    headings = [(p["time"], p["lat"], p["lon"], p["cog"] if p["cog"] is not None else p["heading"]) for p in points]
    headings = [(t, lat, lon, h) for t, lat, lon, h in headings if h is not None]

    changes = []
    for (_, _, _, h1), (t2, lat2, lon2, h2) in zip(headings, headings[1:]):
        diff = _angle_diff(h1, h2)
        if diff >= COURSE_CHANGE_DEG:
            changes.append(
                {"time": t2, "lat": lat2, "lon": lon2, "from_deg": round(h1, 1), "to_deg": round(h2, 1), "change_deg": round(diff, 1)}
            )

    return {
        "course_change_detected": len(changes) > 0,
        "course_changes": changes,
    }


def _analyze_loitering(points: list) -> dict:
    run = 0
    best_run = 0
    run_start = None
    best_start = None
    for p in points:
        if p["sog"] is not None and p["sog"] <= LOITER_SPEED_KN:
            if run == 0:
                run_start = p
            run += 1
            if run > best_run:
                best_run = run
                best_start = run_start
        else:
            run = 0

    loitering_detected = best_run >= LOITER_MIN_CONSECUTIVE
    return {
        "loitering_detected": loitering_detected,
        "loitering_points": best_run if loitering_detected else 0,
        "loitering_at": (
            {"time": best_start["time"], "lat": best_start["lat"], "lon": best_start["lon"]}
            if loitering_detected and best_start
            else None
        ),
    }


def _nearest_approach(points: list, centroid: dict | None, scene_dt) -> dict | None:
    if not points or not centroid or scene_dt is None:
        return None
    best = None
    best_dist = None
    for p in points:
        d = haversine_km(centroid["lat"], centroid["lon"], p["lat"], p["lon"])
        if best_dist is None or d < best_dist:
            best_dist = d
            best = p
    if best is None:
        return None
    t = parse_iso(best["time"])
    time_gap_min = (scene_dt - t).total_seconds() / 60.0
    return {
        "time": best["time"],
        "lat": best["lat"],
        "lon": best["lon"],
        "sog": best["sog"],
        "distance_km": round(best_dist, 3),
        "time_gap_min": round(time_gap_min, 1),
        "before_detection": bool(time_gap_min >= 0),
    }


def _voyage_context(points: list) -> dict:
    if not points:
        return {
            "entry_time": None,
            "exit_time": None,
            "entry_position": None,
            "exit_position": None,
            "time_in_area_min": None,
        }
    first, last = points[0], points[-1]
    t0, t1 = parse_iso(first["time"]), parse_iso(last["time"])
    return {
        "entry_time": first["time"],
        "exit_time": last["time"],
        "entry_position": {"lat": first["lat"], "lon": first["lon"]},
        "exit_position": {"lat": last["lat"], "lon": last["lon"]},
        "time_in_area_min": round((t1 - t0).total_seconds() / 60.0, 1),
    }


def _format_time(iso_ts: str | None) -> str:
    if not iso_ts:
        return "an unknown time"
    try:
        return parse_iso(iso_ts).strftime("%H:%M UTC")
    except ValueError:
        return iso_ts


def _build_summary(
    name: str, mmsi: int, voyage: dict, nearest: dict | None, speed: dict, course: dict, loiter: dict, gaps: dict
) -> str:
    if not voyage["entry_time"]:
        return f"Vessel {name} (MMSI {mmsi}) has no usable AIS track in this scene."

    sentence = f"Vessel {name} (MMSI {mmsi}) entered the area at {_format_time(voyage['entry_time'])}"

    if nearest:
        sentence += f", approached within {nearest['distance_km']:.2f} km of the spill at {_format_time(nearest['time'])}"

    clauses = []
    if speed["slowdown_detected"]:
        clauses.append(
            f"slowed to {speed['min_speed_kn']:.1f} kn (from a track high of {speed['max_speed_kn']:.1f} kn) near that point"
        )
    if loiter["loitering_detected"]:
        clauses.append(f"held a near-stationary speed for {loiter['loitering_points']} consecutive AIS reports")
    if course["course_change_detected"]:
        sharpest = max(course["course_changes"], key=lambda c: c["change_deg"])
        clauses.append(f"made a {sharpest['change_deg']:.0f}° course change nearby")

    if len(clauses) == 1:
        sentence += f", {clauses[0]}"
    elif len(clauses) > 1:
        sentence += ", " + ", ".join(clauses[:-1]) + f", and {clauses[-1]}"

    sentence += f", then exited the area at {_format_time(voyage['exit_time'])}."

    behavior_flagged = speed["slowdown_detected"] or loiter["loitering_detected"]
    if nearest and nearest.get("before_detection") and behavior_flagged:
        sentence += " Behavior is consistent with a discharge event."
    elif nearest and nearest.get("before_detection"):
        sentence += (
            " No slowdown, loitering, or sharp course change was detected near closest approach; "
            "behavior is not clearly consistent with a discharge event beyond proximity and timing alone."
        )
    elif nearest:
        sentence += " Closest approach occurred after the scene's detection time, which weakens (but does not rule out) a discharge link."

    # AIS gap clause -- an anomaly note, never an assertion of deliberate
    # evasion. Only mentions the single longest gap that overlaps the spill
    # window, matching what dark_vessel_flag itself is based on.
    if gaps["dark_vessel_flag"]:
        overlapping = [g for g in gaps["ais_gaps"] if g["overlaps_spill_window"]]
        longest = max(overlapping, key=lambda g: g["gap_duration_min"])
        sentence += (
            f" An AIS transmission gap of {longest['gap_duration_min']:.0f} min was detected "
            f"(from {_format_time(longest['gap_start'])} to {_format_time(longest['gap_end'])}), overlapping "
            "the estimated spill window — possible transponder inactivity; this raises the anomaly score "
            "but is not proof of intent."
        )

    return sentence


def investigate(spill_metadata: dict, suspect: dict, ais_csv_path: str) -> dict:
    """Build the AIS behavioral case file for one suspect vessel.

    spill_metadata: the persisted /api/detect metadata (uses `centroid` and
        `scene_timestamp`; both optional -- nearest-approach analysis is
        simply omitted if either is missing).
    suspect: one ranked entry from ais.correlate.correlate() (uses `mmsi`,
        `confidence`, `min_distance_km`, `time_gap_min`, `intersects`).
    ais_csv_path: path to the AIS CSV correlation was run against.

    Returns {"available": False, "message": ...} if there's no track for
    this vessel's MMSI; otherwise the full analysis described in this
    module's docstring plus an `investigation_summary` narrative built only
    from the values actually computed here.
    """
    mmsi = suspect["mmsi"]
    track = _track_for_mmsi(ais_csv_path, mmsi)
    if not track or not track["points"]:
        return {"available": False, "message": f"No AIS track found for MMSI {mmsi}."}

    points = track["points"]
    centroid = spill_metadata.get("centroid")
    scene_ts = spill_metadata.get("scene_timestamp")
    scene_dt = parse_iso(scene_ts) if scene_ts else None

    speed = _analyze_speed(points)
    course = _analyze_course(points)
    loiter = _analyze_loitering(points)
    nearest = _nearest_approach(points, centroid, scene_dt)
    voyage = _voyage_context(points)
    gaps = summarize_gaps(points, scene_dt)

    summary = _build_summary(track["name"], mmsi, voyage, nearest, speed, course, loiter, gaps)

    return {
        "available": True,
        "vessel": {"mmsi": mmsi, "name": track["name"], "vessel_type": track["type"]},
        "attribution": {
            "confidence": suspect.get("confidence"),
            "min_distance_km": suspect.get("min_distance_km"),
            "time_gap_min": suspect.get("time_gap_min"),
            "intersects": suspect.get("intersects"),
            "length_m": suspect.get("length_m"),
            "width_m": suspect.get("width_m"),
            "draft_m": suspect.get("draft_m"),
        },
        # Culprit Correlation Index -- computed and ranked in
        # ais/correlate.py; passed through here unchanged so the case file
        # shows exactly the same breakdown that determined this vessel's
        # rank, never a second, possibly-divergent computation.
        "cci": suspect.get("cci"),
        "cci_breakdown": suspect.get("cci_breakdown"),
        "cci_note": suspect.get("cci_note"),
        "speed_profile": speed["speed_profile"],
        "speed_stats": {
            "min_speed_kn": speed["min_speed_kn"],
            "max_speed_kn": speed["max_speed_kn"],
            "avg_speed_kn": speed["avg_speed_kn"],
        },
        "slowdown_detected": speed["slowdown_detected"],
        "slowdown_at": speed["slowdown_at"],
        "course_change_detected": course["course_change_detected"],
        "course_changes": course["course_changes"],
        "loitering_detected": loiter["loitering_detected"],
        "loitering_at": loiter["loitering_at"],
        "nearest_approach": nearest,
        "voyage_context": voyage,
        # AIS transmission-gap ("dark vessel") analysis -- see
        # ais/gap_detect.py. dark_vessel_note is the single, honest
        # framing this data should always be shown with.
        "ais_gaps": gaps["ais_gaps"],
        "dark_vessel_flag": gaps["dark_vessel_flag"],
        "total_dark_minutes": gaps["total_dark_minutes"],
        "dark_vessel_note": DARK_VESSEL_NOTE,
        "track_points": points,
        "investigation_summary": summary,
    }
