"use client";

import type { DetectResponse } from "@/lib/types";
import { API_BASE } from "@/lib/config";
import { getSeverity } from "@/lib/severity";

interface ImageResultPanelProps {
  result: DetectResponse;
}

// Shown instead of MapStage when meta.display_mode === "image" -- an
// uploaded SAR/SOS image with no real georeferencing (a plain PNG/JPG, or
// a TIFF with no geo metadata). Its predicted oil region has no genuine
// map coordinates to project onto, so this renders the uploaded image
// itself (with the mask already drawn on it server-side, see
// ml_detect.detect_ml()'s display_image_filename) instead of stretching
// that prediction across an unrelated patch of the real Visakhapatnam bay.
export default function ImageResultPanel({ result }: ImageResultPanelProps) {
  const severity = getSeverity(result.meta.area_km2);
  const primary = result.meta.regions[0] ?? null;
  const imageUrl = result.display_image_url ?? result.overlay_url;

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden rounded-xl border border-line bg-panel/40 shadow-2xl shadow-black/40">
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-950/60 p-4">
        <img
          src={`${API_BASE}${imageUrl}`}
          alt="Uploaded SAR image with AI-predicted oil region overlaid"
          className="max-h-full max-w-full rounded-lg object-contain shadow-lg"
        />
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            AI / U-Net Detection
          </p>
          <p className="text-[11px] text-slate-500">
            Uploaded image -- no georeferencing available, shown here rather than on the map.
          </p>
        </div>
        {result.meta.detected && primary && (
          <div
            className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold uppercase tracking-wide ${severity.bg} ${severity.ring} ${severity.color}`}
          >
            {severity.label} -- {result.meta.area_km2.toFixed(2)} km2
          </div>
        )}
      </div>
    </div>
  );
}
