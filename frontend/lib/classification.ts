import type { Classification } from "@/lib/types";

export interface ClassificationStyle {
  label: Classification;
  color: string; // Tailwind text color class
  bg: string; // Tailwind bg color class (subtle)
  ring: string; // Tailwind ring/border color class
  dot: string; // Tailwind bg color class, for a small swatch/legend dot
}

export function getClassificationStyle(classification: Classification): ClassificationStyle {
  switch (classification) {
    case "LIKELY OIL SPILL":
      return {
        label: classification,
        color: "text-yellow",
        bg: "bg-yellow/10",
        ring: "border-yellow/30",
        dot: "bg-yellow",
      };
    case "UNCERTAIN":
      return {
        label: classification,
        color: "text-amber",
        bg: "bg-amber/10",
        ring: "border-amber/30",
        dot: "bg-amber",
      };
    case "POSSIBLE LOOK-ALIKE":
      return {
        label: classification,
        color: "text-slate-400",
        bg: "bg-slate-500/10",
        ring: "border-slate-500/30",
        dot: "bg-slate-400",
      };
  }
}
