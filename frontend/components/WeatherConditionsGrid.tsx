"use client";

import type { WeatherConditions } from "@/lib/types";
import { degToCompass } from "@/lib/compass";
import { weatherSourceDisplay } from "@/lib/weatherSource";

interface WeatherConditionsGridProps {
  weather: WeatherConditions | null;
  loading: boolean;
  error: string | null;
}

function WindIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
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
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
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
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
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
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
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
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
      <circle cx="12" cy="13" r="7.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 13l3-3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 3.5h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function StatCard({
  icon,
  label,
  value,
  unit,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit: string;
  sub?: string;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-panel p-5 shadow-lg shadow-black/20">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent">
        {icon}
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
        <p className="mt-1 font-mono text-2xl font-bold text-slate-100">
          {value}
          {value !== "—" && <span className="ml-1 text-sm font-medium text-slate-500">{unit}</span>}
        </p>
        {sub && <p className="mt-1 font-mono text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

function fmt(value: number | null, digits = 1): string {
  return value === null ? "—" : value.toFixed(digits);
}

export default function WeatherConditionsGrid({ weather, loading, error }: WeatherConditionsGridProps) {
  return (
    <section className="rounded-xl border border-line bg-panel/40 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-accent">
            Live Conditions
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">Visakhapatnam spill region</p>
        </div>
        {weather &&
          (() => {
            const src = weatherSourceDisplay(weather);
            return (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] uppercase tracking-wider ${src.ringClass} ${src.bgClass} ${src.textClass}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${src.dotClass} ${weather.source === "live" ? "pulse-dot" : ""}`} />
                {src.label}
              </span>
            );
          })()}
      </div>

      {loading && (
        <p className="py-10 text-center text-sm text-accent">Fetching live conditions…</p>
      )}

      {error && !loading && (
        <p className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      )}

      {weather && !loading && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard
              icon={<WindIcon />}
              label="Wind Speed"
              value={fmt(weather.wind_speed_ms)}
              unit="m/s"
              sub={weather.wind_direction !== null ? `${degToCompass(weather.wind_direction)} · ${Math.round(weather.wind_direction)}°` : undefined}
            />
            <StatCard
              icon={<WaveIcon />}
              label="Wave Height"
              value={fmt(weather.wave_height_m, 2)}
              unit="m"
            />
            <StatCard
              icon={<CurrentIcon />}
              label="Ocean Current"
              value={fmt(weather.current_velocity_ms)}
              unit="m/s"
              sub={weather.current_direction !== null ? `${degToCompass(weather.current_direction)} · ${Math.round(weather.current_direction)}°` : undefined}
            />
            <StatCard
              icon={<TempIcon />}
              label="Temperature"
              value={fmt(weather.temperature_c)}
              unit="°C"
            />
            <StatCard
              icon={<PressureIcon />}
              label="Pressure"
              value={fmt(weather.surface_pressure_hpa, 0)}
              unit="hPa"
            />
          </div>

          {weather.notes.length > 0 && (
            <div className="mt-4 flex flex-col gap-1.5">
              {weather.notes.map((note, i) => (
                <p
                  key={i}
                  className="rounded-md border border-amber/30 bg-amber/10 px-3 py-2 text-xs text-amber"
                >
                  {note}
                </p>
              ))}
            </div>
          )}

          <p className="mt-4 text-center text-[11px] text-slate-600">{weatherSourceDisplay(weather).caption}</p>
        </>
      )}
    </section>
  );
}
