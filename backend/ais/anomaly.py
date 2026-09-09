"""
Kinematic/behavioral anomaly scoring, shared by ais/correlate.py (feeds the
"A" factor of the Culprit Correlation Index) and available for anything
else that wants the same slowdown read on a vessel's own track -- one
implementation, so scores never quietly disagree.

This is a description of what a track's SOG values show, nothing more: it
never asserts intent, and it never feeds back into detection or the
classifier.
"""

# A vessel's minimum reported speed at or below this fraction of its own
# track-high counts as a "slowdown" for the boolean flag; the anomaly
# SCORE itself is continuous (see anomaly_score()), so this constant only
# gates the boolean read, not the number.
SLOWDOWN_DROP_FRACTION = 0.35


def speed_anomaly(points: list) -> dict:
    """How much a vessel's own track slowed down, and where. Returns
    {"slowdown_detected", "min_speed_kn", "max_speed_kn", "drop_fraction",
    "slowdown_at"} -- drop_fraction is (max-min)/max, 0 when there's no
    speed data or the vessel never moved."""
    speeds = [p["sog"] for p in points if p["sog"] is not None]
    if not speeds:
        return {
            "slowdown_detected": False,
            "min_speed_kn": None,
            "max_speed_kn": None,
            "drop_fraction": 0.0,
            "slowdown_at": None,
        }

    min_speed, max_speed = min(speeds), max(speeds)
    drop_fraction = 0.0 if max_speed <= 0 else (max_speed - min_speed) / max_speed
    slowdown_detected = max_speed > 0 and min_speed <= max_speed * (1 - SLOWDOWN_DROP_FRACTION)

    slowdown_at = None
    if slowdown_detected:
        slow_point = min((p for p in points if p["sog"] is not None), key=lambda p: p["sog"])
        slowdown_at = {
            "time": slow_point["time"],
            "lat": slow_point["lat"],
            "lon": slow_point["lon"],
            "sog": slow_point["sog"],
        }

    return {
        "slowdown_detected": slowdown_detected,
        "min_speed_kn": round(min_speed, 1),
        "max_speed_kn": round(max_speed, 1),
        "drop_fraction": round(drop_fraction, 3),
        "slowdown_at": slowdown_at,
    }


def anomaly_score(points: list) -> float:
    """0-100 behavioral/kinematic anomaly subscore: how much the vessel's
    speed dropped from its own track-high, as a percentage. A vessel that
    never varies its speed scores 0; one that came to a near-stop from a
    normal transit speed scores near 100."""
    result = speed_anomaly(points)
    return round(min(100.0, max(0.0, result["drop_fraction"] * 100.0)), 1)
