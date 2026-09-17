"""
ML-based oil-spill detection: a trained U-Net segmentation model, offered
as an ALTERNATIVE to the classic-OpenCV detector in cv_detect.py -- never
a replacement. backend/app.py exposes this via a separate endpoint
(POST /api/detect_ml); /api/detect (cv_detect.run) is untouched.

The U-Net (DoubleConv blocks; encoder 1->32->64->128->256 with maxpool;
decoder with ConvTranspose2d + skip connections; final 1x1 conv to 1
channel) was trained on 256x256 grayscale SAR chips normalized to 0-1, and
its saved weights (sindva_unet_oilspill.pth, alongside this file) were
reverse-engineered layer-by-layer from the checkpoint's own state_dict
keys/shapes -- loading it below with strict=True is itself the proof the
architecture here matches training exactly ("<All keys matched
successfully>"), rather than something asserted without evidence.

Preprocessing below matches training EXACTLY, and deliberately does NOT
reuse cv_detect.py's _stretch_to_uint8 (a percentile-contrast-stretch
heuristic tuned for the classic detector's dark-anomaly algorithm, not
what the model was trained on): convert to grayscale ("L"), resize to
256x256, divide by 255.0. Using the stretch here was the actual bug behind
earlier "giant blob" predictions -- feeding the model pixel statistics it
never saw in training. Any image format Pillow can open (png/jpg/jpeg/tif/
tiff) is loaded the same way, uniformly.

Everything downstream of the model's raw mask is deliberately the SAME
code the classic detector uses -- per-region measurements (area/length/
width/perimeter/orientation/volume estimate) and the SkyTruth-style
overlay renderer are all imported from cv_detect.py, not reimplemented, so
an ML-detected region's measurements are computed identically to a
classic-CV one and the two are visually consistent on the map.
Georeferencing (pixel -> lon/lat) is the one place ml_detect.py adds its
own logic beyond what cv_detect.py needs: a plain PNG/JPG upload has no
embedded geo metadata, so _read_georeferencing() below falls back to a
synthetic bounding box over the same Visakhapatnam bay the bundled demo
scene uses, rather than crashing -- the SAME downstream geo helpers then
run unmodified against that synthetic transform+CRS exactly as they would
against a real one.

The only genuinely different piece from the classic detector, besides mask
production itself, is *how oil_confidence is derived* (the model's own
mean predicted probability inside a region, instead of the classic
detector's four-feature texture score -- there is no equivalent texture-
based "look-alike" classifier here because the U-Net was trained to
predict oil directly).
"""

import math
import os
import sys

import cv2
import numpy as np
import rasterio
import torch
import torch.nn as nn
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import transform_bounds

# Same bootstrap pattern as cv_detect.py, ais/, etc.: make sibling
# top-level packages (weather/) importable regardless of how this module
# is invoked, and allow `from detection.cv_detect import ...` to resolve
# whether backend/ or backend/detection/ is on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.cv_detect import (  # noqa: E402
    CENTROID_MARKER_RADIUS_PX,
    CLASS_COLOR_RGB,
    CLASS_LIKELY,
    CLASS_LOOKALIKE,
    DASH_LEN_PX,
    FILL_ALPHA,
    GAP_LEN_PX,
    LABEL_FONT_SCALE,
    LABEL_THICKNESS,
    MAX_REGIONS,
    MIN_REGION_PIXELS,
    OUTLINE_ALPHA,
    OUTLINE_THICKNESS_PX,
    _classification_from_confidence,
    _draw_dashed_contour,
    _region_measurements,
    _region_texture_features,
    _wind_adjustment,
)
from weather.weather import get_conditions  # noqa: E402

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sindva_unet_oilspill.pth")
MODEL_INPUT_SIZE = 256
MASK_THRESHOLD = 0.5

DETECTION_METHOD_ML = "AI / U-Net"

# File types the ML path accepts (the classic-CV /api/detect endpoint is
# untouched and keeps its own, separate .tif/.tiff-only expectation).
ACCEPTED_EXTENSIONS = (".tif", ".tiff", ".png", ".jpg", ".jpeg")

# Same size floor as the classic detector, so ML-side speckle/noise blobs
# are filtered out the same way (not a shared code path, just a shared,
# deliberately identical constant -- imported, not redefined).
_MIN_REGION_PIXELS = MIN_REGION_PIXELS

# Cleanup thresholds for the model's raw binary mask (see _clean_mask()):
# a component smaller than this many pixels is noise, not a candidate
# region; a mask still covering more than this fraction of the frame after
# noise removal reads as an unfocused blob rather than a genuine slick, so
# only its single largest component is kept.
_MAX_AREA_FRACTION = 0.40

# Fallback bounding box (EPSG:4326) for uploads with no embedded
# georeferencing (a plain PNG/JPG, or a TIFF without geo metadata) -- the
# same Visakhapatnam bay extent as the bundled synthetic demo scene (see
# backend/make_synthetic.py's WEST/EAST/SOUTH/NORTH), so a non-georeferenced
# upload still gets a plausible, consistent location instead of crashing.
_FALLBACK_WEST, _FALLBACK_EAST = 83.28, 83.42
_FALLBACK_SOUTH, _FALLBACK_NORTH = 17.60, 17.75


# --- U-Net architecture (verbatim match to sindva_unet_oilspill.pth) ---


class DoubleConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.c = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.c(x)


class UNet(nn.Module):
    def __init__(self, in_channels: int = 1, out_channels: int = 1):
        super().__init__()
        self.pool = nn.MaxPool2d(2)

        self.d1 = DoubleConv(in_channels, 32)
        self.d2 = DoubleConv(32, 64)
        self.d3 = DoubleConv(64, 128)
        self.d4 = DoubleConv(128, 256)

        self.u3 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.c3 = DoubleConv(256, 128)
        self.u2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.c2 = DoubleConv(128, 64)
        self.u1 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.c1 = DoubleConv(64, 32)

        self.out = nn.Conv2d(32, out_channels, kernel_size=1)

    def forward(self, x):
        x1 = self.d1(x)
        x2 = self.d2(self.pool(x1))
        x3 = self.d3(self.pool(x2))
        x4 = self.d4(self.pool(x3))

        x = self.u3(x4)
        x = self.c3(torch.cat([x, x3], dim=1))
        x = self.u2(x)
        x = self.c2(torch.cat([x, x2], dim=1))
        x = self.u1(x)
        x = self.c1(torch.cat([x, x1], dim=1))

        return self.out(x)


# Lazy-loaded singleton -- the ~7.4 MB weights file is read from disk once
# per process, not once per request.
_model: UNet | None = None


def _get_model() -> UNet:
    global _model
    if _model is None:
        model = UNet()
        state_dict = torch.load(WEIGHTS_PATH, map_location="cpu")
        model.load_state_dict(state_dict)  # strict=True (default) -- any
        # architecture mismatch surfaces immediately and loudly here,
        # rather than silently loading partial/garbage weights.
        model.eval()
        _model = model
    return _model


def _load_grayscale_uint8(image_path: str) -> np.ndarray:
    """Load ANY image format Pillow supports (png/jpg/jpeg/tif/tiff) and
    convert to 8-bit grayscale EXACTLY as training did: Pillow's standard
    "L" conversion, at the image's own original resolution -- no
    percentile stretching or other contrast heuristic (that mismatch,
    reusing cv_detect's SAR-anomaly-tuned stretch, was the actual cause of
    earlier "giant blob" predictions)."""
    with Image.open(image_path) as img:
        return np.array(img.convert("L"), dtype=np.uint8)


def _read_georeferencing(image_path: str, image_shape: tuple):
    """(transform, crs) for pixel -> lon/lat conversion. Real georeferencing
    when the file is a genuinely geo-tagged raster (a proper GeoTIFF);
    otherwise a synthetic bounding box over the Visakhapatnam bay (see
    _FALLBACK_* above), so a plain PNG/JPG upload -- or a TIFF with no geo
    metadata -- still produces usable (if approximate) coordinates via the
    exact same downstream geo helpers cv_detect.py uses, rather than
    crashing."""
    try:
        with rasterio.open(image_path) as ds:
            if ds.crs is not None:
                return ds.transform, ds.crs
    except rasterio.errors.RasterioIOError:
        pass

    h, w = image_shape
    transform = from_bounds(_FALLBACK_WEST, _FALLBACK_SOUTH, _FALLBACK_EAST, _FALLBACK_NORTH, w, h)
    return transform, CRS.from_epsg(4326)


def image_bounds(image_path: str) -> dict:
    """Same shape/contract as cv_detect.image_bounds(), but falls back to
    the synthetic Visakhapatnam-bay box (see _read_georeferencing) instead
    of raising when the upload has no real georeferencing."""
    gray = _load_grayscale_uint8(image_path)
    h, w = gray.shape
    transform, crs = _read_georeferencing(image_path, (h, w))
    west, south, east, north = array_bounds(h, w, transform)
    west, south, east, north = transform_bounds(crs, "EPSG:4326", west, south, east, north)
    return {"south": south, "west": west, "north": north, "east": east}


def _run_inference(gray_uint8: np.ndarray):
    """gray_uint8: original-resolution 0-255 grayscale, loaded by
    _load_grayscale_uint8() -- i.e. exactly what training used, not
    cv_detect's contrast-stretched band. Returns (binary_mask, prob_map),
    both resized back to the ORIGINAL resolution -- binary_mask is 0/255
    uint8, prob_map is the model's raw 0-1 probability per pixel (used
    only to score each region's oil_confidence afterward).

    Preprocessing here matches training exactly: resize to 256x256,
    normalize by dividing by 255.0, sigmoid, threshold at 0.5."""
    h, w = gray_uint8.shape
    resized = cv2.resize(gray_uint8, (MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    tensor = torch.from_numpy(normalized)[None, None, :, :]  # (1, 1, 256, 256)

    model = _get_model()
    with torch.no_grad():
        logits = model(tensor)
        probs_256 = torch.sigmoid(logits)[0, 0].numpy().astype(np.float32)  # (256, 256), 0-1

    binary_256 = (probs_256 >= MASK_THRESHOLD).astype(np.uint8) * 255
    mask = cv2.resize(binary_256, (w, h), interpolation=cv2.INTER_NEAREST)
    prob_map = cv2.resize(probs_256, (w, h), interpolation=cv2.INTER_LINEAR)
    return mask, prob_map


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    """Binary mask cleanup via connected components: drop specks smaller
    than _MIN_REGION_PIXELS (noise, not a candidate spill), then, if what's
    left still covers more than _MAX_AREA_FRACTION of the frame, keep only
    the single largest surviving component -- a diffuse prediction that
    size is reading as an unfocused blob rather than a genuine slick, so
    this keeps the result a focused shape instead of the whole frame."""
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total_px = mask.shape[0] * mask.shape[1]

    components = [(i, int(stats[i, cv2.CC_STAT_AREA])) for i in range(1, num_labels)]
    components = [(i, area) for i, area in components if area >= _MIN_REGION_PIXELS]
    if not components:
        return np.zeros_like(mask)

    components.sort(key=lambda item: item[1], reverse=True)

    if sum(area for _, area in components) > _MAX_AREA_FRACTION * total_px:
        components = components[:1]

    cleaned = np.zeros_like(mask)
    for i, _ in components:
        cleaned[labels == i] = 255
    return cleaned


def detect_ml(image_path: str, out_dir: str, timestamp: str) -> dict:
    """Same contract as cv_detect.run() -- see that module's docstring for
    the full return shape. Drop-in interchangeable with it from
    backend/app.py's point of view. Accepts any format in
    ACCEPTED_EXTENSIONS (png/jpg/jpeg/tif/tiff)."""
    os.makedirs(out_dir, exist_ok=True)

    gray = _load_grayscale_uint8(image_path)
    src_transform, src_crs = _read_georeferencing(image_path, gray.shape)

    mask, prob_map = _run_inference(gray)

    # Light morphological cleanup first (smooth speckly edges, close small
    # gaps -- same purpose as cv_detect's own use of this, lighter since
    # the model's mask is already a learned segmentation, not a raw
    # thresholded anomaly map), then connected-components cleanup: drop
    # noise specks and, if the prediction is still an unfocused blob,
    # focus down to its largest component (see _clean_mask()).
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
    cleaned = _clean_mask(cleaned)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [(cv2.contourArea(c), c) for c in contours if cv2.contourArea(c) >= _MIN_REGION_PIXELS]
    candidates.sort(key=lambda item: item[0], reverse=True)
    contour_list = [c for _, c in candidates[:MAX_REGIONS]]

    # Gradient magnitude for the texture stats below -- same recipe as
    # cv_detect.run(), computed once and reused per region.
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)

    region_infos = []
    region_masks = []
    for contour in contour_list:
        region_mask = np.zeros(cleaned.shape, dtype=np.uint8)
        cv2.drawContours(region_mask, [contour], -1, 255, thickness=cv2.FILLED)
        region_masks.append(region_mask)

        # Geo/area measurements: the EXACT same helper cv_detect.run() uses,
        # imported (not reimplemented) -- coordinates and measurements are
        # computed identically for an ML-detected region.
        measurements = _region_measurements(contour, region_mask, src_transform, src_crs)

        # Texture stats are informational here (unlike the classic
        # detector, they do not drive oil_confidence below) -- included so
        # the frontend's existing region fields are populated the same way.
        texture = _region_texture_features(gray, grad_mag, region_mask)

        # oil_confidence: the model's own mean predicted probability inside
        # this region -- this IS the ML classifier, there is no separate
        # texture-based look-alike discrimination step to reuse or
        # reimplement (the model was trained to predict oil directly).
        mean_prob = float(prob_map[region_mask > 0].mean()) if np.any(region_mask) else 0.0
        oil_confidence = round(100.0 * min(1.0, max(0.0, mean_prob)), 1)
        classification = _classification_from_confidence(oil_confidence)

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

    order = sorted(range(len(region_infos)), key=lambda i: region_infos[i]["oil_confidence"], reverse=True)
    region_infos = [region_infos[i] for i in order]
    contour_list = [contour_list[i] for i in order]
    region_masks = [region_masks[i] for i in order]

    # Same wind-adjustment layer as the classic detector (same imported
    # function, same thresholds/multipliers) -- an outage-safe refinement
    # on top of the model's own score, never a replacement for it.
    if region_infos:
        primary_centroid = region_infos[0]["centroid"]
        wind_speed_ms = None
        try:
            conditions = get_conditions(primary_centroid["lat"], primary_centroid["lon"])
            wind_speed_ms = conditions.get("wind_speed_ms")
        except Exception:
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

    final_mask = np.zeros(cleaned.shape, dtype=np.uint8)
    for region_mask in region_masks:
        final_mask = cv2.bitwise_or(final_mask, region_mask)
    mask_filename = f"ml_mask_{timestamp}.png"
    cv2.imwrite(os.path.join(out_dir, mask_filename), final_mask)

    # Overlay rendering: the SAME style constants and dashed-contour helper
    # cv_detect.run() uses, imported rather than reimplemented, so an
    # ML-detected overlay is visually indistinguishable in style from a
    # classic-CV one (only the traced shapes differ, because the mask does).
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
                f"AI Oil Slick: {info['area_km2']:.2f} km2",
                (cx_px + CENTROID_MARKER_RADIUS_PX + 6, cy_px - CENTROID_MARKER_RADIUS_PX - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                LABEL_FONT_SCALE,
                (r, g, b, OUTLINE_ALPHA),
                LABEL_THICKNESS,
                cv2.LINE_AA,
            )
    overlay_filename = f"ml_overlay_{timestamp}.png"
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
