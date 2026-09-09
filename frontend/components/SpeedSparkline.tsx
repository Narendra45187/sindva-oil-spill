"use client";

import type { SpeedProfilePoint } from "@/lib/types";

interface SpeedSparklineProps {
  points: SpeedProfilePoint[];
  slowdownTime: string | null;
}

const WIDTH = 320;
const HEIGHT = 64;
const PAD = 6;

export default function SpeedSparkline({ points, slowdownTime }: SpeedSparklineProps) {
  const known = points.filter((p): p is { time: string; sog: number } => p.sog !== null);
  if (known.length < 2) {
    return <p className="py-3 text-center text-xs text-slate-600">Not enough speed data to plot.</p>;
  }

  const speeds = known.map((p) => p.sog);
  const min = Math.min(...speeds);
  const max = Math.max(...speeds);
  const range = max - min || 1;

  const xAt = (i: number) => PAD + (i / (known.length - 1)) * (WIDTH - PAD * 2);
  const yAt = (sog: number) => HEIGHT - PAD - ((sog - min) / range) * (HEIGHT - PAD * 2);

  const path = known.map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.sog).toFixed(1)}`).join(" ");
  const slowdownIdx = slowdownTime ? known.findIndex((p) => p.time === slowdownTime) : -1;

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-16 w-full" preserveAspectRatio="none">
      <path d={path} fill="none" stroke="#22d3ee" strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
      {known.map((p, i) => (
        <circle key={i} cx={xAt(i)} cy={yAt(p.sog)} r={i === slowdownIdx ? 3.5 : 2} fill={i === slowdownIdx ? "#ef4444" : "#22d3ee"} />
      ))}
    </svg>
  );
}
