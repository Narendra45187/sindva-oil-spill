"use client";

import { useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import type { ReportResponse } from "@/lib/types";

const ZOOM = 10;

type Source = "vesselfinder" | "marinetraffic";

function vesselFinderUrl(lat: number, lon: number): string {
  // VesselFinder retired its old /aismap embed endpoint -- it now returns
  // "Bad request" for any params, including none at all -- and its live
  // Map view (the root domain) sets X-Frame-Options: DENY, so it can't be
  // framed either. /vessels (the Vessels Database tab) is the closest
  // still-working, embeddable view (no framing restriction). lat/lon/zoom
  // are passed through for forward-compatibility, but this view is a
  // searchable list rather than a coordinate-centered map.
  return `https://www.vesselfinder.com/vessels?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&zoom=${ZOOM}`;
}

function marineTrafficUrl(lat: number, lon: number): string {
  return `https://www.marinetraffic.com/en/ais/embed/zoom:${ZOOM}/centery:${lat.toFixed(4)}/centerx:${lon.toFixed(4)}/maptype:4`;
}

const LEGEND_ITEMS: { color: string; label: string }[] = [
  { color: "#22c55e", label: "Cargo" },
  { color: "#ef4444", label: "Tanker" },
  { color: "#3b82f6", label: "Passenger" },
  { color: "#eab308", label: "Fishing" },
  { color: "#a855f7", label: "Pleasure craft / other" },
  { color: "#64748b", label: "Unspecified" },
];

export default function TrafficPage() {
  const [center, setCenter] = useState(DEFAULT_SCENE.center);
  const [regionName, setRegionName] = useState(DEFAULT_SCENE.name);
  const [usingSpillCentroid, setUsingSpillCentroid] = useState(false);
  const [source, setSource] = useState<Source>("vesselfinder");

  // Best-effort: if a spill has been detected and correlated, follow that
  // region instead of the hardcoded default. This page never triggers
  // detection/correlation itself -- it only reads the latest result, and
  // quietly keeps the default center if none is available yet.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/report/latest`);
        if (!res.ok) return;
        const data: ReportResponse = await res.json();
        if (!cancelled && data.available) {
          setCenter(data.spill.centroid);
          setRegionName(data.scene.name);
          setUsingSpillCentroid(true);
        }
      } catch {
        // Live traffic still works against the default center -- this page
        // never blocks or errors on a failed lookup.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const src = source === "vesselfinder" ? vesselFinderUrl(center.lat, center.lon) : marineTrafficUrl(center.lat, center.lon);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar timestamp={DEFAULT_SCENE.timestamp} />
      <NavBar />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 p-4">
        <div>
          <h1 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
            Live Traffic
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Live vessel-traffic map for the current scene region — an external, real-time view alongside
            the Dashboard&apos;s own detection and AIS correlation.
          </p>
        </div>

        <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/20">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Live Vessel Traffic
              </h2>
              <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                {regionName} · {center.lat.toFixed(4)}°, {center.lon.toFixed(4)}°
                {usingSpillCentroid ? (
                  <span className="ml-1.5 text-accent">(centered on latest detected spill)</span>
                ) : (
                  <span className="ml-1.5 text-slate-600">(default scene center)</span>
                )}
              </p>
            </div>

            <div className="flex gap-1">
              {(["vesselfinder", "marinetraffic"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSource(s)}
                  className={`rounded-md border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide transition ${
                    source === s
                      ? "border-accent/50 bg-accent/10 text-accent"
                      : "border-line text-slate-500 hover:border-accent/30 hover:text-slate-300"
                  }`}
                >
                  {s === "vesselfinder" ? "VesselFinder" : "MarineTraffic"}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-line" style={{ height: 600 }}>
            <iframe
              key={src}
              src={src}
              title="Live vessel traffic map"
              className="h-full w-full border-0"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
            />
          </div>

          <p className="mt-2 text-[11px] text-slate-500">
            Live AIS vessel traffic for the region · source: VesselFinder/MarineTraffic. In production,
            this same AIS feed drives the correlation engine.
          </p>
          <p className="mt-1 text-[11px] text-slate-500">
            Live vessel traffic (VesselFinder / MarineTraffic). Use the Vessels, Ports, Containers, and
            Services tabs. Note: the provider&apos;s own Map/Photos tabs open their external site.
          </p>
          <p className="mt-1 text-[11px] text-slate-600">
            This shows live, present-day vessel traffic — it does not represent vessels from the analyzed
            satellite scene&apos;s pass-time.
          </p>

          {/* Legend -- matches the embedded map's own marker-color scheme */}
          <div className="mt-4 border-t border-line/60 pt-3">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Marker colors (by vessel type)
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {LEGEND_ITEMS.map((item) => (
                <div key={item.label} className="flex items-center gap-1.5 text-[11px] text-slate-400">
                  <span
                    className="inline-block h-0 w-0 border-b-[7px] border-l-[5px] border-r-[5px] border-l-transparent border-r-transparent"
                    style={{ borderBottomColor: item.color }}
                  />
                  {item.label}
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
