"use client";

import type { CciFactor } from "@/lib/types";

interface CciBreakdownProps {
  cci: number;
  breakdown: CciFactor[];
  note: string;
}

// The displayed total is always the sum of the displayed contributions --
// never an independently-rounded number -- so this can never mismatch
// what's shown row by row below it.
export default function CciBreakdown({ cci, breakdown, note }: CciBreakdownProps) {
  const summed = Math.round(breakdown.reduce((acc, f) => acc + f.contribution, 0) * 10) / 10;

  return (
    <div>
      <div className="grid grid-cols-[20px_1fr_44px_44px_56px] gap-1.5 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
        <span />
        <span>Factor</span>
        <span className="text-right">Score</span>
        <span className="text-right">Weight</span>
        <span className="text-right">Contrib.</span>
      </div>
      <div className="divide-y divide-line/60">
        {breakdown.map((f) => (
          <div key={f.factor} className="grid grid-cols-[20px_1fr_44px_44px_56px] items-center gap-1.5 py-1.5">
            <span className="font-mono text-[11px] font-bold text-accent">{f.factor}</span>
            <span className="text-[11px] text-slate-400">{f.label}</span>
            <span className="text-right font-mono text-[11px] text-slate-300">{f.subscore.toFixed(1)}</span>
            <span className="text-right font-mono text-[11px] text-slate-600">×{(f.weight * 100).toFixed(0)}%</span>
            <span className="text-right font-mono text-[11px] font-semibold text-slate-200">
              {f.contribution.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between border-t border-line/60 pt-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          CCI (sum of contributions)
        </span>
        <span className="font-mono text-xs font-bold text-accent">
          {summed.toFixed(1)} / 100 {summed === cci ? "" : `(≠ ${cci.toFixed(1)}!)`}
        </span>
      </div>
      <p className="mt-2 text-[10px] italic text-slate-600">{note}</p>
    </div>
  );
}
