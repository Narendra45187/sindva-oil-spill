"""
Synthetic open-water SAR scene for the Module 2 demo, and for demonstrating
Module 1's oil-vs-look-alike classifier.

The real Sentinel-1 scene's spill sits on the coastline, where no vessel
track can realistically pass through it -- AIS correlation there is
necessarily weak. This script generates a synthetic scene with the same
statistical character as SAR imagery (dark speckled sea, bright vessel
returns) but with its oil-spill signature placed out in open water, so a
vessel can genuinely transit through it and the attribution story works
end-to-end. It also seeds two look-alike dark patches -- low-wind/biogenic
style anomalies that are dark but not oil -- so the classifier has
something real to reject.

    py -3.12 backend/make_synthetic.py

Writes backend/data/images/vizag_synthetic.tiff -- a single-band 32-bit
float GeoTIFF, EPSG:4326, georeferenced over the Visakhapatnam bay
(lng 83.28-83.42, lat 17.60-17.75). Does not touch backend/detection/ or
backend/ais/ -- this only produces a new input image for the existing,
unmodified detection and correlation pipeline to run against.
"""

import os

import cv2
import numpy as np
import rasterio
from rasterio.transform import from_origin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "images", "vizag_synthetic.tiff")

# Scene bounds (EPSG:4326) -- open bay, no coastline in frame.
WEST, EAST = 83.28, 83.42
SOUTH, NORTH = 17.60, 17.75
HEIGHT, WIDTH = 500, 500

# Two dark, sharp-edged, smooth-interior spill patches -- real oil, well out
# in the bay. Their shape is a branching, elongated "slick body with
# tendrils" (see _branching_slick_mask): a wandering main spine with a
# couple of thinner branches splitting off at angles, built from many
# overlapping circles of varying radius. The darkening itself is still a
# hard 0/1 cutoff with no blur, so the edge stays physically sharp even
# though its path is complex and jagged.
#
# Module 1's detector estimates *local* background via a wide Gaussian blur
# (sigma ~8px for this image size) and flags pixels darker than that local
# estimate. A uniform darkening offset, by construction, contributes zero
# local contrast more than ~1-2 blur-sigma away from the patch's own edge --
# the local background there is just the same offset, so it cancels out and
# only residual speckle noise is left. That's a problem only for *width*,
# not length: an elongated, branching shape can sprawl for a long total
# distance and still avoid this as long as its local cross-sectional radius
# (base_radius_px, tapering to tip_radius_px) stays in the same ~12-20px
# range that worked for the simple blobs before. Branch tips also can't go
# much below ~5-6px radius or Stage 1's morphological opening (5x5 kernel,
# 2 iterations, ~4-5px erosion depth) severs them.
#
# heading_deg points each slick's main spine *away* from the other slick
# and away from the nearest look-alike, so their (now much larger) extents
# can't collide even though the scene is only 500x500px.
SPILLS = [
    {
        "lat": 17.69,
        "lon": 83.33,
        "heading_deg": 220,  # up-left
        "main_length_px": 60,
        "base_radius_px": 13,
        "tip_radius_px": 6,
        "num_branches": 2,
        "offset_db": 8.0,
    },
    {
        "lat": 17.65,
        "lon": 83.37,
        "heading_deg": 40,  # down-right
        "main_length_px": 55,
        "base_radius_px": 12,
        "tip_radius_px": 6,
        "num_branches": 2,
        "offset_db": 8.0,
    },
]

# Two look-alike patches -- dark, but not oil: low-wind zones or biogenic
# (algal/organic film) slicks. Real, but weakly and non-uniformly so:
#   - fuzzy edge:      the darkening mask itself is Gaussian-blurred (a
#                      small kernel -- just enough to soften the rim, not
#                      dilute the whole footprint) before being applied, so
#                      it fades into the water over a few pixels instead of
#                      cutting off at a hard boundary.
#   - patchy interior: a coarse mottled pattern (smoothly-varying over a
#                      several-pixel scale, not per-pixel noise) is added
#                      inside the footprint. Per-pixel random noise was
#                      tried first and rejected: Stage 1's own morphological
#                      opening acts as a smoothness filter, so fine-grained
#                      noise gets eroded away preferentially (leaving only
#                      the *smoothest* sub-region standing -- exactly the
#                      opposite of "patchy"), and can even fragment the raw
#                      anomaly mask below the survivable size. A coarse,
#                      spatially-correlated mottle survives that filtering
#                      while still reading as non-uniform once measured.
#   - weak contrast:   offset_db is roughly half the oil patches', so even
#                      at full strength these never get close to real oil's
#                      darkness.
#
# Sizing rationale: Stage 1's morphological opening erodes ~4-5px from
# every edge (5x5 kernel, 2 iterations); a solid disk needs roughly
# radius >= 18px for enough of it (>= MIN_REGION_PIXELS = 500px) to survive
# that and still clear MIN_REGION_PIXELS. rx/ry here sit just above that
# floor -- big enough to reliably register, not so big that a weak offset
# reads as strong purely from covering more area.
#
# Placed well away from both oil slicks (no overlap or near-touching) and
# clear of the scene edges.
LOOKALIKES = [
    {
        "lat": 17.73,
        "lon": 83.40,
        "rx_px": 20,
        "ry_px": 27,
        "offset_db": 4.4,
        "edge_blur_px": 2,
        "mottle_db": 2.0,
    },
    {
        "lat": 17.62,
        "lon": 83.30,
        "rx_px": 20,
        "ry_px": 27,
        "offset_db": 4.4,
        "edge_blur_px": 2,
        "mottle_db": 2.0,
    },
]

SEA_MEAN_DB = -12.0
SEA_SPECKLE_DB = 1.3

NUM_SHIPS = 10
SHIP_BRIGHTNESS_DB = (8.0, 14.0)  # bright point returns, added on top of the sea background


def _lonlat_to_px(lon: float, lat: float, transform):
    col, row = ~transform * (lon, lat)
    return int(round(row)), int(round(col))


def _ellipse_mask(yy, xx, row0, col0, rx_px, ry_px) -> np.ndarray:
    return ((xx - col0) ** 2 / rx_px**2 + (yy - row0) ** 2 / ry_px**2) < 1


def _wander_path(rng, row0, col0, heading_deg, length_px, wander_deg, step_px=4.0):
    """A gently random-walking path: heading takes a small random turn each
    step, so the path curves naturally instead of running dead straight.
    Returns [(row, col, heading_deg), ...] at each step."""
    r, c, heading = float(row0), float(col0), float(heading_deg)
    steps = max(int(length_px / step_px), 6)
    pts = []
    for _ in range(steps):
        heading += rng.uniform(-wander_deg, wander_deg)
        rad = np.radians(heading)
        r += step_px * np.sin(rad)
        c += step_px * np.cos(rad)
        pts.append((r, c, heading))
    return pts


def _branching_slick_mask(
    h,
    w,
    row0,
    col0,
    rng,
    heading_deg,
    main_length_px=120,
    base_radius_px=13,
    tip_radius_px=6,
    num_branches=2,
    branch_length_frac=(0.3, 0.5),
    branch_origin_frac=(0.45, 0.8),
) -> np.ndarray:
    """An elongated, branching, organic slick shape: a wandering main
    "spine" tapering from base_radius_px down to tip_radius_px, with a
    couple of thinner branches splitting off at angles partway along it --
    built from many overlapping filled circles, so the boundary comes out
    naturally lumpy/irregular (no smoothing or simplification applied).
    Mimics how a real slick spreads: a main body with fingers trailing off.

    Branches originate from the *back half* of the main spine
    (branch_origin_frac), where it has already tapered down, and their own
    radius is keyed off the spine's local width at that point rather than
    the spine's own base. Originating branches too close to the spine's
    base -- its single widest point -- stacks multiple large circles on
    top of each other there, and that combined mass is wide enough to
    reintroduce the local-background self-cancellation effect (Stage 1
    reads its deep interior as indistinguishable from local background),
    which showed up as a hollow, high-variance "head" on an earlier version
    of this shape.
    """
    mask = np.zeros((h, w), dtype=np.uint8)

    def stamp(pts, radius_start, radius_end, jitter):
        widths = np.linspace(radius_start, radius_end, len(pts))
        for (r, c, _), base_w in zip(pts, widths):
            radius = max(2.0, base_w + rng.uniform(-jitter, jitter))
            cv2.circle(mask, (int(round(c)), int(round(r))), int(round(radius)), 255, -1)

    main_pts = _wander_path(rng, row0, col0, heading_deg, main_length_px, wander_deg=9.0)
    main_widths = np.linspace(base_radius_px, tip_radius_px, len(main_pts))
    stamp(main_pts, base_radius_px, tip_radius_px, jitter=1.5)

    for _ in range(num_branches):
        idx = int(rng.integers(int(branch_origin_frac[0] * len(main_pts)), int(branch_origin_frac[1] * len(main_pts))))
        br_row, br_col, br_heading = main_pts[idx]
        branch_len = main_length_px * rng.uniform(*branch_length_frac)
        branch_heading = br_heading + float(rng.choice([-1.0, 1.0])) * rng.uniform(35, 70)
        branch_pts = _wander_path(rng, br_row, br_col, branch_heading, branch_len, wander_deg=14.0)
        local_radius = main_widths[idx]
        branch_base = local_radius * rng.uniform(0.55, 0.75)
        branch_tip = max(2.5, tip_radius_px * rng.uniform(0.55, 0.85))
        stamp(branch_pts, branch_base, branch_tip, jitter=1.0)

    return mask > 0


def generate(seed: int = 10) -> str:
    # Note on the seed: classification depends on which specific pixels
    # survive Stage 1's threshold + morphological cleaning, which is
    # sensitive to exactly where the mottle pattern's peaks/troughs happen
    # to fall -- not just to the LOOKALIKES parameters above. Seed 10 is
    # the one confirmed (via backend/make_synthetic.py's test iterations)
    # to give clean separation with those parameters; changing the seed
    # without re-verifying classifier output can shift a look-alike back
    # into UNCERTAIN or even LIKELY OIL SPILL territory.
    rng = np.random.default_rng(seed)

    transform = from_origin(WEST, NORTH, (EAST - WEST) / WIDTH, (NORTH - SOUTH) / HEIGHT)

    band = rng.normal(loc=SEA_MEAN_DB, scale=SEA_SPECKLE_DB, size=(HEIGHT, WIDTH)).astype(np.float32)

    yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
    # Tracks every pixel touched by a slick or look-alike, so ship glints
    # (below) never land inside one -- a bright point return buried in an
    # otherwise near-zero-variance oil interior would spike its measured
    # homogeneity and distort the classifier for no physically meaningful
    # reason (this is a placement rule for the synthetic scene, not a
    # change to how the detector measures homogeneity).
    occupied = np.zeros((HEIGHT, WIDTH), dtype=bool)

    # Real oil: hard-edged, branching/elongated organic shape, uniform
    # offset, ambient speckle preserved (untouched) inside -- sharp boundary
    # (still a hard cutoff, just a complex/jagged one), smooth interior,
    # strong contrast.
    for spill in SPILLS:
        row0, col0 = _lonlat_to_px(spill["lon"], spill["lat"], transform)
        mask = _branching_slick_mask(
            HEIGHT,
            WIDTH,
            row0,
            col0,
            rng,
            heading_deg=spill["heading_deg"],
            main_length_px=spill["main_length_px"],
            base_radius_px=spill["base_radius_px"],
            tip_radius_px=spill["tip_radius_px"],
            num_branches=spill["num_branches"],
        )
        band[mask] -= spill["offset_db"]
        occupied |= mask

    # Look-alikes: blur the darkening mask itself (a small kernel -- just
    # softens the rim, doesn't dilute the whole footprint), apply a weaker
    # offset, and add a coarse mottled pattern inside the footprint --
    # fuzzy, patchy, shallow.
    for spot in LOOKALIKES:
        row0, col0 = _lonlat_to_px(spot["lon"], spot["lat"], transform)
        hard_mask = _ellipse_mask(yy, xx, row0, col0, spot["rx_px"], spot["ry_px"]).astype(np.float32)
        k = spot["edge_blur_px"] * 2 + 1  # odd kernel size
        soft_mask = cv2.GaussianBlur(hard_mask, (k, k), 0)

        band -= soft_mask * spot["offset_db"]

        # Coarse mottled texture: varies smoothly over a several-pixel
        # scale (see LOOKALIKES comment above for why this beats per-pixel
        # noise here), amplitude bounded by mottle_db so no pixel's net
        # darkening gets close to zero.
        period_x, period_y = rng.uniform(4, 9), rng.uniform(4, 9)
        phase_x, phase_y = rng.uniform(0, 2 * np.pi), rng.uniform(0, 2 * np.pi)
        mottle = np.sin(xx / period_x + phase_x) * np.sin(yy / period_y + phase_y)
        band += soft_mask * mottle * spot["mottle_db"]
        occupied |= soft_mask > 0.05

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    placed = 0
    attempts = 0
    while placed < NUM_SHIPS and attempts < NUM_SHIPS * 20:
        attempts += 1
        r = int(rng.integers(15, HEIGHT - 15))
        c = int(rng.integers(15, WIDTH - 15))
        if occupied[r - 2 : r + 3, c - 2 : c + 3].any():
            continue
        boost = rng.uniform(*SHIP_BRIGHTNESS_DB)
        band[r - 1 : r + 2, c - 1 : c + 2] += boost
        placed += 1

    with rasterio.open(
        OUTPUT_PATH,
        "w",
        driver="GTiff",
        height=HEIGHT,
        width=WIDTH,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(band, 1)

    return OUTPUT_PATH


if __name__ == "__main__":
    path = generate()
    print(f"Wrote synthetic open-water scene to {path}")
    print(f"Oil slicks centered near: {[(s['lat'], s['lon']) for s in SPILLS]}")
    print(f"Look-alikes centered near: {[(s['lat'], s['lon']) for s in LOOKALIKES]}")
