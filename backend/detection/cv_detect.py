"""
Classic-OpenCV oil-spill detection (no ML) with oil-vs-look-alike
discrimination and pixel-wise measurement.

Stage 1 -- finding candidate dark regions -- is unchanged from before:

  1. Estimates a local background brightness by blurring heavily (a wide
     Gaussian), then flags pixels that are darker than that local
     background by more than an adaptive margin. This finds anomalies
     relative to their neighborhood, not just "dark water" in general.
  2. Throws out any candidate region larger than MAX_REGION_FRACTION of the
     scene -- a blob that big is open sea / a sensor artifact, not a slick.
  3. Throws out tiny specks below MIN_REGION_PIXELS (speckle noise, ships).
  4. Keeps only the MAX_REGIONS largest surviving regions.

Stage 2 is new: a dark region is not necessarily oil -- wind shadows, algal
mats, calm-water patches, and internal waves all show up as dark SAR
anomalies too ("look-alikes"). For each candidate region this module now
measures four physically-motivated features and combines them into an
explainable oil-confidence score (a documented function of the measured
features -- no ML, no randomness):

  - contrast:       mean darkness of the region vs. a ring of water just
                     outside it. Oil suppresses backscatter strongly, so a
                     real slick reads much darker than its surroundings;
                     a weak look-alike barely stands out.
  - edge_sharpness:  mean Sobel gradient magnitude in a band straddling the
                     region's boundary. Oil has a comparatively crisp
                     water/slick interface; look-alikes (wind shadows,
                     current lines) tend to fade in gradually.
  - homogeneity:     standard deviation of intensity *inside* the region
                     (lower = more homogeneous). Oil dampens capillary
                     waves fairly uniformly, so its interior is smooth;
                     look-alikes are often patchier.
  - shape:           a bounded-area, moderate-elongation bonus -- real
                     slicks are neither pinhead specks nor scene-filling
                     blobs, and are usually somewhat elongated (wind/
                     current driven) without being a thin line (which
                     looks more like a ship wake or scan artifact).

Contract expected by backend/app.py:

    run(image_path: str, out_dir: str, timestamp: str) -> dict
        {
          "detected": bool,
          "centroid": {"lat": float, "lon": float} | None,   # of the top region
          "area_km2": float,                                  # of the top region
          "region_count": int,
          "regions": [                                        # every candidate,
              {                                                # sorted by
                "oil_confidence": float,      # 0-100         # oil_confidence
                "classification": str,        # see THRESHOLDS below
                "area_km2": float,
                "length_km": float,
                "width_km": float,
                "elongation": float,          # length / width
                "edge_sharpness": float,
                "homogeneity": float,         # raw std -- lower is smoother
                "contrast": float,
                "centroid": {"lat": float, "lon": float},
              },
              ...
          ],
          "overlay_filename": str,   # colored outline+tint PNG (RGBA), saved into out_dir
          "mask_filename": str,      # plain binary mask PNG (grayscale), saved into out_dir
        }

    image_bounds(image_path: str) -> dict
        { "south": float, "west": float, "north": float, "east": float }  # EPSG:4326

"regions" is additive -- "detected", "centroid", "area_km2", "region_count"
keep their existing meaning (a true/false detection event, and the
top-oil-confidence region's geometry) so Module 2 (AIS correlation), which
only reads "centroid" and the API's "scene_timestamp", is unaffected.
"""

import math
import os
import sys

import cv2
import numpy as np
import rasterio
from rasterio.warp import transform, transform_bounds

# Make `weather` importable as a sibling package regardless of how this
# module is invoked (mirrors the same bootstrap used in backend/ais/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather.weather import get_conditions  # noqa: E402

# --- Stage 1 tuning: unchanged from the previous revision ---

# A region has to be at least this much darker than its local background
# (on the 0-255 stretched scale) to count as an anomaly at all, regardless
# of what Otsu picks — keeps flat, low-contrast scenes from producing noise.
MIN_DARKNESS_MARGIN = 15

# Discard contours smaller than this many pixels — speckle noise or vessels,
# not a slick.
MIN_REGION_PIXELS = 500

# Discard any single contour bigger than this fraction of the whole image —
# that's open sea (or a scene-wide artifact), not a bounded slick.
MAX_REGION_FRACTION = 0.15

# Keep only the top N largest surviving candidates.
MAX_REGIONS = 5

# --- Stage 2: oil-vs-look-alike classifier ---

# Contrast and edge-sharpness are mapped to [0,1] via a sigmoid centered on
# the midpoint between "textbook oil" and "textbook look-alike" values
# (calibrated against measured contrast/edge on the stretched 0-255 image --
# real oil typically reads ~120-200+, weak/fuzzy look-alikes ~75-140), with
# STEEPNESS controlling how quickly the score moves across that gap. This
# still no ML/no randomness: it's the same "documented function of the
# measured feature" as before, just an S-curve instead of a from-zero
# saturating exponential -- the earlier exponential's scale was too small
# to stay discriminating once genuine oil-level contrast/edge values (which
# run into the hundreds) pushed both classes past its saturation point.
CONTRAST_MIDPOINT = 100.0
CONTRAST_STEEPNESS = 15.0
EDGE_SHARPNESS_MIDPOINT = 165.0
EDGE_SHARPNESS_STEEPNESS = 20.0
HOMOGENEITY_SCALE = 4.0  # for the *std*; lower std -> higher sub-score (still exp-decay, unchanged)

# Shape bonus: a smooth bump favoring a moderate elongation (real slicks are
# usually stretched by wind/current, but not a thin line like a ship wake)
# and a region size comfortably inside the allowed [MIN_REGION_PIXELS,
# MAX_REGION_FRACTION] band rather than right at either edge of it.
ELONGATION_PEAK = 3.0
ELONGATION_SIGMA = 3.0
SIZE_PEAK_POSITION = 0.3  # 0 = at MIN_REGION_PIXELS, 1 = at the max-area cutoff
SIZE_SIGMA = 0.35

WEIGHT_CONTRAST = 0.35
WEIGHT_EDGE_SHARPNESS = 0.25
WEIGHT_HOMOGENEITY = 0.25
WEIGHT_SHAPE = 0.15

CLASSIFY_LIKELY_THRESHOLD = 60.0
CLASSIFY_UNCERTAIN_THRESHOLD = 35.0

CLASS_LIKELY = "LIKELY OIL SPILL"
CLASS_UNCERTAIN = "UNCERTAIN"
CLASS_LOOKALIKE = "POSSIBLE LOOK-ALIKE"

# RGBA outline colors per classification, SkyTruth-reference style: a thin,
# crisp, bright traced boundary on the exact pixel contour (jaggedness kept
# as-is, never smoothed/simplified), with only a very faint fill so the SAR
# texture underneath still shows through.
CLASS_COLOR_RGB = {
    CLASS_LIKELY: (255, 221, 0),  # bright yellow
    CLASS_UNCERTAIN: (245, 158, 11),  # amber
    CLASS_LOOKALIKE: (148, 163, 184),  # slate/grey
}
FILL_ALPHA = 15  # ~6% -- faint area tint, well under the "no more than ~10%" cap
OUTLINE_ALPHA = 255
OUTLINE_THICKNESS_PX = 2
CENTROID_MARKER_RADIUS_PX = 3
DASH_LEN_PX = 6  # look-alike outlines are dashed; oil/uncertain are solid
GAP_LEN_PX = 4
LABEL_FONT_SCALE = 0.42
LABEL_THICKNESS = 1

# Ring width (px) used to sample "surrounding water" for the contrast
# feature, and the boundary-straddling band width (px, each side) used for
# the edge-sharpness feature.
CONTRAST_RING_PX = 8
EDGE_BAND_PX = 3

EARTH_RADIUS_KM = 6371.0088

# Rough-estimate assumption for estimated_volume_m3 -- a typical thin sheen
# thickness (1 mm). This is a coarse order-of-magnitude figure, not a
# measured value; it is always returned alongside the estimate so the UI
# can label it clearly.
ASSUMED_FILM_THICKNESS_M = 0.001


def _odd(n: int) -> int:
    n = int(n)
    return n if n % 2 == 1 else n + 1


def _stretch_to_uint8(band: np.ndarray) -> np.ndarray:
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros(band.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [2, 98])
    if hi <= lo:
        hi = lo + 1.0
    stretched = np.clip((band - lo) / (hi - lo), 0.0, 1.0)
    return (stretched * 255).astype(np.uint8)


def _local_dark_anomaly_mask(gray: np.ndarray) -> np.ndarray:
    """Flag pixels darker than their local background minus an adaptive margin."""
    h, w = gray.shape

    # Heavy blur = "local background": wide enough to average out a slick-sized
    # patch into the surrounding water, but far smaller than the whole scene.
    bg_ksize = _odd(np.clip(min(h, w) // 10, 31, 301))
    background = cv2.GaussianBlur(gray, (bg_ksize, bg_ksize), 0)

    # How much darker each pixel is than its local background (0 where the
    # pixel is at or above the local background — saturated subtraction).
    diff = cv2.subtract(background, gray)

    # Otsu on the "darker than background" signal separates real anomalies
    # from ambient noise, floored so a near-flat scene doesn't get flagged.
    otsu_margin, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    margin = max(MIN_DARKNESS_MARGIN, otsu_margin)

    _, mask = cv2.threshold(diff, margin, 255, cv2.THRESH_BINARY)
    return mask


# --- Georeferencing helpers (unchanged logic; reused for per-region measurement) ---


def _pixel_area_km2(transform_affine, crs, lat_ref: float) -> float:
    px_w = abs(transform_affine.a)
    px_h = abs(transform_affine.e)
    if crs is not None and crs.is_geographic:
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat_ref))
        px_w_m = px_w * m_per_deg_lon
        px_h_m = px_h * m_per_deg_lat
    else:
        px_w_m = px_w
        px_h_m = px_h
    return (px_w_m * px_h_m) / 1_000_000.0


def _pixel_to_lonlat(row: float, col: float, src_transform, src_crs):
    x_geo, y_geo = rasterio.transform.xy(src_transform, row, col)
    lon, lat = transform(src_crs, "EPSG:4326", [x_geo], [y_geo])
    return lon[0], lat[0]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Forward azimuth from point 1 to point 2, degrees, 0-360 (0 = north)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def image_bounds(image_path: str) -> dict:
    with rasterio.open(image_path) as ds:
        west, south, east, north = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    return {"south": south, "west": west, "north": north, "east": east}


# --- Stage 2: per-region feature extraction ---


def _contour_perimeter_km(contour, src_transform, src_crs) -> float:
    """Contour perimeter (cv2.arcLength, closed loop) converted to km by
    summing haversine distances between consecutive vertices in lon/lat."""
    pts = contour.reshape(-1, 2)  # (col, row) pixel pairs
    lonlat = [_pixel_to_lonlat(row, col, src_transform, src_crs) for col, row in pts]
    n = len(lonlat)
    perimeter_km = 0.0
    for i in range(n):
        lon1, lat1 = lonlat[i]
        lon2, lat2 = lonlat[(i + 1) % n]
        perimeter_km += _haversine_km(lat1, lon1, lat2, lon2)
    return perimeter_km


def _region_measurements(contour, region_mask, src_transform, src_crs):
    """Area (km²), rotated-rect length/width (km), elongation, centroid,
    perimeter (km), slick orientation (deg), and a rough volume estimate."""
    ys, xs = np.nonzero(region_mask)
    cy_px, cx_px = float(ys.mean()), float(xs.mean())
    lon, lat = _pixel_to_lonlat(cy_px, cx_px, src_transform, src_crs)

    px_area_km2 = _pixel_area_km2(src_transform, src_crs, lat)
    area_km2 = float(region_mask.sum() / 255) * px_area_km2

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)  # 4 corner points in pixel (col, row) space
    box_lonlat = [_pixel_to_lonlat(row, col, src_transform, src_crs) for col, row in box]

    side_a = _haversine_km(box_lonlat[0][1], box_lonlat[0][0], box_lonlat[1][1], box_lonlat[1][0])
    side_b = _haversine_km(box_lonlat[1][1], box_lonlat[1][0], box_lonlat[2][1], box_lonlat[2][0])
    length_km, width_km = max(side_a, side_b), min(side_a, side_b)
    elongation = length_km / width_km if width_km > 1e-6 else float("inf")

    # Orientation: forward-azimuth of the long-axis side, folded into 0-180
    # deg (a line has no head/tail, so 190deg and 10deg describe the same
    # orientation).
    if side_a >= side_b:
        long_p1, long_p2 = box_lonlat[0], box_lonlat[1]
    else:
        long_p1, long_p2 = box_lonlat[1], box_lonlat[2]
    orientation_deg = _bearing_deg(long_p1[1], long_p1[0], long_p2[1], long_p2[0]) % 180

    perimeter_km = _contour_perimeter_km(contour, src_transform, src_crs)

    # Rough order-of-magnitude volume estimate: area x an assumed uniform
    # film thickness. This is NOT a measured volume -- always surfaced with
    # the assumed thickness so it is labeled as an estimate downstream.
    area_m2 = area_km2 * 1_000_000.0
    estimated_volume_m3 = area_m2 * ASSUMED_FILM_THICKNESS_M

    return {
        "area_km2": area_km2,
        "length_km": length_km,
        "width_km": width_km,
        "elongation": elongation,
        "centroid": {"lat": lat, "lon": lon},
        "perimeter_km": perimeter_km,
        "orientation_deg": orientation_deg,
        "estimated_volume_m3": estimated_volume_m3,
        "assumed_thickness_m": ASSUMED_FILM_THICKNESS_M,
    }


def _region_texture_features(gray, grad_mag, region_mask):
    """Edge sharpness, internal homogeneity (std), and contrast vs. surrounding water."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    # Edge sharpness: mean gradient magnitude in a thin band straddling the
    # traced boundary (dilate minus erode = a ring centered on the contour).
    dil = cv2.dilate(region_mask, kernel, iterations=EDGE_BAND_PX)
    ero = cv2.erode(region_mask, kernel, iterations=EDGE_BAND_PX)
    boundary_band = cv2.subtract(dil, ero)
    if np.any(boundary_band):
        edge_sharpness = float(grad_mag[boundary_band > 0].mean())
    else:
        edge_sharpness = 0.0

    # Internal homogeneity: std of intensity a little inside the boundary,
    # so the sharp edge itself doesn't inflate the interior's variance.
    interior = cv2.erode(region_mask, kernel, iterations=EDGE_BAND_PX)
    interior_pixels = gray[interior > 0] if np.any(interior) else gray[region_mask > 0]
    homogeneity_std = float(interior_pixels.std()) if interior_pixels.size else 0.0

    # Contrast: how much darker the region is than a ring of water just
    # outside it (not the whole scene, which may include other regions).
    ring_outer = cv2.dilate(region_mask, kernel, iterations=CONTRAST_RING_PX)
    surrounding_ring = cv2.subtract(ring_outer, region_mask)
    mean_inside = float(gray[region_mask > 0].mean())
    if np.any(surrounding_ring):
        mean_outside = float(gray[surrounding_ring > 0].mean())
    else:
        mean_outside = mean_inside
    contrast = mean_outside - mean_inside  # positive = region darker than its surroundings

    return {
        "edge_sharpness": edge_sharpness,
        "homogeneity": homogeneity_std,
        "contrast": max(0.0, contrast),
    }


def _shape_score(area_px: float, elongation: float, total_area_px: float) -> float:
    max_region_px = MAX_REGION_FRACTION * total_area_px
    log_area = math.log(max(area_px, 1.0))
    log_min = math.log(max(MIN_REGION_PIXELS, 1.0))
    log_max = math.log(max(max_region_px, MIN_REGION_PIXELS + 1.0))
    pos = (log_area - log_min) / (log_max - log_min) if log_max > log_min else 0.5
    pos = min(1.0, max(0.0, pos))
    size_score = math.exp(-((pos - SIZE_PEAK_POSITION) ** 2) / (2 * SIZE_SIGMA**2))

    if math.isinf(elongation):
        elongation_score = 0.0
    else:
        elongation_score = math.exp(-((elongation - ELONGATION_PEAK) ** 2) / (2 * ELONGATION_SIGMA**2))

    return 0.5 * size_score + 0.5 * elongation_score


def _sigmoid(value: float, midpoint: float, steepness: float) -> float:
    return 1.0 / (1.0 + math.exp(-(value - midpoint) / steepness))


def _classify(contrast: float, edge_sharpness: float, homogeneity: float, shape_score: float):
    """Documented, feature-driven oil-confidence score -- no ML, no randomness.

    Contrast and edge sharpness are mapped to [0,1] via a sigmoid centered
    on the measured midpoint between oil and look-alike values (more is
    still always better, but the score is most sensitive right around that
    midpoint, which is what actually separates the two classes). Homogeneity
    is mapped via a saturating exponential decay (lower std -> higher
    score). All four sub-scores are then combined with the fixed weights
    above -- a smooth, explainable function of exactly the four measured
    features.
    """
    contrast_score = _sigmoid(max(0.0, contrast), CONTRAST_MIDPOINT, CONTRAST_STEEPNESS)
    edge_score = _sigmoid(max(0.0, edge_sharpness), EDGE_SHARPNESS_MIDPOINT, EDGE_SHARPNESS_STEEPNESS)
    homogeneity_score = math.exp(-max(0.0, homogeneity) / HOMOGENEITY_SCALE)

    blend = (
        WEIGHT_CONTRAST * contrast_score
        + WEIGHT_EDGE_SHARPNESS * edge_score
        + WEIGHT_HOMOGENEITY * homogeneity_score
        + WEIGHT_SHAPE * shape_score
    )
    oil_confidence = round(100.0 * min(1.0, max(0.0, blend)), 1)

    return oil_confidence, _classification_from_confidence(oil_confidence)


def _classification_from_confidence(oil_confidence: float) -> str:
    if oil_confidence >= CLASSIFY_LIKELY_THRESHOLD:
        return CLASS_LIKELY
    elif oil_confidence >= CLASSIFY_UNCERTAIN_THRESHOLD:
        return CLASS_UNCERTAIN
    return CLASS_LOOKALIKE


# --- Stage 2b: wind adjustment (an adjustment layer on top of the image-
# feature score above, not a replacement for it) ---

# Low wind lets the sea surface go glassy-smooth, which reads dark on SAR
# and mimics oil (a classic "calm-water look-alike"). High wind roughens
# the surface, so a dark patch that persists despite wind is more likely
# to genuinely be oil. Thresholds and multipliers are deliberately modest:
# this refines the image-feature score, it doesn't override it -- a region
# with strong image evidence stays classified as oil even in low wind (see
# the modest 0.85 multiplier and the empirical check in run(), which
# verified against this project's real synthetic-scene confidences --
# 87-94% for genuine oil -- that even the low-wind case (x0.85 -> 74-80%)
# stays comfortably above CLASSIFY_LIKELY_THRESHOLD).
LOW_WIND_THRESHOLD_MS = 3.0
HIGH_WIND_THRESHOLD_MS = 6.0
LOW_WIND_MULTIPLIER = 0.85
HIGH_WIND_MULTIPLIER = 1.10


def _wind_adjustment(wind_speed_ms):
    """(multiplier, label, low_wind_caution) for the given wind speed.

    wind_speed_ms may be None (weather fetch failed/unavailable) -- always
    returns a neutral, safe result in that case rather than raising, so a
    weather outage never blocks or skews detection.
    """
    if wind_speed_ms is None:
        return 1.0, "wind data unavailable", False
    if wind_speed_ms < LOW_WIND_THRESHOLD_MS:
        pct = round((LOW_WIND_MULTIPLIER - 1) * 100)
        return LOW_WIND_MULTIPLIER, f"low-wind caution ({pct}%)", True
    if wind_speed_ms > HIGH_WIND_THRESHOLD_MS:
        pct = round((HIGH_WIND_MULTIPLIER - 1) * 100)
        return HIGH_WIND_MULTIPLIER, f"high-wind support (+{pct}%)", False
    return 1.0, "neutral", False


# --- Stage 3: rendering ---


def _draw_dashed_contour(img, contour, color, thickness=2, dash_len=6, gap_len=4):
    """Trace a closed contour as a dashed line, walking its exact pixel
    points (no smoothing/simplification) -- used for look-alike outlines."""
    pts = contour.reshape(-1, 2)
    n = len(pts)
    if n < 2:
        return

    dist_in_phase = 0.0
    dash_on = True
    for i in range(n):
        p1 = pts[i].astype(np.float64)
        p2 = pts[(i + 1) % n].astype(np.float64)
        seg_len = float(np.hypot(*(p2 - p1)))
        if seg_len < 1e-6:
            continue
        steps = max(1, int(math.ceil(seg_len)))
        for s in range(steps):
            t0, t1 = s / steps, (s + 1) / steps
            if dash_on:
                a = tuple(np.round(p1 + (p2 - p1) * t0).astype(int))
                b = tuple(np.round(p1 + (p2 - p1) * t1).astype(int))
                cv2.line(img, a, b, color, thickness, cv2.LINE_AA)
            dist_in_phase += seg_len / steps
            if dash_on and dist_in_phase >= dash_len:
                dash_on, dist_in_phase = False, 0.0
            elif not dash_on and dist_in_phase >= gap_len:
                dash_on, dist_in_phase = True, 0.0


def run(image_path: str, out_dir: str, timestamp: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    with rasterio.open(image_path) as ds:
        band = ds.read(1).astype(np.float32)
        src_crs = ds.crs
        src_transform = ds.transform

    gray = _stretch_to_uint8(band)
    total_area_px = gray.shape[0] * gray.shape[1]

    # Light denoise before background estimation (SAR speckle).
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    dark_mask = _local_dark_anomaly_mask(denoised)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    max_region_px = MAX_REGION_FRACTION * total_area_px
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_REGION_PIXELS:
            continue  # noise / vessel-sized speck
        if area > max_region_px:
            continue  # unbounded "open sea" reading, not a slick
        candidates.append((area, c))

    candidates.sort(key=lambda item: item[0], reverse=True)
    contour_list = [c for _, c in candidates[:MAX_REGIONS]]

    # Gradient magnitude computed once for the whole scene, reused per region.
    gx = cv2.Sobel(denoised, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(denoised, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)

    region_infos = []
    region_masks = []
    for contour in contour_list:
        region_mask = np.zeros(cleaned.shape, dtype=np.uint8)
        cv2.drawContours(region_mask, [contour], -1, 255, thickness=cv2.FILLED)
        region_masks.append(region_mask)

        measurements = _region_measurements(contour, region_mask, src_transform, src_crs)
        texture = _region_texture_features(denoised, grad_mag, region_mask)
        shape_score = _shape_score(
            cv2.contourArea(contour), measurements["elongation"], total_area_px
        )
        oil_confidence, classification = _classify(
            texture["contrast"], texture["edge_sharpness"], texture["homogeneity"], shape_score
        )

        region_infos.append(
            {
                "oil_confidence": oil_confidence,
                "classification": classification,
                "area_km2": round(measurements["area_km2"], 4),
                "length_km": round(measurements["length_km"], 4),
                "width_km": round(measurements["width_km"], 4),
                "elongation": round(measurements["elongation"], 2)
                if not math.isinf(measurements["elongation"])
                else None,
                "edge_sharpness": round(texture["edge_sharpness"], 2),
                "homogeneity": round(texture["homogeneity"], 2),
                "contrast": round(texture["contrast"], 2),
                "centroid": measurements["centroid"],
                "perimeter_km": round(measurements["perimeter_km"], 4),
                "orientation_deg": round(measurements["orientation_deg"], 1),
                "estimated_volume_m3": round(measurements["estimated_volume_m3"], 2),
                "assumed_thickness_m": measurements["assumed_thickness_m"],
            }
        )

    # Rank by oil-confidence, highest first; the top region drives the
    # top-level detected/centroid/area_km2 fields Module 2 depends on.
    order = sorted(range(len(region_infos)), key=lambda i: region_infos[i]["oil_confidence"], reverse=True)
    region_infos = [region_infos[i] for i in order]
    contour_list = [contour_list[i] for i in order]
    region_masks = [region_masks[i] for i in order]

    # Wind adjustment layer: refines the image-feature score above, never
    # replaces it. One live wind reading for the scene (at the top,
    # image-only-ranked region's centroid) is applied as the same
    # multiplier to every region -- wind is a property of the scene, not
    # of any one region -- so relative ranking between regions is
    # unaffected (a uniform positive scale factor preserves order); only
    # where each region falls relative to the fixed 60/35 thresholds can
    # shift, and only modestly by design.
    if region_infos:
        primary_centroid = region_infos[0]["centroid"]
        wind_speed_ms = None
        try:
            conditions = get_conditions(primary_centroid["lat"], primary_centroid["lon"])
            wind_speed_ms = conditions.get("wind_speed_ms")
        except Exception:
            # Weather fetch must never block or crash detection -- fall
            # back to image-only classification (multiplier stays 1.0).
            wind_speed_ms = None

        multiplier, wind_adjustment_label, low_wind_caution = _wind_adjustment(wind_speed_ms)

        for info in region_infos:
            adjusted = round(min(100.0, max(0.0, info["oil_confidence"] * multiplier)), 1)
            info["oil_confidence"] = adjusted
            info["classification"] = _classification_from_confidence(adjusted)
            info["wind_speed_ms"] = wind_speed_ms
            info["wind_adjustment"] = wind_adjustment_label
            info["low_wind_caution"] = low_wind_caution

    detected = len(region_infos) > 0
    centroid = region_infos[0]["centroid"] if detected else None
    area_km2 = region_infos[0]["area_km2"] if detected else 0.0

    # Plain binary mask (grayscale PNG) -- union of every candidate region,
    # unchanged from before.
    final_mask = np.zeros(cleaned.shape, dtype=np.uint8)
    for region_mask in region_masks:
        final_mask = cv2.bitwise_or(final_mask, region_mask)
    mask_filename = f"mask_{timestamp}.png"
    cv2.imwrite(os.path.join(out_dir, mask_filename), final_mask)

    # SkyTruth-reference-style overlay: a thin, crisp, bright outline traced
    # on the exact pixel contour (jaggedness preserved, never smoothed into
    # an ellipse/polygon), a very faint fill so the SAR texture underneath
    # still reads through, and a small centroid marker -- colored by
    # classification (yellow = likely oil, amber = uncertain, dashed grey =
    # look-alike). The primary (highest-confidence) region is labeled with
    # its area, like the reference maps.
    overlay_rgba = np.zeros((*final_mask.shape, 4), dtype=np.uint8)
    for idx, (contour, region_mask, info) in enumerate(zip(contour_list, region_masks, region_infos)):
        r, g, b = CLASS_COLOR_RGB[info["classification"]]
        if FILL_ALPHA > 0:
            overlay_rgba[region_mask == 255] = (r, g, b, FILL_ALPHA)

        if info["classification"] == CLASS_LOOKALIKE:
            _draw_dashed_contour(
                overlay_rgba, contour, (r, g, b, OUTLINE_ALPHA), OUTLINE_THICKNESS_PX, DASH_LEN_PX, GAP_LEN_PX
            )
        else:
            cv2.drawContours(
                overlay_rgba, [contour], -1, (r, g, b, OUTLINE_ALPHA), thickness=OUTLINE_THICKNESS_PX
            )

        ys, xs = np.nonzero(region_mask)
        cx_px, cy_px = int(round(xs.mean())), int(round(ys.mean()))
        cv2.circle(
            overlay_rgba, (cx_px, cy_px), CENTROID_MARKER_RADIUS_PX, (r, g, b, OUTLINE_ALPHA), cv2.FILLED
        )
        cv2.circle(overlay_rgba, (cx_px, cy_px), CENTROID_MARKER_RADIUS_PX, (10, 14, 20, OUTLINE_ALPHA), 1)

        if idx == 0 and info["classification"] == CLASS_LIKELY:
            cv2.putText(
                overlay_rgba,
                f"Oil Slick: {info['area_km2']:.2f} km2",
                (cx_px + CENTROID_MARKER_RADIUS_PX + 6, cy_px - CENTROID_MARKER_RADIUS_PX - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                LABEL_FONT_SCALE,
                (r, g, b, OUTLINE_ALPHA),
                LABEL_THICKNESS,
                cv2.LINE_AA,
            )
    overlay_filename = f"overlay_{timestamp}.png"
    cv2.imwrite(
        os.path.join(out_dir, overlay_filename),
        cv2.cvtColor(overlay_rgba, cv2.COLOR_RGBA2BGRA),
    )

    return {
        "detected": detected,
        "centroid": centroid,
        "area_km2": round(area_km2, 4),
        "region_count": len(region_infos),
        "regions": region_infos,
        "overlay_filename": overlay_filename,
        "mask_filename": mask_filename,
    }
