---

title: SINDVA Marine Watch
emoji: 🌊
colorFrom: blue
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
-------------

# 🌊 SINDVA Marine Watch

### Satellite Oil-Spill Detection, Vessel Attribution & Maritime Investigation Platform

**SIH 2026 — Problem Statement SIH26143 | Disaster Management | Software**

SINDVA Marine Watch is an AI-assisted maritime surveillance platform designed to detect potential oil spills from **Sentinel-1 SAR satellite imagery**, distinguish oil from radar look-alikes, correlate detected spills with **AIS vessel tracks**, estimate the probable spill origin, and identify vessels that are most likely associated with the incident.

The platform is designed around a simple objective:

> **Detect the spill. Understand its movement. Trace its origin. Identify the likely source.**

Instead of treating oil-spill detection as a standalone image-classification problem, SINDVA combines **satellite imagery, computer vision, deep learning, weather conditions, vessel movement, anomaly analysis, and geospatial reasoning** into a single investigation workflow.

---

## 🎯 Problem Statement

Oil spills at sea are difficult to detect and investigate because oceans cover enormous areas, conventional monitoring is expensive, and the responsible vessel may not always be immediately identifiable.

The SIH26143 problem statement focuses on:

* Detecting oil spills using satellite imagery.
* Correlating detected spills with AIS vessel data.
* Identifying the vessel potentially responsible for the spill.

SINDVA addresses this by transforming satellite observations into an **evidence-driven maritime investigation workflow**.

---

# 🚀 What SINDVA Does

SINDVA currently provides an integrated workflow covering:

| Capability                   | Description                                                    |
| ---------------------------- | -------------------------------------------------------------- |
| 🛰️ Satellite Detection      | Detects potential oil-spill regions from SAR imagery           |
| 🤖 AI Segmentation           | Uses a trained U-Net model for oil-spill segmentation          |
| 👁️ Computer Vision          | Provides an explainable classical CV detection pipeline        |
| 🔍 Look-Alike Filtering      | Helps distinguish oil signatures from radar look-alikes        |
| 🌦️ Weather Analysis         | Incorporates environmental conditions into detection reasoning |
| 🚢 AIS Correlation           | Correlates detected spills with vessel tracks                  |
| ⚠️ Vessel Anomaly Detection  | Identifies suspicious vessel behaviour and AIS gaps            |
| 🎯 Culprit Correlation Index | Produces a transparent weighted vessel-risk score              |
| 🌊 Origin Estimation         | Estimates where the spill may have originated                  |
| 🌐 Drift Forecasting         | Estimates potential movement and future spread                 |
| 🗺️ Investigation Dashboard  | Provides an interactive geospatial investigation interface     |
| 📊 Evidence Fusion           | Combines multiple evidence sources into a unified assessment   |
| 📄 Reporting                 | Converts investigation results into structured reports         |

The system is intended to support **monitoring, investigation, response, and enforcement**, rather than simply producing a binary "oil / no oil" prediction.

---

# 🧠 System Architecture

```text
                    ┌──────────────────────────┐
                    │   Sentinel-1 SAR Image   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                 ┌──────────────────────────────┐
                 │     Preprocessing / GeoTIFF   │
                 └──────────────┬───────────────┘
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
      ┌──────────────────┐             ┌──────────────────┐
      │ Classical CV     │             │ U-Net Deep       │
      │ Detection        │             │ Learning Model   │
      └────────┬─────────┘             └────────┬─────────┘
               │                                │
               └───────────────┬────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Evidence Fusion     │
                    │ & Classification    │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
          ┌──────────┐   ┌──────────┐   ┌─────────────┐
          │ Weather  │   │ AIS Data │   │ Spill       │
          │ Analysis │   │ Tracks   │   │ Geometry    │
          └────┬─────┘   └────┬─────┘   └──────┬──────┘
               │              │                │
               └──────────────┼────────────────┘
                              ▼
                  ┌────────────────────────┐
                  │ Vessel Correlation     │
                  │ + Behaviour Analysis   │
                  └────────────┬───────────┘
                               ▼
                  ┌────────────────────────┐
                  │ Origin Estimation      │
                  │ & Drift Forecasting    │
                  └────────────┬───────────┘
                               ▼
                  ┌────────────────────────┐
                  │ Investigation          │
                  │ Dashboard & Reports    │
                  └────────────────────────┘
```

---

# 🔬 Core Technical Approach

## 1. Satellite-Based Spill Detection

SINDVA works with **Sentinel-1 SAR imagery**, which is particularly useful for maritime monitoring because SAR can operate independently of daylight and is less dependent on conventional optical imaging conditions.

The detection pipeline supports two complementary approaches:

### Classical Computer Vision

The classical detector analyses local SAR intensity characteristics and identifies anomalous dark regions using techniques including:

* Background estimation
* Local darkness comparison
* Adaptive thresholding
* Contour extraction
* Region filtering
* Geospatial bounding-box generation

This approach provides an explainable detection baseline.

### Deep Learning

A trained **U-Net segmentation model** is included in the backend for semantic segmentation of potential oil-spill regions.

The combination of AI and classical computer vision provides a more robust architecture than relying on a single detection method.

---

# 🧪 2. Oil vs. Radar Look-Alike Analysis

Dark regions in SAR imagery do not automatically represent oil.

Potential look-alikes can be caused by:

* Calm water
* Low wind conditions
* Radar artefacts
* Natural ocean phenomena
* Other surface effects

SINDVA therefore incorporates environmental information and detection evidence before treating a dark SAR signature as a potential oil spill.

This **look-alike filtering and wind-condition analysis** is one of the core design principles of the system.

---

# 🚢 3. AIS Vessel Correlation

After a potential spill is detected, SINDVA correlates the spill location with vessel movement data.

The correlation considers factors such as:

* Spatial proximity
* Temporal proximity
* Track intersection
* Vessel movement
* Spill geometry
* Behavioural anomalies

The system then ranks vessels according to their likelihood of being associated with the detected spill.

---

# ⚠️ 4. Vessel Behaviour & AIS Anomaly Detection

A vessel does not necessarily need to be physically located at the spill centroid to be relevant.

SINDVA therefore includes analysis for suspicious vessel behaviour, including:

* AIS transmission gaps
* Unusual speed changes
* Loitering behaviour
* Route deviations
* Track irregularities
* Potential dark-vessel periods

These signals are treated as **investigative evidence**, rather than definitive proof of responsibility.

---

# 🎯 5. Culprit Correlation Index

One of SINDVA's key concepts is the **Culprit Correlation Index (CCI)**.

Rather than returning:

> "Vessel X caused the spill."

the system produces a transparent weighted assessment based on multiple signals.

Conceptually:

```text
CCI
 │
 ├── Spatial correlation
 ├── Temporal correlation
 ├── Spill/track intersection
 ├── Vessel behaviour
 ├── AIS continuity / gaps
 └── Supporting environmental evidence
```

This makes the result easier to interpret and investigate.

The purpose is not to replace human or legal investigation, but to provide **ranked, evidence-backed leads**.

---

# 🌊 6. Spill Origin & Drift Forecasting

SINDVA goes beyond detecting the present spill location.

Using environmental and geospatial information, the system can:

### Estimate Origin

Work backwards from the detected spill region to estimate a probable source/origin area.

### Forecast Drift

Estimate how the spill may move under prevailing environmental conditions.

This enables the system to support both:

**Retrospective investigation**

```text
Detected Spill
      ↓
Backtrack movement
      ↓
Estimate probable origin
```

and:

**Forward response planning**

```text
Current Spill
      ↓
Environmental conditions
      ↓
Predicted movement
      ↓
Potential future affected area
```

---

# 🗺️ Investigation Dashboard

The frontend provides an interactive investigation-oriented interface rather than a simple prediction screen.

Major dashboard areas include:

* Spill detection
* Investigation map
* Vessel traffic
* Weather conditions
* Vessel analysis
* Alerts
* Evidence fusion
* CCI breakdown
* Drift forecast
* Investigation reports

The objective is to allow an investigator to move from:

**Detection → Correlation → Investigation → Evidence → Report**

within one platform.

---

# 🧩 Technology Stack

## Backend

* Python 3.12
* FastAPI
* OpenCV
* PyTorch
* U-Net
* Rasterio
* NumPy
* Pandas

## Frontend

* Next.js
* React
* TypeScript
* Leaflet
* CSS / modern web UI

## Data & Geospatial Processing

* Sentinel-1 SAR imagery
* GeoTIFF
* AIS vessel data
* MarineCadastre AIS format
* Open-Meteo environmental data

## Deployment

* Docker
* Hugging Face Spaces
* Netlify

---

# 📁 Project Structure

```text
sindva-oil-spill/
│
├── backend/
│   ├── ais/
│   │   ├── anomaly.py
│   │   ├── correlate.py
│   │   ├── gap_detect.py
│   │   ├── generate_ais.py
│   │   ├── geo.py
│   │   └── investigate.py
│   │
│   ├── detection/
│   │   ├── cv_detect.py
│   │   ├── ml_detect.py
│   │   └── sindva_unet_oilspill.pth
│   │
│   ├── fusion/
│   │   └── evidence_fusion.py
│   │
│   ├── origin/
│   │   ├── estimate_origin.py
│   │   └── forecast_drift.py
│   │
│   ├── weather/
│   │   └── weather.py
│   │
│   ├── data/
│   │   ├── ais/
│   │   ├── images/
│   │   └── outputs/
│   │
│   ├── app.py
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   ├── alerts/
│   │   ├── investigation/
│   │   ├── reports/
│   │   ├── traffic/
│   │   └── weather/
│   │
│   ├── components/
│   ├── lib/
│   └── package.json
│
├── Dockerfile
├── netlify.toml
└── README.md
```

---

# ⚙️ Local Development

SINDVA consists of two independently running applications:

```text
Frontend
   │
   │ HTTP API
   ▼
FastAPI Backend
   │
   ├── Detection
   ├── AI Segmentation
   ├── AIS Correlation
   ├── Weather
   ├── Origin Estimation
   └── Drift Forecasting
```

## Prerequisites

Recommended environment:

* Python 3.12
* Node.js
* npm
* Git

> Python 3.14 is not currently recommended because of native geospatial dependency compatibility.

---

## 1. Clone the Repository

```bash
git clone https://github.com/Narendra45187/sindva-oil-spill.git
cd sindva-oil-spill
```

---

## 2. Start the Backend

```bash
cd backend
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app:app --port 8000
```

The backend will be available at:

```text
http://localhost:8000
```

---

## 3. Start the Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at:

```text
http://localhost:3000
```

The frontend communicates with the FastAPI backend through its configured API base URL.

---

# 🚢 AIS Demonstration Data

For local demonstration, the repository includes an AIS dataset following the **MarineCadastre-style column format**.

To regenerate the demonstration vessel tracks:

```bash
py -3.12 backend/ais/generate_ais.py
```

This generates:

```text
backend/data/ais/ais_vizag.csv
```

The demonstration environment contains synthetic vessel tracks intended for testing and visualization.

### Important

Synthetic AIS data should **not** be interpreted as real-world vessel attribution.

For operational deployment, the system should be connected to an appropriate live or historical AIS provider.

---

# 🛰️ Satellite Input

SINDVA can process GeoTIFF satellite imagery through the backend detection pipeline.

For local testing, satellite imagery can be placed under:

```text
backend/data/images/
```

The repository also contains a synthetic demonstration scene so that the application can be tested without requiring immediate access to a live satellite-data pipeline.

For real-world analysis, Sentinel-1 SAR imagery should be obtained from an appropriate Copernicus data source.

---

# ☁️ Deployment

## Backend — Hugging Face Spaces

The backend is containerized using Docker and can be deployed using the **Docker SDK on Hugging Face Spaces**.

The root Dockerfile:

1. Installs required system dependencies.
2. Installs the Python backend dependencies.
3. Configures the FastAPI service.
4. Exposes port `7860`.

The deployed service is designed to serve the backend API.

## Frontend — Netlify

The Next.js frontend can be deployed independently.

The frontend is configured to communicate with the deployed backend through the API base configuration.

This separation allows the frontend and backend to scale independently.

---

# 🔌 API Workflow

At a high level, the backend exposes workflows for:

```text
POST /api/detect
        │
        ▼
Satellite Image Analysis
        │
        ▼
Spill Metadata
        │
        ▼
POST /api/correlate
        │
        ▼
AIS Vessel Ranking
        │
        ▼
Investigation / Evidence
```

Detection must be performed before vessel correlation because the correlation module uses the latest detected spill as its spatial and temporal reference.

---

# 💡 Key Innovations

### 1. Hybrid Detection

Combines:

**Classical Computer Vision + Deep Learning**

rather than depending exclusively on one model.

### 2. Look-Alike Filtering

Environmental conditions are considered to reduce false positives caused by non-oil SAR dark spots.

### 3. Evidence-Based Attribution

Vessel ranking combines multiple independent signals rather than relying only on distance from the spill.

### 4. Transparent CCI

The Culprit Correlation Index provides an interpretable scoring framework for vessel investigation.

### 5. Dark-Vessel Analysis

AIS gaps and anomalous vessel behaviour can become additional investigative signals.

### 6. Origin + Forecast

The platform supports both backward-looking source estimation and forward-looking spill movement analysis.

### 7. End-to-End Investigation

The system connects:

```text
Satellite
   ↓
Detection
   ↓
Validation
   ↓
Weather
   ↓
AIS
   ↓
Attribution
   ↓
Origin
   ↓
Forecast
   ↓
Report
```

---

# 🌍 Impact

SINDVA is designed to support three major areas:

### Environmental

* Faster identification of potential marine pollution.
* Reduced response time.
* Protection of marine ecosystems.
* Protection of fisheries and coastal communities.

### Economic

* Potential reduction in spill-response and cleanup costs.
* Reduced impact on fishing and coastal industries.
* Low-cost monitoring using publicly available data sources.

### Maritime Security & Enforcement

* Large-area maritime monitoring.
* Detection of suspicious vessel behaviour.
* Evidence-oriented vessel investigation.
* Improved accountability for potential polluters.

The broader objective is to transform the ocean from a largely unobservable monitoring environment into a **continuously analyzable and evidence-driven maritime space**.

---

# ⚠️ Limitations & Responsible Use

SINDVA is a research and demonstration prototype and should not be treated as an autonomous legal attribution system.

Important limitations include:

### SAR Ambiguity

Not every dark SAR signature represents oil.

### AIS Availability

AIS data may be:

* Missing
* Delayed
* Incomplete
* Intentionally disabled
* Inaccurate

### Environmental Uncertainty

Spill movement depends on complex oceanographic and atmospheric conditions.

### Synthetic Demonstration Data

Some demonstration components use synthetic data and should not be interpreted as real incidents.

### Attribution Confidence

A high CCI score indicates a stronger correlation based on available evidence. It does **not** establish legal responsibility.

Human verification and additional operational evidence are required before enforcement decisions.

---

# 🔮 Future Roadmap

Potential future improvements include:

* [ ] Live Sentinel-1 data ingestion
* [ ] Automated satellite-scene acquisition
* [ ] Live AIS integration
* [ ] Multi-satellite fusion
* [ ] Improved oil-vs-look-alike classification
* [ ] Larger U-Net / transformer segmentation models
* [ ] Advanced ocean-current integration
* [ ] Real-time spill alerts
* [ ] Historical incident replay
* [ ] Multi-region deployment
* [ ] Automated evidence packages
* [ ] Confidence calibration and model benchmarking
* [ ] Large-scale cloud processing
* [ ] Integration with maritime command-and-control systems

---

# 📚 Data Sources & Research

### Satellite Data

**Copernicus Sentinel-1 SAR**

Used as the primary satellite-imagery source for SAR-based marine monitoring.

### AIS Data

**MarineCadastre AIS data format**

Used for vessel-track representation and demonstration workflows.

### Environmental Data

**Open-Meteo**

Used for environmental/weather information supporting detection and investigation.

### Research Datasets

* Sentinel-1 SAR oil-spill datasets
* Deep SAR SOS dataset

### Research Literature

The project draws on research concerning:

* SAR-based oil-spill detection
* SAR backscatter and texture analysis
* Deep-learning segmentation
* AIS-based vessel behaviour analysis
* Oil-spill drift modelling

---

# 🏆 Smart India Hackathon 2026

**Problem Statement:** SIH26143
**Category:** Software
**Theme:** Disaster Management
**Project:** SINDVA Marine Watch
**Team:** Skill Sphere

SINDVA was developed as a solution to the Smart India Hackathon 2026 problem statement focused on detecting marine oil spills using satellite imagery and correlating them with AIS data to identify potentially responsible vessels.

---

# 👥 Team

**Team Aarambh**

Built for **Smart India Hackathon 2026**.

---

# 📄 License

Add the project's intended open-source license here, for example:

```text
MIT License
```

if the project is intended to be released under MIT.

---

## ⚡ Project Status

**Prototype / Research Demonstration**

The system currently demonstrates an end-to-end workflow from satellite-based detection through vessel correlation, investigation, origin estimation, drift forecasting, and reporting.

---

> **SINDVA Marine Watch — From satellite pixels to maritime evidence.** 🌊
