"""
AIS transmission-gap ("dark vessel") detection.

Shared by ais/correlate.py (attaches these fields, display-only, to every
ranked suspect) and ais/investigate.py (surfaces the full detail for the
likely offender's case file), so the exact same gap-finding logic and
honest framing are used in both places -- never two slightly different
implementations that could disagree.

A "gap" is simply a longer-than-usual silence between two consecutive AIS
reports from the same vessel. It is an ANOMALY worth flagging, never proof
of anything -- DARK_VESSEL_NOTE below is the single source of truth for how
that is worded everywhere it's shown (backend responses and the frontend
both use it verbatim).
"""

from datetime import datetime, timedelta

from ais.geo import parse_iso

# A gap between consecutive reports longer than this counts as a
# transmission gap. Configurable per call -- this is only the default.
DEFAULT_GAP_THRESHOLD_MIN = 15.0

# How far around the scene's detection/pass time counts as "the spill
# window" for deciding whether a gap's timing is suspicious, not just long.
# Deliberately generous (wider than the origin-estimation drift assumption
# in origin/estimate_origin.py) since the true release moment is itself an
# estimate, not a known fact.
SPILL_WINDOW_BEFORE_MIN = 60.0
SPILL_WINDOW_AFTER_MIN = 30.0

DARK_VESSEL_NOTE = (
    "AIS gap detected — possible transponder inactivity during the spill window. "
    "Raises anomaly score; NOT proof of intent."
)


def _as_dt(t) -> datetime:
    """Points come from two different sources with two different `time`
    representations: ais.correlate._load_grouped()'s internal grouped
    points carry a parsed datetime, while ais.correlate.load_tracks()'s
    public/JSON-safe points carry an ISO string. Accept either."""
    return t if isinstance(t, datetime) else parse_iso(t)


def detect_gaps(points: list, threshold_min: float = DEFAULT_GAP_THRESHOLD_MIN) -> list:
    """Consecutive-report gaps longer than `threshold_min` minutes. Each
    entry carries the vessel's last-known position before the gap and its
    first position after it reappears -- `overlaps_spill_window` is added
    separately by summarize_gaps() once a scene time is known. gap_start/
    gap_end are always returned as ISO strings, regardless of which `time`
    representation the input points used."""
    gaps = []
    for p1, p2 in zip(points, points[1:]):
        t1, t2 = _as_dt(p1["time"]), _as_dt(p2["time"])
        gap_min = (t2 - t1).total_seconds() / 60.0
        if gap_min > threshold_min:
            gaps.append(
                {
                    "gap_start": t1.isoformat(),
                    "gap_end": t2.isoformat(),
                    "gap_duration_min": round(gap_min, 1),
                    "last_position_before": {"lat": p1["lat"], "lon": p1["lon"]},
                    "first_position_after": {"lat": p2["lat"], "lon": p2["lon"]},
                }
            )
    return gaps


def spill_window(scene_dt):
    """(start, end) datetimes bracketing the estimated spill/origin time,
    for deciding whether a gap's timing overlaps it. None if there's no
    scene time to anchor to (gap overlap is then simply False for every
    gap -- a gap can still be reported, just not flagged as suspiciously
    timed)."""
    if scene_dt is None:
        return None
    return (
        scene_dt - timedelta(minutes=SPILL_WINDOW_BEFORE_MIN),
        scene_dt + timedelta(minutes=SPILL_WINDOW_AFTER_MIN),
    )


def _overlaps(gap: dict, window) -> bool:
    if window is None:
        return False
    win_start, win_end = window
    gap_start, gap_end = parse_iso(gap["gap_start"]), parse_iso(gap["gap_end"])
    return gap_start <= win_end and gap_end >= win_start


def summarize_gaps(points: list, scene_dt, threshold_min: float = DEFAULT_GAP_THRESHOLD_MIN) -> dict:
    """The additive {ais_gaps, dark_vessel_flag, total_dark_minutes} block
    both ais/correlate.py and ais/investigate.py attach to a vessel. Never
    raises -- an empty/short points list simply yields no gaps."""
    window = spill_window(scene_dt)
    gaps = detect_gaps(points, threshold_min)
    for g in gaps:
        g["overlaps_spill_window"] = _overlaps(g, window)

    return {
        "ais_gaps": gaps,
        "dark_vessel_flag": any(g["overlaps_spill_window"] for g in gaps),
        "total_dark_minutes": round(sum(g["gap_duration_min"] for g in gaps), 1),
    }
