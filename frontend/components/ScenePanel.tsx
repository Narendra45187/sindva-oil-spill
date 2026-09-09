"use client";

import { useRef } from "react";
import type {
  DetectedRegion,
  DetectResponse,
  DriftForecastResponse,
  OriginEstimate,
  Scene,
  WeatherConditions,
} from "@/lib/types";
import { getClassificationStyle } from "@/lib/classification";
import WeatherPanel from "@/components/WeatherPanel";

const DRIFT_MINUTES_OPTIONS = [15, 30, 60];
const FORECAST_HOURS_OPTIONS = [3, 6, 12];

function windContext(region: DetectedRegion): { text: string; amber: boolean } {
  if (region.wind_speed_ms === null) {
    return { text: "Wind data unavailable — classification uses image features only.", amber: false };
  }
  const speed = region.wind_speed_ms.toFixed(1);
  if (region.low_wind_caution) {
    return {
      text: `Wind: ${speed} m/s (low) — calm-water look-alikes possible; classification wind-adjusted.`,
      amber: true,
    };
  }
  if (region.wind_speed_ms > 6) {
    return {
      text: `Wind: ${speed} m/s (high) — supports oil evidence; classification wind-adjusted.`,
      amber: false,
    };
  }
  return { text: `Wind: ${speed} m/s (moderate) — no adjustment applied.`, amber: false };
}

interface ScenePanelProps {
  scene: Scene;
  result: DetectResponse | null;
  loading: boolean;
  error: string | null;
  onAnalyze: () => void;
  onUpload: (file: File) => void;
  weather: WeatherConditions | null;
  weatherLoading: boolean;
  weatherError: string | null;
  origin: OriginEstimate | null;
  originLoading: boolean;
  driftMinutes: number;
  onDriftMinutesChange: (minutes: number) => void;
  forecast: DriftForecastResponse | null;
  forecastLoading: boolean;
  forecastHours: number;
  onForecastHoursChange: (hours: number) => void;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className="text-right font-mono text-xs text-slate-300">{value}</span>
    </div>
  );
}

export default function ScenePanel({
  scene,
  result,
  loading,
  error,
  onAnalyze,
  onUpload,
  weather,
  weatherLoading,
  weatherError,
  origin,
  originLoading,
  driftMinutes,
  onDriftMinutesChange,
  forecast,
  forecastLoading,
  forecastHours,
  onForecastHoursChange,
}: ScenePanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const meta = result?.meta ?? null;
  const activeScene = result?.scene ?? scene;
  const regions = meta?.regions ?? [];
  const primary = regions.length > 0 ? regions[0] : null;
  const primaryStyle = primary ? getClassificationStyle(primary.classification) : null;

  return (
    <aside className="flex h-full flex-col gap-4 overflow-y-auto scroll-thin p-4">
      <div>
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
          Scene &amp; Detection
        </h2>
      </div>

      {/* Source scene card */}
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Source Scene
        </h3>
        <div className="divide-y divide-line/60">
          <Field label="Region" value={activeScene.name} />
          <Field label="Sensor" value={activeScene.sensor} />
          <Field
            label="Pass time"
            value={activeScene.timestamp.replace("T", " ").replace("Z", "Z")}
          />
          <Field
            label="Center"
            value={`${activeScene.center.lat.toFixed(3)}°, ${activeScene.center.lon.toFixed(3)}°`}
          />
        </div>
      </section>

      {/* Actions */}
      <section className="flex flex-col gap-2 rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Run Detection
        </h3>

        <button
          onClick={onAnalyze}
          disabled={loading}
          className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-lg border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading && (
            <span className="absolute inset-0 overflow-hidden">
              <span className="scan-sweep absolute inset-x-0 h-1/3 bg-gradient-to-b from-transparent via-accent/20 to-transparent" />
            </span>
          )}
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
            <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          {loading ? "Analyzing Scene…" : "Analyze Visakhapatnam Scene"}
        </button>

        <div className="mt-1 flex items-center gap-2">
          <div className="h-px flex-1 bg-line" />
          <span className="text-[10px] uppercase tracking-wider text-slate-600">or</span>
          <div className="h-px flex-1 bg-line" />
        </div>

        <label className="flex w-full cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-line px-4 py-3 text-center transition hover:border-accent/40 hover:bg-white/[0.02]">
          <span className="text-xs font-medium text-slate-300">Upload SAR GeoTIFF</span>
          <span className="text-[10px] text-slate-500">.tif / .tiff scenes</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".tif,.tiff,image/tiff"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
        </label>

        {error && (
          <p className="rounded-md border border-red/30 bg-red/10 px-3 py-2 text-xs text-red">
            {error}
          </p>
        )}
      </section>

      {/* Results */}
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Detection Result
        </h3>

        {!meta && !loading && (
          <p className="py-4 text-center text-xs text-slate-500">
            No analysis run yet. Analyze the scene to detect oil-spill signatures.
          </p>
        )}

        {loading && (
          <p className="py-4 text-center text-xs text-accent">
            Running SAR dark-spot detection…
          </p>
        )}

        {meta && !loading && (
          <div className="flex flex-col gap-3">
            {/* Classification badge for the primary (highest-oil-confidence) region */}
            {primary && primaryStyle ? (
              <div
                className={`flex items-center justify-between rounded-lg border px-3 py-2 ${primaryStyle.bg} ${primaryStyle.ring}`}
              >
                <span className="text-xs font-medium text-slate-300">
                  {meta.region_count} region{meta.region_count !== 1 ? "s" : ""} detected
                </span>
                <span className={`text-xs font-bold uppercase tracking-wide ${primaryStyle.color}`}>
                  {primaryStyle.label}
                </span>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-lg border border-slate-500/30 bg-slate-500/10 px-3 py-2">
                <span className="text-xs font-medium text-slate-300">No spill signature found</span>
              </div>
            )}

            {/* Oil-confidence bar */}
            {primary && primaryStyle && (
              <div>
                <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-600">
                  <span>Oil confidence</span>
                  <span className={`font-mono font-bold ${primaryStyle.color}`}>
                    {primary.oil_confidence.toFixed(1)}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.04]">
                  <div
                    className={`h-full rounded-full ${primaryStyle.dot} transition-all duration-500`}
                    style={{ width: `${Math.max(0, Math.min(100, primary.oil_confidence))}%` }}
                  />
                </div>
              </div>
            )}

            {/* Wind context: an adjustment layer on top of the image-feature
                score, not a replacement -- see windContext() above. */}
            {primary && (
              <p className={`text-[11px] ${windContext(primary).amber ? "text-amber" : "text-slate-500"}`}>
                {windContext(primary).text}
              </p>
            )}

            <div className="divide-y divide-line/60">
              <Field
                label="Centroid"
                value={
                  meta.centroid
                    ? `${meta.centroid.lat.toFixed(4)}°, ${meta.centroid.lon.toFixed(4)}°`
                    : "—"
                }
              />
              <Field label="Regions found" value={`${meta.region_count}`} />
              <Field
                label="Analyzed at"
                value={new Date(
                  meta.timestamp.replace(
                    /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})\d*$/,
                    "$1-$2-$3T$4:$5:$6Z"
                  )
                ).toLocaleTimeString()}
              />
            </div>

            {/* Spill parameters -- existing area/length/width plus perimeter,
                orientation, and a clearly-labeled rough volume estimate. */}
            <div>
              <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">
                Spill Parameters
              </h4>
              <div className="divide-y divide-line/60">
                <Field
                  label="Area"
                  value={
                    primary ? `${primary.area_km2.toFixed(3)} km²` : `${meta.area_km2.toFixed(3)} km²`
                  }
                />
                <Field label="Length" value={primary ? `${primary.length_km.toFixed(3)} km` : "—"} />
                <Field label="Width" value={primary ? `${primary.width_km.toFixed(3)} km` : "—"} />
                <Field
                  label="Perimeter"
                  value={primary ? `${primary.perimeter_km.toFixed(3)} km` : "—"}
                />
                <Field
                  label="Orientation"
                  value={primary ? `${primary.orientation_deg.toFixed(1)}°` : "—"}
                />
                <Field
                  label="Est. Volume"
                  value={primary ? `${primary.estimated_volume_m3.toLocaleString(undefined, { maximumFractionDigits: 1 })} m³` : "—"}
                />
              </div>
              {primary && (
                <p className="mt-1 text-[10px] italic text-slate-600">
                  (est. · assumes {(primary.assumed_thickness_m * 1000).toFixed(0)} mm film — order-of-magnitude only, not a measured volume)
                </p>
              )}
            </div>

            {/* Per-region breakdown, when more than one region is on the water */}
            {regions.length > 1 && (
              <div>
                <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">
                  All Regions
                </h4>
                <div className="flex flex-col gap-1.5">
                  {regions.map((r, i) => {
                    const style = getClassificationStyle(r.classification);
                    return (
                      <div
                        key={i}
                        className={`flex items-center justify-between rounded-md border px-2.5 py-1.5 ${style.bg} ${style.ring}`}
                      >
                        <span className="text-[11px] text-slate-300">
                          Region {i + 1} · {r.area_km2.toFixed(2)} km²
                        </span>
                        <span className={`font-mono text-[11px] font-bold ${style.color}`}>
                          {r.oil_confidence.toFixed(0)}% · {style.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Origin estimation -- back-tracked from the spill against the
          combined wind+current drift. Always presented as an ESTIMATE,
          never a confirmed release point. */}
      {meta && (
        <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Origin Estimation <span className="normal-case text-slate-600">(estimated)</span>
            </h3>
            <div className="flex gap-1">
              {DRIFT_MINUTES_OPTIONS.map((m) => (
                <button
                  key={m}
                  onClick={() => onDriftMinutesChange(m)}
                  className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold transition ${
                    driftMinutes === m
                      ? "border-red/50 bg-red/10 text-red"
                      : "border-line text-slate-500 hover:border-red/30 hover:text-slate-300"
                  }`}
                >
                  {m}m
                </button>
              ))}
            </div>
          </div>

          {originLoading && (
            <p className="py-3 text-center text-xs text-accent">Estimating back-drift…</p>
          )}

          {!originLoading && origin?.available && (
            <>
              <div className="divide-y divide-line/60">
                <Field
                  label="Origin zone"
                  value={`${origin.origin_zone.center_lat.toFixed(3)}°, ${origin.origin_zone.center_lon.toFixed(3)}° · ± ${origin.origin_zone.radius_km.toFixed(2)} km`}
                />
                <Field
                  label="Release window"
                  value={origin.release_window ? origin.release_window.display : "—"}
                />
                <Field label="Origin confidence" value={`${origin.origin_confidence.toFixed(0)}%`} />
                <Field label="Drift distance (nominal)" value={`${origin.drift_distance_km.toFixed(2)} km`} />
                <Field label="Drift bearing" value={`${origin.drift_bearing_deg.toFixed(0)}°`} />
                <Field label="Assumed drift time (nominal)" value={`${origin.drift_minutes} min`} />
              </div>
              <p className="mt-1.5 text-[10px] italic text-slate-600">{origin.method_note}</p>
            </>
          )}

          {!originLoading && origin && !origin.available && (
            <p className="py-3 text-center text-xs text-slate-500">{origin.message}</p>
          )}

          {!originLoading && !origin && (
            <p className="py-3 text-center text-xs text-slate-600">
              Origin estimate will appear once weather conditions load.
            </p>
          )}
        </section>
      )}

      {/* Drift forecast -- the forward counterpart to Origin Estimation
          above: same wind+current drift model, projected FORWARD from the
          spill instead of backward. Always presented as a PREDICTION with
          growing uncertainty over time, never a certain future track. */}
      {meta && (
        <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Drift Forecast <span className="normal-case text-slate-600">(predicted)</span>
            </h3>
            <div className="flex gap-1">
              {FORECAST_HOURS_OPTIONS.map((h) => (
                <button
                  key={h}
                  onClick={() => onForecastHoursChange(h)}
                  className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold transition ${
                    forecastHours === h
                      ? "border-accent/50 bg-accent/10 text-accent"
                      : "border-line text-slate-500 hover:border-accent/30 hover:text-slate-300"
                  }`}
                >
                  {h}h
                </button>
              ))}
            </div>
          </div>

          {forecastLoading && (
            <p className="py-3 text-center text-xs text-accent">Projecting forward drift…</p>
          )}

          {!forecastLoading && forecast?.available && (
            <>
              <div className="divide-y divide-line/60">
                <Field
                  label="Predicted displacement"
                  value={`${forecast.total_displacement_km.toFixed(2)} km`}
                />
                <Field label="Drift bearing" value={`${forecast.drift_bearing_deg.toFixed(0)}°`} />
                <Field label="Horizon" value={`${forecast.horizon_hours}h`} />
                <Field
                  label="Uncertainty at horizon"
                  value={`± ${forecast.points[forecast.points.length - 1]?.uncertainty_km.toFixed(2) ?? "—"} km`}
                />
              </div>
              <p className="mt-1.5 text-[10px] italic text-slate-600">{forecast.method_note}</p>
            </>
          )}

          {!forecastLoading && forecast && !forecast.available && (
            <p className="py-3 text-center text-xs text-slate-500">{forecast.message}</p>
          )}

          {!forecastLoading && !forecast && (
            <p className="py-3 text-center text-xs text-slate-600">
              Drift forecast will appear once weather conditions load.
            </p>
          )}
        </section>
      )}

      <WeatherPanel weather={weather} loading={weatherLoading} error={weatherError} />
    </aside>
  );
}
