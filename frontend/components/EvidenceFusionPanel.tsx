"use client";

import type { FusionResponse } from "@/lib/types";

interface EvidenceFusionPanelProps {
  fusion: FusionResponse | null;
  loading: boolean;
}

function categoryStyle(category: "HIGH" | "MEDIUM" | "LOW") {
  if (category === "HIGH") return { bg: "bg-green/10", ring: "border-green/40", color: "text-green", dot: "bg-green" };
  if (category === "MEDIUM") return { bg: "bg-amber/10", ring: "border-amber/40", color: "text-amber", dot: "bg-amber" };
  return { bg: "bg-red/10", ring: "border-red/40", color: "text-red", dot: "bg-red" };
}

interface ChainNode {
  label: string;
  display: string;
  dim: boolean;
}

export default function EvidenceFusionPanel({ fusion, loading }: EvidenceFusionPanelProps) {
  return (
    <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Overall Attribution Confidence
      </h3>

      {loading && <p className="py-3 text-center text-xs text-accent">Fusing evidence…</p>}

      {!loading && !fusion && (
        <p className="py-3 text-center text-xs text-slate-600">
          Overall confidence will appear once detection and correlation have run.
        </p>
      )}

      {!loading && fusion && !fusion.available && (
        <p className="py-3 text-center text-xs text-slate-600">{fusion.message}</p>
      )}

      {!loading && fusion && fusion.available && (
        <>
          {(() => {
            const style = categoryStyle(fusion.category);
            const detStage = fusion.stages.find((s) => s.name === "Oil Detection");
            const originStage = fusion.stages.find((s) => s.name === "Origin Reconstruction");
            const cciStage = fusion.stages.find((s) => s.name === "Vessel Attribution (CCI)");

            const chain: ChainNode[] = [
              {
                label: "Satellite Detection",
                display: detStage?.available ? `${detStage.value?.toFixed(1)}%` : "N/A",
                dim: !detStage?.available,
              },
              { label: "Oil Confirmed", display: "", dim: !detStage?.available },
              {
                label: "Origin Zone",
                display: originStage?.available ? `${originStage.value?.toFixed(1)}%` : "N/A",
                dim: !originStage?.available,
              },
              {
                label: "Vessel Correlated",
                display: cciStage?.available ? `CCI ${cciStage.value?.toFixed(1)}` : "N/A",
                dim: !cciStage?.available,
              },
              {
                label: "Overall",
                display: `${fusion.overall_confidence.toFixed(1)}% · ${fusion.category}`,
                dim: false,
              },
            ];

            return (
              <>
                {/* Headline */}
                <div className={`flex items-center justify-between rounded-lg border px-3 py-2 ${style.bg} ${style.ring}`}>
                  <span className="text-xs font-medium text-slate-300">
                    {fusion.overall_confidence.toFixed(1)}% overall
                  </span>
                  <span className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide ${style.color}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                    {fusion.category}
                  </span>
                </div>
                <p className="mt-1.5 text-[10px] italic text-slate-600">
                  Overall evidence strength — correlation-based, not proof of guilt.
                </p>

                {/* Contributing stages */}
                <div className="mt-3 divide-y divide-line/60">
                  {fusion.stages.map((s) => (
                    <div key={s.name} className="flex items-center justify-between py-1.5">
                      <span className="text-[11px] uppercase tracking-wider text-slate-500">{s.name}</span>
                      <span className={`font-mono text-xs ${s.available ? "text-slate-300" : "text-slate-600"}`}>
                        {s.available ? `${s.value?.toFixed(1)}%` : "N/A"}
                      </span>
                    </div>
                  ))}
                </div>

                <p className="mt-2 text-[10px] text-slate-600">
                  Fused via {fusion.method}; overall strength is limited by the weakest link.
                  {fusion.reduced_certainty && (
                    <span className="text-amber"> Reduced certainty — missing: {fusion.missing_stages.join(", ")}.</span>
                  )}
                </p>

                {/* Evidence chain */}
                <div className="mt-3 overflow-x-auto">
                  <div className="flex min-w-max items-center gap-1.5 py-1">
                    {chain.map((node, i) => (
                      <div key={node.label} className="flex items-center gap-1.5">
                        <div
                          className={`flex flex-col items-center rounded-lg border px-2.5 py-1.5 text-center ${
                            node.dim
                              ? "border-line bg-white/[0.02] text-slate-600"
                              : i === chain.length - 1
                                ? `${style.ring} ${style.bg}`
                                : "border-accent/30 bg-accent/5"
                          }`}
                        >
                          <span
                            className={`text-[9px] font-semibold uppercase tracking-wide ${
                              node.dim ? "text-slate-600" : i === chain.length - 1 ? style.color : "text-accent"
                            }`}
                          >
                            {node.label}
                          </span>
                          {node.display && (
                            <span className="font-mono text-[10px] font-bold text-slate-200">{node.display}</span>
                          )}
                        </div>
                        {i < chain.length - 1 && <span className="text-xs text-slate-600">→</span>}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            );
          })()}
        </>
      )}
    </section>
  );
}
