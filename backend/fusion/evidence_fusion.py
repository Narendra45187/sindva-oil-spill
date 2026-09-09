"""
Uncertainty-aware evidence fusion.

Combines the confidence each independent pipeline stage already produces --
oil-spill detection, origin-estimation, and vessel-attribution (CCI) -- into
one honestly-labeled Overall Attribution Confidence, with the contributing
stage values and the fusion method always shown alongside it.

This module NEVER recomputes or adjusts any stage's own number. It reads
whatever detection/cv_detect.py (oil_confidence), origin/estimate_origin.py
(origin_confidence), and ais/correlate.py (cci) already produced -- callers
pass those straight through, unmodified. origin_confidence in particular is
computed and owned entirely by origin/estimate_origin.py (see its own
docstring) -- this module reads that single number for its "Origin
Reconstruction" stage rather than deriving a second, possibly-divergent one.

Fusion method: geometric mean of the available stage confidences (each
0-1). A geometric mean embodies "weakest link" reasoning -- one very weak
stage pulls the overall score down hard -- without being as brutal as a
raw product (which would crush the result if any single stage is merely
"a bit weak" rather than "essentially zero"). If a stage is unavailable,
it is simply excluded from the mean and the result is flagged with
reduced certainty, rather than silently treated as zero or as perfect.
"""

HIGH_THRESHOLD = 75.0
MEDIUM_THRESHOLD = 50.0

FUSION_METHOD = "geometric mean of stage confidences"

ATTRIBUTION_NOTE = "Overall evidence strength — correlation-based, not proof of guilt."

# Floor used only to keep a literal 0% stage from collapsing the entire
# geometric-mean product to exactly zero; does not materially change any
# realistic (non-zero) stage value.
_PRODUCT_FLOOR = 1e-6


def _category(overall_pct: float) -> str:
    if overall_pct >= HIGH_THRESHOLD:
        return "HIGH"
    if overall_pct >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def fuse_evidence(
    detection_conf_pct: float | None,
    origin_result: dict | None,
    attribution_cci_pct: float | None,
) -> dict:
    """Fuse the three pipeline-stage confidences into one Overall
    Attribution Confidence.

    detection_conf_pct: the primary spill region's oil_confidence (0-100),
        as already computed by detection/cv_detect.py -- or None if no
        detection has run yet.
    origin_result: the dict already returned by
        origin.estimate_origin.estimate_origin() (or None) -- read for its
        `available` flag AND its `origin_confidence` (0-100); neither is
        ever altered here.
    attribution_cci_pct: the top-ranked suspect's CCI (0-100), as already
        computed by ais/correlate.py -- or None if no correlation has run.

    Returns {"available": False, "message": ...} if not even one stage has
    produced a value yet. Otherwise:
        {
            "available": True,
            "overall_confidence": float,   # 0-100
            "category": "HIGH" | "MEDIUM" | "LOW",
            "method": str,
            "stages": [{"name", "value", "available"}, ...],  # all 3, always
            "reduced_certainty": bool,      # True if any stage was missing
            "missing_stages": [str, ...],
            "note": str,                    # honest framing, show verbatim
        }
    """
    stages = [
        {
            "name": "Oil Detection",
            "value": round(detection_conf_pct, 1) if detection_conf_pct is not None else None,
            "available": detection_conf_pct is not None,
        }
    ]

    origin_available = bool(origin_result and origin_result.get("available"))
    origin_conf = origin_result.get("origin_confidence") if origin_available else None
    stages.append(
        {
            "name": "Origin Reconstruction",
            "value": round(origin_conf, 1) if origin_conf is not None else None,
            "available": origin_conf is not None,
        }
    )

    stages.append(
        {
            "name": "Vessel Attribution (CCI)",
            "value": round(attribution_cci_pct, 1) if attribution_cci_pct is not None else None,
            "available": attribution_cci_pct is not None,
        }
    )

    available_values = [s["value"] / 100.0 for s in stages if s["available"]]

    if not available_values:
        return {
            "available": False,
            "message": "No pipeline stage has produced a confidence yet — run detection, then AIS correlation, on the Dashboard.",
        }

    product = 1.0
    for v in available_values:
        product *= max(v, _PRODUCT_FLOOR)
    overall = product ** (1.0 / len(available_values))
    overall_pct = round(min(100.0, max(0.0, overall * 100.0)), 1)

    missing_stages = [s["name"] for s in stages if not s["available"]]

    return {
        "available": True,
        "overall_confidence": overall_pct,
        "category": _category(overall_pct),
        "method": FUSION_METHOD,
        "stages": stages,
        "reduced_certainty": len(missing_stages) > 0,
        "missing_stages": missing_stages,
        "note": ATTRIBUTION_NOTE,
    }
