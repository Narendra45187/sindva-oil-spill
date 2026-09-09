import type { WeatherConditions } from "./types";

// Single source of truth for how the LIVE / CACHED / DEFAULT weather tiers
// are labeled -- used by both the Dashboard's WeatherPanel and the Weather
// page's WeatherConditionsGrid, so the two can never disagree or drift
// into presenting a fallback as if it were live.
export interface WeatherSourceDisplay {
  label: string;
  textClass: string;
  dotClass: string;
  ringClass: string;
  bgClass: string;
  caption: string;
}

export function weatherSourceDisplay(weather: WeatherConditions): WeatherSourceDisplay {
  const fetchedTime = new Date(weather.fetched_at).toLocaleTimeString();
  const fetchedFull = new Date(weather.fetched_at).toLocaleString();

  if (weather.source === "cached") {
    return {
      label: "CACHED",
      textClass: "text-amber",
      dotClass: "bg-amber",
      ringClass: "border-amber/30",
      bgClass: "bg-amber/10",
      caption: `Last live update ${fetchedFull} · showing last known values (live API unavailable)`,
    };
  }

  if (weather.source === "default") {
    return {
      label: "OFFLINE — REGIONAL DEFAULTS",
      textClass: "text-slate-400",
      dotClass: "bg-slate-500",
      ringClass: "border-line",
      bgClass: "bg-white/[0.03]",
      caption: "Live weather unavailable; showing typical regional values (not live)",
    };
  }

  return {
    label: "LIVE",
    textClass: "text-green",
    dotClass: "bg-green",
    ringClass: "border-green/30",
    bgClass: "bg-green/10",
    caption: `Live · fetched at ${fetchedTime} · Open-Meteo`,
  };
}
