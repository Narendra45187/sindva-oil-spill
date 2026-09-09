"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import { degToCompass } from "@/lib/compass";
import type { IncidentFull, ReportAvailable, ReportResponse, ReportSuspect } from "@/lib/types";

// Viewing a specific logged incident (?id=...) reuses the exact same report
// rendering as the "latest" flow -- this adapter is the only thing that
// changes, mapping an incident record onto the same ReportAvailable shape
// so the JSX below never needs to know which source the data came from.
function incidentToReport(incident: IncidentFull): ReportAvailable & { incident_id: string } {
  return {
    available: true,
    generated_at: incident.logged_at,
    scene: incident.scene,
    spill: incident.spill,
    weather: incident.weather,
    attribution: incident.attribution,
    overlay_url: incident.overlay_url,
    incident_id: incident.incident_id,
  };
}

function reportId(generatedAt: string): string {
  const d = new Date(generatedAt);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `SINDVA-${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}-${pad(
    d.getUTCHours()
  )}${pad(d.getUTCMinutes())}`;
}

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

function fmtWithDir(speed: number | null, dirDeg: number | null, unit: string): string {
  if (speed === null) return "—";
  const base = `${speed.toFixed(1)} ${unit}`;
  return dirDeg === null ? base : `${base} (${degToCompass(dirDeg)}, ${Math.round(dirDeg)}°)`;
}

function timeBeforeLabel(minutes: number): string {
  const mins = Math.round(Math.abs(minutes));
  return minutes >= 0 ? `${mins} min before detection` : `${mins} min after detection`;
}

function classificationBadgeClass(classification: string): string {
  if (classification === "LIKELY OIL SPILL") return "border-amber-300 bg-amber-50 text-amber-800";
  if (classification === "UNCERTAIN") return "border-slate-300 bg-slate-50 text-slate-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function severityBadgeClass(severity: string): string {
  if (severity === "Severe") return "border-red-300 bg-red-50 text-red-700";
  if (severity === "Moderate") return "border-amber-300 bg-amber-50 text-amber-800";
  if (severity === "Minor") return "border-green-300 bg-green-50 text-green-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-slate-200 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono font-medium text-slate-900">{value}</span>
    </div>
  );
}

function SuspectRow({ suspect, rank }: { suspect: ReportSuspect; rank: number }) {
  return (
    <tr className="border-b border-slate-200 text-sm">
      <td className="py-1.5 pr-3 font-mono text-slate-500">#{rank}</td>
      <td className="py-1.5 pr-3 font-medium text-slate-900">{suspect.name}</td>
      <td className="py-1.5 pr-3 font-mono text-slate-600">{suspect.mmsi}</td>
      <td className="py-1.5 pr-3 text-slate-600">{suspect.type}</td>
      <td className="py-1.5 pr-3 text-right font-mono font-semibold text-slate-900">
        {suspect.confidence.toFixed(1)}%
      </td>
      <td className="py-1.5 pr-3 text-right font-mono text-slate-600">
        {suspect.distance_km.toFixed(2)} km
      </td>
      <td className="py-1.5 text-right text-slate-600">{suspect.intersects ? "Yes" : "No"}</td>
    </tr>
  );
}

function buildConclusion(report: Extract<ReportResponse, { available: true }>): string {
  const { spill, attribution } = report;
  const offender = attribution.likely_offender;
  const timePhrase =
    offender.time_before_min >= 0
      ? `${Math.round(offender.time_before_min)} minutes before detection`
      : `${Math.round(Math.abs(offender.time_before_min))} minutes after detection`;
  return (
    `Based on satellite SAR detection and AIS correlation, vessel ${offender.name} ` +
    `(MMSI ${offender.mmsi}) is the likely source of the detected oil spill ` +
    `(~${spill.area_km2.toFixed(2)} km²) at ${spill.centroid.lat.toFixed(4)}, ` +
    `${spill.centroid.lon.toFixed(4)}, having passed within ${offender.distance_km.toFixed(2)} km ` +
    `of the spill ${timePhrase}.`
  );
}

function ReportsPageContent() {
  const searchParams = useSearchParams();
  const incidentId = searchParams.get("id");

  const [report, setReport] = useState<(ReportResponse & { incident_id?: string }) | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/report/latest`);
      if (!res.ok) throw new Error(`Report service returned ${res.status}`);
      const data: ReportResponse = await res.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? `Could not generate report — ${err.message}` : "Could not generate report.");
    } finally {
      setLoading(false);
    }
  };

  // ?id=<incident_id> present: load that logged incident automatically
  // instead of waiting for "Generate Report" (which always means "latest").
  useEffect(() => {
    if (!incidentId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/incidents/${incidentId}`);
        if (!res.ok) {
          throw new Error(res.status === 404 ? "Incident not found." : `Incident service returned ${res.status}`);
        }
        const data: IncidentFull = await res.json();
        if (!cancelled) setReport(incidentToReport(data));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? `Could not load incident — ${err.message}` : "Could not load incident.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  return (
    <div className="flex min-h-screen flex-col">
      <div className="no-print">
        <TopBar timestamp={DEFAULT_SCENE.timestamp} />
        <NavBar />
      </div>

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-4 p-4">
        <div className="no-print flex items-center justify-between">
          <div>
            <h1 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
              Reports
            </h1>
            <p className="mt-0.5 text-xs text-slate-500">
              Consolidated incident report from the latest detection, correlation, and weather results.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {incidentId ? (
              <span className="font-mono text-xs text-slate-500">Viewing logged incident {incidentId}</span>
            ) : (
              <button
                onClick={generateReport}
                disabled={loading}
                className="rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Generating…" : "Generate Report"}
              </button>
            )}
            {report?.available && (
              <button
                onClick={() => window.print()}
                className="rounded-lg border border-line bg-panel px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-accent/40 hover:text-accent"
              >
                Download / Print
              </button>
            )}
          </div>
        </div>

        {error && (
          <p className="no-print rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
            {error}
          </p>
        )}

        {!report && !loading && !error && (
          <p className="no-print py-16 text-center text-sm text-slate-500">
            {incidentId
              ? "Loading incident…"
              : 'Click "Generate Report" to build the incident report from the latest results.'}
          </p>
        )}

        {report && !report.available && (
          <div className="no-print rounded-xl border border-amber/30 bg-amber/10 px-5 py-6 text-center">
            <p className="text-sm font-medium text-amber">{report.message}</p>
          </div>
        )}

        {report && report.available && (
          <article className="report-sheet rounded-xl border border-slate-200 bg-white p-8 text-slate-900 shadow-2xl shadow-black/40">
            {/* Header */}
            <div className="flex items-start justify-between border-b-2 border-slate-900 pb-4">
              <div>
                <h2 className="text-xl font-bold tracking-tight">OIL SPILL INCIDENT REPORT</h2>
                <p className="mt-1 font-mono text-xs text-slate-500">
                  Report ID: {report.incident_id ?? reportId(report.generated_at)}
                </p>
              </div>
              <div className="text-right">
                <p className="font-mono text-xs text-slate-500">
                  Generated: {new Date(report.generated_at).toLocaleString()}
                </p>
                <p className="mt-1 text-xs font-semibold uppercase tracking-wider text-slate-700">
                  SIH26143 · NTRO
                </p>
              </div>
            </div>

            {/* 1. Scene */}
            <section className="mt-6">
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                1. Scene
              </h3>
              <DataRow label="Region" value={report.scene.name} />
              <DataRow label="Sensor" value={report.scene.sensor} />
              <DataRow
                label="Satellite Pass-Time"
                value={new Date(report.scene.timestamp).toUTCString()}
              />
              <DataRow
                label="Scene Center"
                value={`${report.scene.center.lat.toFixed(3)}°, ${report.scene.center.lon.toFixed(3)}°`}
              />
            </section>

            {/* 2. Spill Detection */}
            <section className="mt-6">
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                2. Spill Detection
              </h3>
              <div className="mb-3 flex flex-wrap gap-2">
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${classificationBadgeClass(report.spill.classification)}`}
                >
                  {report.spill.classification}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${severityBadgeClass(report.spill.severity)}`}
                >
                  {report.spill.severity} severity
                </span>
                <span className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs font-mono font-bold text-slate-700">
                  {report.spill.oil_confidence.toFixed(1)}% confidence
                </span>
              </div>
              <DataRow label="Area" value={`${report.spill.area_km2.toFixed(3)} km²`} />
              <DataRow label="Length" value={`${report.spill.length_km.toFixed(3)} km`} />
              <DataRow label="Width" value={`${report.spill.width_km.toFixed(3)} km`} />
              <DataRow
                label="Centroid"
                value={`${report.spill.centroid.lat.toFixed(4)}°, ${report.spill.centroid.lon.toFixed(4)}°`}
              />
              <DataRow label="Regions Detected" value={`${report.spill.regions.length}`} />

              {report.overlay_url && (
                <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
                  {/* Detection overlay: real image from the last run, not a placeholder. */}
                  <img
                    src={`${API_BASE}${report.overlay_url}`}
                    alt="Detection overlay showing the traced spill boundary"
                    className="w-full bg-slate-900"
                  />
                </div>
              )}
            </section>

            {/* 3. Environmental Conditions */}
            <section className="mt-6">
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                3. Environmental Conditions
              </h3>
              {report.weather ? (
                <>
                  <DataRow
                    label="Wind"
                    value={fmtWithDir(report.weather.wind_speed_ms, report.weather.wind_direction, "m/s")}
                  />
                  <DataRow label="Wave Height" value={`${fmt(report.weather.wave_height_m, 2)} m`} />
                  <DataRow label="Ocean Current" value={`${fmt(report.weather.current_velocity_ms)} m/s`} />
                  <DataRow label="Temperature" value={`${fmt(report.weather.temperature_c)} °C`} />
                  <DataRow label="Pressure" value={`${fmt(report.weather.pressure_hpa, 0)} hPa`} />
                </>
              ) : (
                <p className="py-2 text-sm text-slate-500">Weather snapshot unavailable for this run.</p>
              )}
              <p className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                {report.spill.wind_context}
              </p>
            </section>

            {/* 4. Vessel Attribution */}
            <section className="mt-6">
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                4. Vessel Attribution
              </h3>
              <div className="rounded-lg border border-slate-300 bg-slate-50 p-4">
                <p className="text-[11px] uppercase tracking-wider text-slate-500">Likely Offender</p>
                <p className="mt-1 text-lg font-bold text-slate-900">
                  {report.attribution.likely_offender.name}
                </p>
                <p className="font-mono text-xs text-slate-500">
                  MMSI {report.attribution.likely_offender.mmsi} · {report.attribution.likely_offender.type}
                </p>
                <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="font-mono text-lg font-bold text-slate-900">
                      {report.attribution.likely_offender.confidence.toFixed(1)}%
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Confidence</p>
                  </div>
                  <div>
                    <p className="font-mono text-lg font-bold text-slate-900">
                      {report.attribution.likely_offender.distance_km.toFixed(2)} km
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Distance to Spill</p>
                  </div>
                  <div>
                    <p className="font-mono text-lg font-bold text-slate-900">
                      {report.attribution.likely_offender.intersects ? "Yes" : "No"}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Track Intersects</p>
                  </div>
                </div>
                <p className="mt-2 text-center text-xs text-slate-600">
                  {timeBeforeLabel(report.attribution.likely_offender.time_before_min)}
                </p>
              </div>

              <h4 className="mb-1.5 mt-4 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Suspect Ranking (Top {report.attribution.ranking.length})
              </h4>
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b-2 border-slate-300 text-left text-[10px] uppercase tracking-wider text-slate-500">
                    <th className="py-1 pr-3 font-medium">Rank</th>
                    <th className="py-1 pr-3 font-medium">Vessel</th>
                    <th className="py-1 pr-3 font-medium">MMSI</th>
                    <th className="py-1 pr-3 font-medium">Type</th>
                    <th className="py-1 pr-3 text-right font-medium">Confidence</th>
                    <th className="py-1 pr-3 text-right font-medium">Distance</th>
                    <th className="py-1 text-right font-medium">Intersects</th>
                  </tr>
                </thead>
                <tbody>
                  {report.attribution.ranking.map((s, i) => (
                    <SuspectRow key={s.mmsi} suspect={s} rank={i + 1} />
                  ))}
                </tbody>
              </table>
            </section>

            {/* 5. Conclusion */}
            <section className="mt-6 border-t-2 border-slate-900 pt-4">
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                5. Conclusion
              </h3>
              <p className="text-sm leading-relaxed text-slate-800">{buildConclusion(report)}</p>
            </section>

            <p className="mt-8 border-t border-slate-200 pt-3 text-center text-[10px] text-slate-400">
              Generated automatically by SINDVA Marine Watch from live satellite SAR detection and AIS
              correlation results. For official use — SIH26143 · NTRO.
            </p>
          </article>
        )}
      </main>
    </div>
  );
}

export default function ReportsPage() {
  // useSearchParams() requires a Suspense boundary around whatever reads it.
  return (
    <Suspense fallback={null}>
      <ReportsPageContent />
    </Suspense>
  );
}
