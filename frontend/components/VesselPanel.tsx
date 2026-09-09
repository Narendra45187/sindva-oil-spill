"use client";

import type { FusionResponse, Suspect } from "@/lib/types";
import CciBreakdown from "@/components/CciBreakdown";
import EvidenceFusionPanel from "@/components/EvidenceFusionPanel";

interface VesselPanelProps {
  canCorrelate: boolean;
  suspects: Suspect[] | null;
  loading: boolean;
  error: string | null;
  selectedMmsi: number | null;
  onCorrelate: () => void;
  onSelect: (mmsi: number) => void;
  fusion: FusionResponse | null;
  fusionLoading: boolean;
}

function PendingBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber/30 bg-amber/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber">
      <span className="h-1.5 w-1.5 rounded-full bg-amber pulse-dot" />
      Module 2 · Pending
    </span>
  );
}

function ShipIcon({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none">
      <path
        d="M4 18l2-8h12l2 8M6 10l1.5-5h9L18 10M2 21c1.6 0 1.6-1.5 3.2-1.5S6.8 21 8.4 21s1.6-1.5 3.2-1.5S13.2 21 14.8 21s1.6-1.5 3.2-1.5S19.6 21 21.2 21"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ConfidenceBar({ value, tone }: { value: number; tone: "hero" | "muted" }) {
  const barColor = tone === "hero" ? "bg-red" : "bg-accent";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.04]">
      <div
        className={`h-full rounded-full ${barColor} transition-all duration-500`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

function timeGapLabel(timeGapMin: number): string {
  const mins = Math.round(Math.abs(timeGapMin));
  return timeGapMin >= 0 ? `${mins} min before` : `${mins} min after`;
}

export default function VesselPanel({
  canCorrelate,
  suspects,
  loading,
  error,
  selectedMmsi,
  onCorrelate,
  onSelect,
  fusion,
  fusionLoading,
}: VesselPanelProps) {
  const hasResults = suspects !== null && suspects.length > 0;
  const topSuspect = hasResults ? suspects[0] : null;
  const selected =
    (hasResults && suspects.find((s) => s.mmsi === selectedMmsi)) || topSuspect;

  return (
    <aside className="flex h-full flex-col gap-4 overflow-y-auto scroll-thin p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
          Vessel Attribution
        </h2>
        {!hasResults && <PendingBadge />}
      </div>

      {/* Correlate action */}
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <button
          onClick={onCorrelate}
          disabled={!canCorrelate || loading}
          className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-lg border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading && (
            <span className="absolute inset-0 overflow-hidden">
              <span className="scan-sweep absolute inset-x-0 h-1/3 bg-gradient-to-b from-transparent via-accent/20 to-transparent" />
            </span>
          )}
          <ShipIcon className="h-4 w-4" />
          {loading ? "Correlating AIS Tracks…" : "Correlate AIS Tracks"}
        </button>
        {!canCorrelate && (
          <p className="mt-2 text-center text-[11px] text-slate-600">
            Run detection first — correlation needs a spill to compare tracks against.
          </p>
        )}
        {error && (
          <p className="mt-2 rounded-md border border-red/30 bg-red/10 px-3 py-2 text-xs text-red">
            {error}
          </p>
        )}
      </section>

      {/* Hero card: Likely Offender */}
      <section
        className={`rounded-xl border p-5 text-center shadow-lg shadow-black/20 ${
          topSuspect ? "border-red/30 bg-red/5" : "border-dashed border-line bg-panel"
        }`}
      >
        <p className="text-[11px] uppercase tracking-wider text-slate-500">Likely Offender</p>

        {!topSuspect ? (
          <div className="my-4 flex flex-col items-center gap-2">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-line bg-white/[0.02]">
              <ShipIcon className="h-6 w-6 text-slate-600" />
            </div>
            <p className="text-sm font-semibold text-slate-400">Awaiting AIS module</p>
            <p className="text-[11px] text-slate-600">
              Vessel correlation requires AIS track ingestion (Module 2)
            </p>
          </div>
        ) : (
          <div className="my-4 flex flex-col items-center gap-1.5">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-red/40 bg-red/10">
              <ShipIcon className="h-6 w-6 text-red" />
            </div>
            <p className="text-base font-bold text-slate-100">{topSuspect.vessel_name}</p>
            <p className="font-mono text-[11px] text-slate-500">
              MMSI {topSuspect.mmsi} · {topSuspect.vessel_type}
            </p>
          </div>
        )}

        <div>
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-600">
            <span>Culprit Correlation Index</span>
            <span className={topSuspect ? "font-mono font-bold text-red" : ""}>
              {topSuspect ? `CCI: ${topSuspect.cci.toFixed(1)}/100` : "—"}
            </span>
          </div>
          <ConfidenceBar value={topSuspect?.cci ?? 0} tone="hero" />
        </div>

        {/* Vessel parameters, from the offender's AIS record (static hull
            fields + SOG/COG/Heading at its nearest approach to the spill). */}
        {topSuspect && (
          <div className="mt-4 text-left">
            <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">
              Vessel Parameters
            </h4>
            <div className="grid grid-cols-2 gap-x-4 divide-y divide-line/60 [&>*:nth-child(odd)]:pr-2">
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Type</span>
                <span className="font-mono text-xs text-slate-300">{topSuspect.vessel_type}</span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Draft</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.draft_m !== null ? `${topSuspect.draft_m.toFixed(1)} m` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Length</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.length_m !== null ? `${topSuspect.length_m.toFixed(0)} m` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Speed (SOG)</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.speed_sog !== null ? `${topSuspect.speed_sog.toFixed(1)} kn` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Width</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.width_m !== null ? `${topSuspect.width_m.toFixed(0)} m` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Course (COG)</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.course_cog !== null ? `${topSuspect.course_cog.toFixed(0)}°` : "—"}
                </span>
              </div>
              <div className="col-span-2 flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">Heading</span>
                <span className="font-mono text-xs text-slate-300">
                  {topSuspect.heading !== null ? `${topSuspect.heading.toFixed(0)}°` : "—"}
                </span>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* CCI breakdown -- the full, transparent weighted-factor computation
          behind the Likely Offender's headline number above. */}
      {topSuspect && (
        <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            CCI Breakdown
          </h3>
          <CciBreakdown cci={topSuspect.cci} breakdown={topSuspect.cci_breakdown} note={topSuspect.cci_note} />
        </section>
      )}

      {/* Suspect ranking */}
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Suspect Ranking
          </h3>
          {!hasResults && <PendingBadge />}
        </div>

        {!hasResults ? (
          <p className="py-3 text-center text-xs text-slate-600">
            Ranked candidate vessels will appear here once AIS track correlation is run.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {suspects.slice(0, 3).map((s, i) => {
              const isSelected = selected?.mmsi === s.mmsi;
              return (
                <button
                  key={s.mmsi}
                  onClick={() => onSelect(s.mmsi)}
                  className={`flex flex-col gap-1.5 rounded-lg border px-3 py-2 text-left transition ${
                    isSelected
                      ? "border-accent/50 bg-accent/10"
                      : "border-line bg-white/[0.02] hover:border-accent/30"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs font-medium text-slate-200">
                      <span className="font-mono text-[10px] text-slate-500">#{i + 1}</span>
                      {s.vessel_name}
                    </span>
                    <span
                      className={`font-mono text-xs font-bold ${
                        i === 0 ? "text-red" : "text-slate-300"
                      }`}
                    >
                      {s.confidence.toFixed(1)}%
                    </span>
                  </div>
                  <ConfidenceBar value={s.confidence} tone={i === 0 ? "hero" : "muted"} />
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Confidence breakdown */}
      <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Confidence Breakdown
          </h3>
          {!hasResults && <PendingBadge />}
        </div>

        {!hasResults || !selected ? (
          <p className="py-3 text-center text-xs text-slate-600">
            Distance, timing, and intersection scores will populate this panel.
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            <p className="mb-1 text-[11px] text-slate-500">
              For <span className="text-slate-300">{selected.vessel_name}</span>
            </p>
            <div className="divide-y divide-line/60">
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">
                  Distance to spill
                </span>
                <span className="font-mono text-xs text-slate-300">
                  {selected.min_distance_km.toFixed(2)} km
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">
                  Time before detection
                </span>
                <span className="font-mono text-xs text-slate-300">
                  {timeGapLabel(selected.time_gap_min)}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] uppercase tracking-wider text-slate-500">
                  Track intersects spill
                </span>
                <span
                  className={`text-xs font-bold uppercase ${
                    selected.intersects ? "text-red" : "text-slate-400"
                  }`}
                >
                  {selected.intersects ? "Yes" : "No"}
                </span>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Overall Attribution Confidence -- fuses detection, origin, and CCI
          into one honest, transparent evidence-chain verdict. */}
      <EvidenceFusionPanel fusion={fusion} loading={fusionLoading} />
    </aside>
  );
}
