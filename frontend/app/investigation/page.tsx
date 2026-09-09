"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import SpeedSparkline from "@/components/SpeedSparkline";
import CciBreakdown from "@/components/CciBreakdown";
import EvidenceFusionPanel from "@/components/EvidenceFusionPanel";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import type { FusionResponse, InvestigationResponse } from "@/lib/types";

const InvestigationMap = dynamic(() => import("@/components/InvestigationMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center rounded-xl border border-line bg-panel text-sm text-slate-500">
      Loading map…
    </div>
  ),
});

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className="text-right font-mono text-xs text-slate-300">{value}</span>
    </div>
  );
}

function FlagBadge({ detected, label }: { detected: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
        detected ? "border-red/40 bg-red/10 text-red" : "border-line bg-white/[0.02] text-slate-500"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${detected ? "bg-red" : "bg-slate-600"}`} />
      {label}: {detected ? "Detected" : "Not detected"}
    </span>
  );
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function fmtLatLon(pos: { lat: number; lon: number } | null): string {
  if (!pos) return "—";
  return `${pos.lat.toFixed(4)}°, ${pos.lon.toFixed(4)}°`;
}

export default function InvestigationPage() {
  const [data, setData] = useState<InvestigationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fusion, setFusion] = useState<FusionResponse | null>(null);
  const [fusionLoading, setFusionLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/investigation`);
        if (!res.ok) throw new Error(`Investigation service returned ${res.status}`);
        const result: InvestigationResponse = await res.json();
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? `Could not load investigation — ${err.message}` : "Could not load investigation.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    async function loadFusion() {
      setFusionLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/fusion`);
        const result: FusionResponse = await res.json();
        if (!cancelled) setFusion(result);
      } catch (err) {
        if (!cancelled) {
          setFusion({
            available: false,
            message: err instanceof Error ? `Could not fuse evidence — ${err.message}` : "Could not fuse evidence.",
          });
        }
      } finally {
        if (!cancelled) setFusionLoading(false);
      }
    }
    load();
    loadFusion();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar timestamp={DEFAULT_SCENE.timestamp} />
      <NavBar />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 p-4">
        <div>
          <h1 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
            AIS Investigation
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Behavioral case file built from the likely offender&apos;s own AIS track.
          </p>
        </div>

        {loading && <p className="py-16 text-center text-sm text-accent">Loading investigation…</p>}

        {error && !loading && (
          <p className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
        )}

        {data && !data.available && !loading && (
          <div className="rounded-xl border border-amber/30 bg-amber/10 px-5 py-6 text-center">
            <p className="text-sm font-medium text-amber">
              {data.message || "Run detection + AIS correlation on the Dashboard first."}
            </p>
          </div>
        )}

        {data && data.available && !loading && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
            {/* Left column: case file */}
            <div className="flex flex-col gap-4">
              {/* Suspect header */}
              <section className="rounded-xl border border-red/30 bg-red/5 p-4 shadow-lg shadow-black/20">
                <p className="text-[11px] uppercase tracking-wider text-slate-500">Suspect Vessel</p>
                <p className="mt-0.5 text-lg font-bold text-slate-100">{data.vessel.name}</p>
                <p className="font-mono text-[11px] text-slate-500">
                  MMSI {data.vessel.mmsi} · {data.vessel.vessel_type}
                </p>
                <div className="mt-3 divide-y divide-line/60">
                  <Field
                    label="Dimensions (L × W × Draft)"
                    value={
                      data.attribution.length_m !== null
                        ? `${data.attribution.length_m.toFixed(0)} × ${data.attribution.width_m?.toFixed(0)} × ${data.attribution.draft_m?.toFixed(1)} m`
                        : "—"
                    }
                  />
                  <Field label="Culprit Correlation Index" value={`CCI: ${data.cci.toFixed(1)}/100`} />
                </div>
              </section>

              {/* Dark-vessel anomaly banner -- only shown when a detected
                  gap actually overlaps the spill window. Worded as an
                  anomaly signal, never as proof. */}
              {data.dark_vessel_flag && (
                <div className="rounded-xl border-2 border-red/50 bg-red/10 px-4 py-3 text-center">
                  <p className="text-xs font-bold uppercase tracking-wide text-red">
                    ⚠ Dark Vessel Anomaly — AIS gap during spill window
                  </p>
                  <p className="mt-1 text-[11px] text-red/80">(not proof of intent)</p>
                </div>
              )}

              {/* Culprit Correlation Index -- the full, transparent
                  weighted-factor computation behind this vessel's rank. */}
              <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Culprit Correlation Index
                  </h3>
                  <span className="font-mono text-sm font-bold text-accent">{data.cci.toFixed(1)}/100</span>
                </div>
                <CciBreakdown cci={data.cci} breakdown={data.cci_breakdown} note={data.cci_note} />
              </section>

              {/* Evidence */}
              <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Evidence</h3>
                <div className="divide-y divide-line/60">
                  <Field label="Distance to spill" value={`${data.attribution.min_distance_km.toFixed(2)} km`} />
                  <Field
                    label="Time before detection"
                    value={`${Math.abs(data.attribution.time_gap_min).toFixed(0)} min ${data.attribution.time_gap_min >= 0 ? "before" : "after"}`}
                  />
                  <Field label="Track intersects spill" value={data.attribution.intersects ? "Yes" : "No"} />
                </div>
              </section>

              {/* Behavioral analysis */}
              <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Behavioral Analysis
                </h3>

                <p className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">Speed profile (SOG)</p>
                <SpeedSparkline points={data.speed_profile} slowdownTime={data.slowdown_at?.time ?? null} />
                <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                  <div>
                    <p className="font-mono text-sm font-bold text-slate-200">
                      {data.speed_stats.min_speed_kn?.toFixed(1) ?? "—"}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-600">Min kn</p>
                  </div>
                  <div>
                    <p className="font-mono text-sm font-bold text-slate-200">
                      {data.speed_stats.avg_speed_kn?.toFixed(1) ?? "—"}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-600">Avg kn</p>
                  </div>
                  <div>
                    <p className="font-mono text-sm font-bold text-slate-200">
                      {data.speed_stats.max_speed_kn?.toFixed(1) ?? "—"}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-slate-600">Max kn</p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <FlagBadge detected={data.slowdown_detected} label="Slowdown" />
                  <FlagBadge detected={data.loitering_detected} label="Loitering" />
                  <FlagBadge detected={data.course_change_detected} label="Course change" />
                </div>

                {data.slowdown_detected && data.slowdown_at && (
                  <p className="mt-2 text-[11px] text-slate-500">
                    Dropped to {data.slowdown_at.sog?.toFixed(1)} kn at {fmtTime(data.slowdown_at.time)}.
                  </p>
                )}
                {data.loitering_detected && data.loitering_at && (
                  <p className="mt-1 text-[11px] text-slate-500">
                    Held near-stationary speed for {data.loitering_points} consecutive reports starting {fmtTime(data.loitering_at.time)}.
                  </p>
                )}
                {data.course_change_detected && data.course_changes.length > 0 && (
                  <p className="mt-1 text-[11px] text-slate-500">
                    Largest course change: {data.course_changes[0].change_deg.toFixed(0)}° at{" "}
                    {fmtTime(data.course_changes[0].time)}.
                  </p>
                )}

                {data.nearest_approach && (
                  <div className="mt-3 border-t border-line/60 pt-3">
                    <p className="mb-1 text-[11px] uppercase tracking-wider text-slate-500">Nearest approach</p>
                    <div className="divide-y divide-line/60">
                      <Field label="Distance" value={`${data.nearest_approach.distance_km.toFixed(2)} km`} />
                      <Field label="Time" value={fmtTime(data.nearest_approach.time)} />
                      <Field
                        label="Relative to detection"
                        value={`${Math.abs(data.nearest_approach.time_gap_min).toFixed(0)} min ${data.nearest_approach.before_detection ? "before" : "after"}`}
                      />
                    </div>
                  </div>
                )}
              </section>

              {/* AIS transmission analysis (gap / "dark vessel" detection) */}
              <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    AIS Transmission Analysis
                  </h3>
                  <FlagBadge detected={data.ais_gaps.length > 0} label="Gap" />
                </div>

                {data.ais_gaps.length === 0 && (
                  <p className="py-3 text-center text-xs text-slate-600">
                    No AIS transmission gaps detected — the vessel reported continuously.
                  </p>
                )}

                {data.ais_gaps.map((gap, i) => (
                  <div key={i} className={i > 0 ? "mt-3 border-t border-line/60 pt-3" : ""}>
                    <div className="divide-y divide-line/60">
                      <Field label="Gap start" value={fmtTime(gap.gap_start)} />
                      <Field label="Gap end" value={fmtTime(gap.gap_end)} />
                      <Field label="Duration" value={`${gap.gap_duration_min.toFixed(0)} min`} />
                      <Field
                        label="Overlaps spill window"
                        value={gap.overlaps_spill_window ? "Yes" : "No"}
                      />
                    </div>
                  </div>
                ))}

                {data.total_dark_minutes > 0 && (
                  <p className="mt-2 text-[11px] text-slate-500">
                    Total dark time: {data.total_dark_minutes.toFixed(0)} min across{" "}
                    {data.ais_gaps.length} gap{data.ais_gaps.length !== 1 ? "s" : ""}.
                  </p>
                )}

                <p className="mt-2 rounded-md border border-amber/30 bg-amber/5 px-2.5 py-2 text-[11px] text-amber">
                  {data.dark_vessel_note}
                </p>
              </section>

              {/* Voyage context */}
              <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Voyage Context
                </h3>
                <div className="divide-y divide-line/60">
                  <Field label="Entered area" value={fmtTime(data.voyage_context.entry_time)} />
                  <Field label="Entry position" value={fmtLatLon(data.voyage_context.entry_position)} />
                  <Field label="Exited area" value={fmtTime(data.voyage_context.exit_time)} />
                  <Field label="Exit position" value={fmtLatLon(data.voyage_context.exit_position)} />
                  <Field
                    label="Time in area"
                    value={data.voyage_context.time_in_area_min !== null ? `${data.voyage_context.time_in_area_min.toFixed(0)} min` : "—"}
                  />
                </div>
              </section>

              {/* Investigation summary */}
              <section className="rounded-xl border border-accent/40 bg-accent/5 p-4 shadow-lg shadow-black/20">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-accent">
                  Investigation Summary
                </h3>
                <p className="text-sm leading-relaxed text-slate-200">{data.investigation_summary}</p>
                <p className="mt-2 text-[10px] italic text-slate-600">
                  Generated automatically from the vessel&apos;s own AIS track — reflects only behavior actually
                  detected above.
                </p>
              </section>

              {/* Overall Attribution Confidence -- fuses detection, origin,
                  and CCI into one honest, transparent evidence-chain verdict. */}
              <EvidenceFusionPanel fusion={fusion} loading={fusionLoading} />
            </div>

            {/* Right column: focused map */}
            <div className="min-h-[520px] lg:sticky lg:top-4 lg:h-[calc(100vh-7rem)]">
              <InvestigationMap
                vesselName={data.vessel.name}
                track={data.track_points}
                spillCentroid={data.spill.centroid}
                spillAreaKm2={data.spill.area_km2}
                nearestApproach={data.nearest_approach}
                aisGaps={data.ais_gaps}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
