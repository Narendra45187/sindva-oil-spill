"use client";

import { useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import WeatherConditionsGrid from "@/components/WeatherConditionsGrid";
import WindyMap from "@/components/WindyMap";
import ForecastStrip from "@/components/ForecastStrip";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import type { ForecastResponse, WeatherConditions } from "@/lib/types";

// Visakhapatnam spill region default -- the last detected centroid seen in
// this project's demo runs. The dashboard's own detection flow has its own
// independent weather fetch (tied to whatever spill it just found); this
// page is a standalone conditions/forecast view, not wired to that
// per-session state, so it uses this fixed regional default instead.
const DEFAULT_LAT = 17.6952;
const DEFAULT_LON = 83.3243;

export default function WeatherPage() {
  const [weather, setWeather] = useState<WeatherConditions | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(true);
  const [weatherError, setWeatherError] = useState<string | null>(null);

  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastLoading, setForecastLoading] = useState(true);
  const [forecastError, setForecastError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadWeather() {
      setWeatherLoading(true);
      setWeatherError(null);
      try {
        const url = new URL(`${API_BASE}/api/weather`);
        url.searchParams.set("lat", String(DEFAULT_LAT));
        url.searchParams.set("lon", String(DEFAULT_LON));
        const res = await fetch(url.toString());
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `Weather service returned ${res.status}`);
        }
        const data: WeatherConditions = await res.json();
        if (!cancelled) setWeather(data);
      } catch (err) {
        if (!cancelled) {
          setWeatherError(
            err instanceof Error
              ? `Could not load conditions — ${err.message}`
              : "Could not load conditions."
          );
        }
      } finally {
        if (!cancelled) setWeatherLoading(false);
      }
    }

    async function loadForecast() {
      setForecastLoading(true);
      setForecastError(null);
      try {
        const url = new URL(`${API_BASE}/api/weather/forecast`);
        url.searchParams.set("lat", String(DEFAULT_LAT));
        url.searchParams.set("lon", String(DEFAULT_LON));
        url.searchParams.set("hours", "24");
        const res = await fetch(url.toString());
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `Forecast service returned ${res.status}`);
        }
        const data: ForecastResponse = await res.json();
        if (!cancelled) setForecast(data);
      } catch (err) {
        if (!cancelled) {
          setForecastError(
            err instanceof Error
              ? `Could not load forecast — ${err.message}`
              : "Could not load forecast."
          );
        }
      } finally {
        if (!cancelled) setForecastLoading(false);
      }
    }

    loadWeather();
    loadForecast();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar timestamp={DEFAULT_SCENE.timestamp} />
      <NavBar />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 p-4">
        <div>
          <h1 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
            Weather &amp; Ocean
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Live conditions, animated wind field, and short-term forecast for the Visakhapatnam
            spill region.
          </p>
        </div>

        <WeatherConditionsGrid weather={weather} loading={weatherLoading} error={weatherError} />
        <WindyMap />
        <ForecastStrip forecast={forecast} loading={forecastLoading} error={forecastError} />
      </main>
    </div>
  );
}
