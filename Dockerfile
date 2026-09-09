# SINDVA Marine Watch -- backend image for Hugging Face Spaces (Docker SDK).
#
# This image builds and runs ONLY the FastAPI backend in backend/ -- the
# Next.js frontend deploys separately (e.g. Netlify) and is not part of
# this image or this build.
#
# Build-order note (read this before touching the apt/pip lines below):
# the system GDAL library + headers (gdal-bin, libgdal-dev) are installed
# BEFORE `pip install -r requirements.txt` runs. That order matters: if
# pip has no prebuilt (manylinux) wheel for rasterio matching this exact
# Python/OS/CPU combination, it falls back to compiling rasterio from
# source, which requires a system GDAL to link against -- with the apt
# install done first, that fallback succeeds instead of failing the build.
# Debian bookworm's GDAL (3.6.x) is within rasterio 1.3.10's documented
# supported GDAL range (3.1-3.8), so the version already pinned in
# backend/requirements.txt is compatible as-is; nothing there needed to
# change for this image to work.

FROM python:3.12-slim

# System GDAL + build tooling, installed before any Python package that
# might need to compile against it (rasterio, primarily).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Read by rasterio/GDAL's build backend if pip compiles from source;
# harmless and unused if pip installs a prebuilt wheel instead.
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal \
    PYTHONUNBUFFERED=1

# Hugging Face Spaces runs Docker Space containers as a non-root user by
# convention. The app writes runtime files under backend/data/ (detection
# overlays/masks, the incident log, the weather fallback cache) -- without
# a matching non-root user + ownership here, those writes would fail with
# a permission error the first time the deployed Space is actually used,
# even though the image builds and the health check passes.
RUN useradd -m -u 1000 appuser
WORKDIR /home/appuser/app

# Python deps in their own layer -- only reinstalled when
# backend/requirements.txt actually changes, not on every code edit.
# Installed while still root; the installed packages only need to be
# readable (not writable) by appuser, which they are by default.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend source, including the sample scene/AIS data it reads at
# runtime (backend/data/images/vizag_synthetic.tiff, backend/data/ais/*.csv)
# -- both are needed for the app to work out of the box, so nothing under
# backend/data is excluded here (see .dockerignore). Owned by appuser so
# its later runtime writes under backend/data/ succeed.
COPY --chown=appuser:appuser backend/ ./backend/

USER appuser
WORKDIR /home/appuser/app/backend

# Hugging Face Spaces (Docker SDK) always routes traffic to port 7860.
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
