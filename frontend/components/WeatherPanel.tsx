"use client";

import type { WeatherConditions } from "@/lib/types";
import { degToCompass } from "@/lib/compass";
import { weatherSourceDisplay } from "@/lib/weatherSource";

interface WeatherPanelProps {
  weather: WeatherConditions | null;
  loading: boolean;
  error: string | null;
}

function WindIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
      <path
        d="M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h9a2.5 2.5 0 1 1-2.5 2.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function WaveIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
      <path
        d="M2 8c1.5-1.5 3-1.5 4.5 0s3 1.5 4.5 0 3-1.5 4.5 0 3 1.5 4.5 0M2 14c1.5-1.5 3-1.5 4.5 0s3 1.5 4.5 0 3-1.5 4.5 0 3 1.5 4.5 0M2 20c1.5-1.5 3-1.5 4.5 0s3 1.5 4.5 0 3-1.5 4.5 0 3 1.5 4.5 0"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CurrentIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
      <path
        d="M4 6c2 3 2 5 0 8M9 4c2 4 2 8 0 12M14 6c2 3 2 5 0 8M19 4c2 4 2 8 0 12"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path d="M14 2l3 2-3 2M5 20l-3-2 3-2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TempIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
      <path
        d="M12 14.5V4a2 2 0 1 0-4 0v10.5a4 4 0 1 0 4 0Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="17" r="1.4" fill="currentColor" />
    </svg>
  );
}

function PressureIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
      <circle cx="12" cy="13" r="7.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 13l3-3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 3.5h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function formatValue(value: number | null, unit: string, digits = 1): string {
  return value === null ? "—" : `${value.toFixed(digits)} ${unit}`;
}

function formatWithDirection(speed: number | null, dirDeg: number | null, unit: string): string {
  if (speed === null) return "—";
  const base = `${speed.toFixed(1)} ${unit}`;
  return dirDeg === null ? base : `${base} · ${degToCompass(dirDeg)} (${Math.round(dirDeg)}°)`;
}

function Row({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="text-accent/70">{icon}</span>
        {label}
      </span>
      <span className="text-right font-mono text-xs text-slate-300">{value}</span>
    </div>
  );
}

export default function WeatherPanel({ weather, loading, error }: WeatherPanelProps) {
  return (
    <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Weather &amp; Ocean Conditions
        </h3>
        {weather &&
          (() => {
            const src = weatherSourceDisplay(weather);
            return (
              <span className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider ${src.textClass}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${src.dotClass} ${weather.source === "live" ? "pulse-dot" : ""}`} />
                {src.label}
              </span>
            );
          })()}
      </div>

      {!weather && !loading && !error && (
        <p className="py-4 text-center text-xs text-slate-500">
          Run detection to load live conditions for the spill region.
        </p>
      )}

      {loading && (
        <p className="py-4 text-center text-xs text-accent">Fetching live conditions…</p>
      )}

      {error && !loading && (
        <p className="rounded-md border border-red/30 bg-red/10 px-3 py-2 text-xs text-red">
          {error}
        </p>
      )}

      {weather && !loading && (
        <div className="flex flex-col gap-2">
          <div className="divide-y divide-line/60">
            <Row
              icon={<WindIcon />}
              label="Wind"
              value={formatWithDirection(weather.wind_speed_ms, weather.wind_direction, "m/s")}
            />
            <Row icon={<WaveIcon />} label="Wave height" value={formatValue(weather.wave_height_m, "m", 2)} />
            <Row
              icon={<CurrentIcon />}
              label="Ocean current"
              value={formatWithDirection(weather.current_velocity_ms, weather.current_direction, "m/s")}
            />
            <Row icon={<TempIcon />} label="Temperature" value={formatValue(weather.temperature_c, "°C")} />
            <Row
              icon={<PressureIcon />}
              label="Pressure"
              value={formatValue(weather.surface_pressure_hpa, "hPa", 0)}
            />
          </div>

          {weather.notes.length > 0 && (
            <div className="flex flex-col gap-1">
              {weather.notes.map((note, i) => (
                <p
                  key={i}
                  className="rounded-md border border-amber/30 bg-amber/10 px-2.5 py-1.5 text-[11px] text-amber"
                >
                  {note}
                </p>
              ))}
            </div>
          )}

          <p className="text-center text-[10px] text-slate-600">{weatherSourceDisplay(weather).caption}</p>
        </div>
      )}
    </section>
  );
}
