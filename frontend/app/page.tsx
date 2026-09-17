"use client";

import { useCallback, useState } from "react";
import dynamic from "next/dynamic";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import ScenePanel from "@/components/ScenePanel";
import VesselPanel from "@/components/VesselPanel";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import type {
  CorrelateResponse,
  DetectResponse,
  DriftForecastResponse,
  FusionResponse,
  OriginEstimate,
  WeatherConditions,
} from "@/lib/types";

const DEFAULT_DRIFT_MINUTES = 30;
const DEFAULT_FORECAST_HOURS = 6;

const MapStage = dynamic(() => import("@/components/MapStage"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center rounded-xl border border-line bg-panel text-sm text-slate-500">
      Loading map…
    </div>
  ),
});

export default function Home() {
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Which button is in flight, purely so each shows its own loading label
  // while sharing the same `loading`/`error` state (only one detection
  // request is ever in flight at a time either way).
  const [runningMethod, setRunningMethod] = useState<"cv" | "ml" | null>(null);

  const [correlation, setCorrelation] = useState<CorrelateResponse | null>(null);
  const [correlating, setCorrelating] = useState(false);
  const [correlateError, setCorrelateError] = useState<string | null>(null);
  const [selectedMmsi, setSelectedMmsi] = useState<number | null>(null);

  const [weather, setWeather] = useState<WeatherConditions | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState<string | null>(null);

  const [origin, setOrigin] = useState<OriginEstimate | null>(null);
  const [originLoading, setOriginLoading] = useState(false);
  const [driftMinutes, setDriftMinutes] = useState(DEFAULT_DRIFT_MINUTES);

  const [forecast, setForecast] = useState<DriftForecastResponse | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastHours, setForecastHours] = useState(DEFAULT_FORECAST_HOURS);

  const [fusion, setFusion] = useState<FusionResponse | null>(null);
  const [fusionLoading, setFusionLoading] = useState(false);

  const fetchFusion = useCallback(async () => {
    setFusionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/fusion`);
      const data: FusionResponse = await res.json();
      setFusion(data);
    } catch (err) {
      setFusion({
        available: false,
        message: err instanceof Error ? `Could not fuse evidence — ${err.message}` : "Could not fuse evidence.",
      });
    } finally {
      setFusionLoading(false);
    }
  }, []);

  const fetchOrigin = useCallback(async (minutes: number) => {
    setOriginLoading(true);
    try {
      const url = new URL(`${API_BASE}/api/origin`);
      url.searchParams.set("minutes", String(minutes));

      const res = await fetch(url.toString());
      const data: OriginEstimate = await res.json();
      setOrigin(data);
    } catch (err) {
      setOrigin({
        available: false,
        message: err instanceof Error ? `Could not estimate origin — ${err.message}` : "Could not estimate origin.",
      });
    } finally {
      setOriginLoading(false);
    }
  }, []);

  const changeDriftMinutes = useCallback(
    (minutes: number) => {
      setDriftMinutes(minutes);
      fetchOrigin(minutes);
    },
    [fetchOrigin]
  );

  const fetchForecast = useCallback(async (hours: number) => {
    setForecastLoading(true);
    try {
      const url = new URL(`${API_BASE}/api/forecast`);
      url.searchParams.set("hours", String(hours));

      const res = await fetch(url.toString());
      const data: DriftForecastResponse = await res.json();
      setForecast(data);
    } catch (err) {
      setForecast({
        available: false,
        message: err instanceof Error ? `Could not forecast drift — ${err.message}` : "Could not forecast drift.",
      });
    } finally {
      setForecastLoading(false);
    }
  }, []);

  const changeForecastHours = useCallback(
    (hours: number) => {
      setForecastHours(hours);
      fetchForecast(hours);
    },
    [fetchForecast]
  );

  const fetchWeather = useCallback(async (lat: number, lon: number) => {
    setWeatherLoading(true);
    setWeatherError(null);
    try {
      const url = new URL(`${API_BASE}/api/weather`);
      url.searchParams.set("lat", String(lat));
      url.searchParams.set("lon", String(lon));

      const res = await fetch(url.toString());
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `Weather service returned ${res.status}`);
      }

      const data: WeatherConditions = await res.json();
      setWeather(data);
    } catch (err) {
      setWeatherError(
        err instanceof Error
          ? `Could not load conditions — ${err.message}`
          : "Could not load conditions."
      );
    } finally {
      setWeatherLoading(false);
    }
  }, []);

  const runDetection = useCallback(
    async (file?: File, endpoint: "/api/detect" | "/api/detect_ml" = "/api/detect") => {
      setLoading(true);
      setError(null);
      setRunningMethod(endpoint === "/api/detect_ml" ? "ml" : "cv");
      try {
        const formData = new FormData();
        if (file) formData.append("file", file);

        const res = await fetch(`${API_BASE}${endpoint}`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `Detection service returned ${res.status}`);
        }

        const data: DetectResponse = await res.json();
        setResult(data);
        // A new spill invalidates any correlation / conditions read against
        // the previous one.
        setCorrelation(null);
        setCorrelateError(null);
        setSelectedMmsi(null);
        setWeather(null);
        setWeatherError(null);
        setOrigin(null);
        setForecast(null);
        setFusion(null);

        if (data.meta.centroid) {
          // Origin estimation and drift forecast both read the weather
          // snapshot the backend persists as a side effect of
          // /api/weather, so wait for that call first -- otherwise either
          // could read a stale (or missing) weather reading from a
          // previous spill.
          await fetchWeather(data.meta.centroid.lat, data.meta.centroid.lon);
          fetchOrigin(driftMinutes);
          fetchForecast(forecastHours);
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? `Could not reach detection service — ${err.message}`
            : "Could not reach detection service."
        );
      } finally {
        setLoading(false);
      }
    },
    [fetchWeather, fetchOrigin, driftMinutes, fetchForecast, forecastHours]
  );

  const runCorrelation = useCallback(async () => {
    setCorrelating(true);
    setCorrelateError(null);
    try {
      const res = await fetch(`${API_BASE}/api/correlate`, { method: "POST" });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `Correlation service returned ${res.status}`);
      }

      const data: CorrelateResponse = await res.json();
      setCorrelation(data);
      setSelectedMmsi(data.suspects[0]?.mmsi ?? null);
      // Evidence fusion needs the CCI this correlation run just produced,
      // alongside the detection/origin stages that are already available.
      fetchFusion();
    } catch (err) {
      setCorrelateError(
        err instanceof Error
          ? `Could not correlate AIS tracks — ${err.message}`
          : "Could not correlate AIS tracks."
      );
    } finally {
      setCorrelating(false);
    }
  }, [fetchFusion]);

  const scene = result?.scene ?? DEFAULT_SCENE;

  return (
    <div className="flex h-screen flex-col">
      <TopBar timestamp={scene.timestamp} />
      <NavBar />

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[320px_1fr_320px] xl:grid-cols-[360px_1fr_360px]">
        <div className="min-h-0 rounded-xl border border-line bg-panel/40 lg:order-1">
          <ScenePanel
            scene={DEFAULT_SCENE}
            result={result}
            loading={loading}
            error={error}
            onAnalyze={() => runDetection()}
            onAnalyzeML={() => runDetection(undefined, "/api/detect_ml")}
            onUpload={(file) => runDetection(file)}
            onUploadML={(file) => runDetection(file, "/api/detect_ml")}
            runningMethod={runningMethod}
            weather={weather}
            weatherLoading={weatherLoading}
            weatherError={weatherError}
            origin={origin}
            originLoading={originLoading}
            driftMinutes={driftMinutes}
            onDriftMinutesChange={changeDriftMinutes}
            forecast={forecast}
            forecastLoading={forecastLoading}
            forecastHours={forecastHours}
            onForecastHoursChange={changeForecastHours}
          />
        </div>

        <div className="order-first min-h-[360px] lg:order-2 lg:min-h-0">
          <MapStage
            center={DEFAULT_SCENE.center}
            result={result}
            aisTracks={correlation?.ais_tracks ?? null}
            suspects={correlation?.suspects ?? null}
            selectedMmsi={selectedMmsi}
            onSelectVessel={setSelectedMmsi}
            origin={origin}
            forecast={forecast}
          />
        </div>

        <div className="min-h-0 rounded-xl border border-line bg-panel/40 lg:order-3">
          <VesselPanel
            canCorrelate={result !== null}
            suspects={correlation?.suspects ?? null}
            loading={correlating}
            error={correlateError}
            selectedMmsi={selectedMmsi}
            onCorrelate={runCorrelation}
            onSelect={setSelectedMmsi}
            fusion={fusion}
            fusionLoading={fusionLoading}
          />
        </div>
      </main>
    </div>
  );
}
