"use client";

interface TopBarProps {
  timestamp: string;
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").replace("Z", " UTC");
  } catch {
    return iso;
  }
}

export default function TopBar({ timestamp }: TopBarProps) {
  return (
    <header className="flex items-center justify-between gap-6 border-b border-line bg-panel/80 px-6 py-3 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-accent/30 bg-accent/10">
          {/* SINDVA mark: a sea wave whose crest rises into a forward-
              pointing vector arrowhead ("sea + vector"). Single-accent,
              currentColor so it inherits the badge's cyan. */}
          <svg viewBox="0 0 24 24" className="h-5 w-5 text-accent" fill="none">
            <path
              d="M2 16c2-2.8 4-2.8 6 0s4 2.8 6 0"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M14 16 19 8"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M14.5 8 19 8 19 13.5"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="leading-tight">
          <div className="flex items-baseline gap-2">
            <span className="font-wordmark text-[16px] font-bold tracking-[0.14em] text-slate-100">
              SINDVA
            </span>
            <span className="hidden text-xs font-medium tracking-wide text-slate-500 sm:inline">
              MARINE WATCH
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            Satellite Oil-Spill Detection &amp; AIS Vessel Attribution
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden flex-col items-end leading-tight md:flex">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            Scene pass-time
          </span>
          <span className="font-mono text-xs text-slate-300">
            {formatTimestamp(timestamp)}
          </span>
        </div>

        <div className="flex items-center gap-1.5 rounded-full border border-green/30 bg-green/10 px-3 py-1">
          <span className="relative flex h-2 w-2">
            <span className="pulse-dot absolute inline-flex h-full w-full rounded-full bg-green" />
          </span>
          <span className="text-[11px] font-semibold tracking-wide text-green">
            SYSTEM ONLINE
          </span>
        </div>

        <div className="hidden h-8 w-px bg-line lg:block" />

        <span className="hidden font-mono text-[11px] tracking-wide text-slate-500 lg:inline">
          SIH26143 · NTRO
        </span>
      </div>
    </header>
  );
}
