"use client";

import type { DetectResponse } from "@/lib/types";
import { API_BASE } from "@/lib/config";
import { getSeverity } from "@/lib/severity";

interface MLResultPanelProps {
  result: DetectResponse;
}

// Shown instead of MapStage whenever meta.detection_method === "AI / U-Net"
// (see app/page.tsx) -- an uploaded SAR/SOS image has no real geographic
// relation to the fixed Visakhapatnam scene, so its predicted oil mask is
// never projected onto the Leaflet map (that made outlines land on
// unrelated parts of the real bay/coastline). Instead this renders the
// two PNGs ml_detect.detect_ml() always produces for the AI path side by
// side: the uploaded input image, and that same image with the mask drawn
// on it. Classic CV keeps using MapStage exactly as before.
export default function MLResultPanel({ result }: MLResultPanelProps) {
  const { meta } = result;
  const severity = getSeverity(meta.area_km2);
  const primary = meta.regions[0] ?? null;

  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-line bg-panel/40 shadow-2xl shadow-black/40">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-accent">
            AI / U-Net Segmentation Result
          </p>
          <p className="text-[11px] text-slate-500">
            Uploaded image -- shown here, not on the map (no geographic relation to Visakhapatnam).
          </p>
        </div>
        {meta.detected && primary && (
          <div
            className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold uppercase tracking-wide ${severity.bg} ${severity.ring} ${severity.color}`}
          >
            {severity.label} -- {meta.area_km2.toFixed(2)} km2
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-auto p-3 sm:grid-cols-2">
        <figure className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-slate-950/60">
          <figcaption className="border-b border-line px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Input SAR Image
          </figcaption>
          <div className="flex flex-1 items-center justify-center overflow-auto p-2">
            {result.input_image_url && (
              <img
                src={`${API_BASE}${result.input_image_url}`}
                alt="Uploaded SAR input image"
                className="max-h-full max-w-full rounded object-contain"
              />
            )}
          </div>
        </figure>

        <figure className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-slate-950/60">
          <figcaption className="border-b border-line px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            AI-Detected Oil Mask
          </figcaption>
          <div className="flex flex-1 items-center justify-center overflow-auto p-2">
            {result.display_image_url && (
              <img
                src={`${API_BASE}${result.display_image_url}`}
                alt="AI-predicted oil mask overlaid on the input image"
                className="max-h-full max-w-full rounded object-contain"
              />
            )}
          </div>
        </figure>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-xs text-slate-300">
        <span>
          <span className="text-slate-500">Method:</span>{" "}
          <span className="font-mono font-semibold">{meta.detection_method}</span>
        </span>
        <span>
          <span className="text-slate-500">Regions found:</span>{" "}
          <span className="font-mono font-semibold">{meta.region_count}</span>
        </span>
        <span>
          <span className="text-slate-500">Area:</span>{" "}
          <span className="font-mono font-semibold">{meta.area_km2.toFixed(3)} km2</span>
        </span>
        {primary && (
          <span>
            <span className="text-slate-500">Classification:</span>{" "}
            <span className="font-mono font-semibold">{primary.classification}</span>
          </span>
        )}
      </div>
    </div>
  );
}
