"use client";

import type { ForecastResponse } from "@/lib/types";

interface ForecastStripProps {
  forecast: ForecastResponse | null;
  loading: boolean;
  error: string | null;
}

function formatHour(iso: string): string {
  // Open-Meteo returns naive local-ish timestamps (no offset) -- treat as
  // UTC for a stable, consistent display rather than letting the browser
  // guess a timezone.
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
}

export default function ForecastStrip({ forecast, loading, error }: ForecastStripProps) {
  return (
    <section className="rounded-xl border border-line bg-panel/40 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-accent">
        Short-Term Forecast
      </h2>
      <p className="mt-0.5 text-xs text-slate-500">Next hours · wind speed &amp; wave height</p>

      {loading && <p className="py-8 text-center text-sm text-accent">Loading forecast…</p>}

      {error && !loading && (
        <p className="mt-4 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
          {error}
        </p>
      )}

      {forecast && !loading && (
        <>
          {forecast.hours.length === 0 ? (
            <p className="py-8 text-center text-xs text-slate-500">No forecast data available.</p>
          ) : (
            <div className="mt-4 flex gap-2 overflow-x-auto pb-2 scroll-thin">
              {forecast.hours.map((h) => (
                <div
                  key={h.time}
                  className="flex min-w-[92px] flex-shrink-0 flex-col items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-3"
                >
                  <span className="text-[11px] uppercase tracking-wider text-slate-500">
                    {formatHour(h.time)}
                  </span>
                  <span className="font-mono text-sm font-bold text-accent">
                    {h.wind_speed_ms === null ? "—" : `${h.wind_speed_ms.toFixed(1)}`}
                    <span className="ml-0.5 text-[10px] font-normal text-slate-500">m/s</span>
                  </span>
                  <span className="font-mono text-xs text-slate-400">
                    {h.wave_height_m === null ? "—" : `${h.wave_height_m.toFixed(2)} m`}
                  </span>
                </div>
              ))}
            </div>
          )}

          {forecast.notes.length > 0 && (
            <div className="mt-3 flex flex-col gap-1.5">
              {forecast.notes.map((note, i) => (
                <p
                  key={i}
                  className="rounded-md border border-amber/30 bg-amber/10 px-3 py-2 text-xs text-amber"
                >
                  {note}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
