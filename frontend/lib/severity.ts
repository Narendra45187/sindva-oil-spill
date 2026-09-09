export type SeverityLevel = "None" | "Minor" | "Moderate" | "Severe";

export interface Severity {
  label: SeverityLevel;
  color: string; // Tailwind text color class
  bg: string; // Tailwind bg color class (subtle)
  ring: string; // Tailwind ring/border color class
}

export function getSeverity(areaKm2: number): Severity {
  if (areaKm2 <= 0) {
    return { label: "None", color: "text-slate-400", bg: "bg-slate-500/10", ring: "border-slate-500/30" };
  }
  if (areaKm2 < 1) {
    return { label: "Minor", color: "text-green", bg: "bg-green/10", ring: "border-green/30" };
  }
  if (areaKm2 < 5) {
    return { label: "Moderate", color: "text-amber", bg: "bg-amber/10", ring: "border-amber/30" };
  }
  return { label: "Severe", color: "text-red", bg: "bg-red/10", ring: "border-red/30" };
}
