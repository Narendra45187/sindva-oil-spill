---
title: Sindva Marine Watch
emoji: 🌊
colorFrom: blue
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
---

# SINDVA Marine Watch — SIH26143

Satellite Oil-Spill Detection & AIS Vessel Attribution dashboard for Visakhapatnam, Bay of Bengal.

## Deployment (Hugging Face Spaces, Docker SDK)

The YAML block at the top of this file is Hugging Face Spaces' required
config header — it tells the Space to build the root `Dockerfile` (Docker
SDK) and route traffic to port `7860`, which is what that Dockerfile's
`uvicorn` command listens on. The Dockerfile builds **only the backend**
(`backend/`) — the frontend deploys separately (e.g. Netlify) and calls
this Space's URL as its API base.

To deploy: create a new Space on Hugging Face with the Docker SDK, and
either push this repo to the Space's own git remote, or connect it to this
GitHub repo. No other configuration is required — the Dockerfile installs
system GDAL before `pip install`-ing `rasterio` (see the Dockerfile's own
comments for why that order matters), and the sample scene/AIS CSV under
`backend/data/` ship in the image so the Space works immediately without
any manual data upload.

Two independent servers — run both at once:

## 1. Backend (detection service)

```
cd backend
py -3.12 -m uvicorn app:app --port 8000
```

Requires Python 3.12 (not 3.14). First-time setup:

```
py -3.12 -m pip install -r requirements.txt
```

Place a real Sentinel-1 GeoTIFF at `backend/data/images/vizag.tiff` — this is what
`POST /api/detect` analyzes when no file is uploaded through the dashboard.

> **Note on `rasterio` version:** `requirements.txt` pins `rasterio==1.3.10`.
> Newer rasterio wheels (1.4+) bundle a GDAL DLL with a per-build hashed
> filename that has no reputation history — on a machine with Windows
> **Smart App Control** enabled, that DLL gets silently blocked
> (`ImportError: DLL load failed ... Application Control policy`) even though
> `pip install` succeeds. 1.3.10 is a long-established build already trusted
> by Smart App Control. If you ever bump this pin, re-test `py -3.12 -c "import rasterio"`
> before relying on it.

## 2. Frontend (dashboard)

```
cd frontend
npm install
npm run dev
```

Opens at http://localhost:3000 and calls the backend at http://localhost:8000.

## 3. AIS vessel correlation (Module 2)

```
py -3.12 backend/ais/generate_ais.py
```

Writes `backend/data/ais/ais_vizag.csv` — 6 synthetic vessels, MarineCadastre.gov
column format, tracks spread around the Visakhapatnam scene. Run this once;
`POST /api/correlate` reads the CSV on every call rather than regenerating it.
If `backend/data/outputs/spill_metadata.json` already exists (i.e. detection has
run at least once), vessel 1's track is anchored to that spill's real centroid
instead of the hardcoded default — regenerate the CSV after a detection run if
you want the demo vessel positioned against your actual scene.

`POST /api/correlate` ranks all vessels in the CSV by likelihood of being the
spill source (spatial + temporal + intersection scoring against the latest
detection) and returns their tracks for the map. Responds `400 "Run detection
first."` if `/api/detect` hasn't been called yet, and a similar 400 if the AIS
CSV hasn't been generated yet.

## Detection logic

`backend/detection/cv_detect.py` is a classic-OpenCV detector (adaptive local
darkness vs. a heavily-blurred background estimate, then size-filtered
contours — see the module docstring). `backend/app.py` depends only on its
`run(image_path, out_dir, timestamp)` and `image_bounds(image_path)` contract,
so it can be swapped for different detection logic without touching the API
or frontend, as long as that contract is preserved.
