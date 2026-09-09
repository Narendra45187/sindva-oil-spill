"use client";

import { MapContainer, TileLayer, Polyline, Circle, Marker, CircleMarker, Popup, useMap } from "react-leaflet";
import L, { type LatLngExpression } from "leaflet";
import { Fragment, useEffect } from "react";
import type { AisGap, AisPoint, NearestApproach } from "@/lib/types";

interface InvestigationMapProps {
  vesselName: string;
  track: AisPoint[];
  spillCentroid: { lat: number; lon: number } | null;
  spillAreaKm2: number | null;
  nearestApproach: NearestApproach | null;
  aisGaps: AisGap[];
}

// Distinct from the Dashboard's spill marker -- this page is a single
// vessel's own focused case file, so its own small icon set keeps it
// visually independent of components/MapStage.tsx.
const spillCenterIcon = L.divIcon({
  className: "",
  html: '<div style="width:10px;height:10px;border-radius:50%;background:#ffdd00;box-shadow:0 0 6px 2px rgba(255,221,0,0.8)"></div>',
  iconSize: [10, 10],
  iconAnchor: [5, 5],
});

const nearestApproachIcon = L.divIcon({
  className: "",
  html: `<svg viewBox="0 0 24 24" width="22" height="22" style="filter:drop-shadow(0 0 4px rgba(239,68,68,0.9))">
    <circle cx="12" cy="12" r="8" fill="none" stroke="#ef4444" stroke-width="2.5"/>
    <circle cx="12" cy="12" r="2" fill="#ef4444"/>
  </svg>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function gapLabelIcon(durationMin: number) {
  return L.divIcon({
    className: "",
    html: `<div style="display:flex;align-items:center;gap:4px;white-space:nowrap;transform:translateY(-2px)">
      <svg viewBox="0 0 20 20" width="16" height="16" style="filter:drop-shadow(0 0 3px rgba(148,163,184,0.9))">
        <circle cx="10" cy="10" r="7" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="3 2.5"/>
      </svg>
      <span style="font:600 10px monospace;color:#e2e8f0;background:rgba(10,14,20,0.85);padding:1px 5px;border-radius:4px;border:1px solid #94a3b8">AIS gap: ${durationMin.toFixed(0)} min</span>
    </div>`,
    iconSize: [140, 20],
    iconAnchor: [8, 10],
  });
}

// Splits a time-ordered track into contiguous segments, breaking right
// after any point that begins a detected AIS gap (matched by its ISO
// timestamp -- both come from the same backend response, so the strings
// are byte-identical). Segments render solid (real transmissions); the gap
// itself is bridged separately as a dashed, greyed-out interpolation --
// never presented as real data.
function splitAtGaps(track: AisPoint[], gaps: AisGap[]): AisPoint[][] {
  const gapStartTimes = new Set(gaps.map((g) => g.gap_start));
  const segments: AisPoint[][] = [];
  let current: AisPoint[] = [];
  for (const point of track) {
    current.push(point);
    if (gapStartTimes.has(point.time)) {
      segments.push(current);
      current = [];
    }
  }
  if (current.length > 0) segments.push(current);
  return segments;
}

function FitToTrack({
  track,
  spillCentroid,
}: {
  track: AisPoint[];
  spillCentroid: { lat: number; lon: number } | null;
}) {
  const map = useMap();
  useEffect(() => {
    if (track.length === 0 && !spillCentroid) return;
    const bounds = L.latLngBounds(track.map((p): LatLngExpression => [p.lat, p.lon]));
    if (spillCentroid) bounds.extend([spillCentroid.lat, spillCentroid.lon]);
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [track, spillCentroid, map]);
  return null;
}

export default function InvestigationMap({
  vesselName,
  track,
  spillCentroid,
  spillAreaKm2,
  nearestApproach,
  aisGaps,
}: InvestigationMapProps) {
  const positions: LatLngExpression[] = track.map((p) => [p.lat, p.lon]);
  const center: LatLngExpression = spillCentroid
    ? [spillCentroid.lat, spillCentroid.lon]
    : positions[0] ?? [0, 0];
  const segments = splitAtGaps(track, aisGaps);

  // Circle radius from the spill's own area (approximated as a disc) -- a
  // rough "spill footprint" for this focused view, not the traced SAR
  // outline the Dashboard shows.
  const spillRadiusM = spillAreaKm2 ? Math.sqrt(spillAreaKm2 / Math.PI) * 1000 : null;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-line shadow-2xl shadow-black/40">
      <MapContainer center={center} zoom={12} className="h-full w-full" zoomControl={true}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        />

        {spillCentroid && spillRadiusM && (
          <Circle
            center={[spillCentroid.lat, spillCentroid.lon]}
            radius={spillRadiusM}
            pathOptions={{ color: "#ffdd00", weight: 1.5, opacity: 0.7, fillColor: "#ffdd00", fillOpacity: 0.08, dashArray: "5 4" }}
          />
        )}
        {spillCentroid && <Marker position={[spillCentroid.lat, spillCentroid.lon]} icon={spillCenterIcon} />}

        {/* Solid where the vessel actually transmitted */}
        {segments.map(
          (segment, i) =>
            segment.length > 1 && (
              <Polyline
                key={`segment-${i}`}
                positions={segment.map((p): LatLngExpression => [p.lat, p.lon])}
                pathOptions={{ color: "#ef4444", weight: 3, opacity: 0.9 }}
              />
            )
        )}

        {/* Dashed, greyed-out interpolation across each AIS gap -- an
            estimate of the path with no real data, never presented as an
            actual transmission -- plus a small "AIS gap" label. */}
        {aisGaps.map((gap, i) => (
          <Fragment key={`gap-${i}`}>
            <Polyline
              positions={[
                [gap.last_position_before.lat, gap.last_position_before.lon],
                [gap.first_position_after.lat, gap.first_position_after.lon],
              ]}
              pathOptions={{ color: "#94a3b8", weight: 2.5, opacity: 0.75, dashArray: "2 6" }}
            />
            <Marker
              position={[
                (gap.last_position_before.lat + gap.first_position_after.lat) / 2,
                (gap.last_position_before.lon + gap.first_position_after.lon) / 2,
              ]}
              icon={gapLabelIcon(gap.gap_duration_min)}
            >
              <Popup>
                <div className="font-sans text-xs leading-relaxed">
                  <p className="font-bold">AIS Transmission Gap</p>
                  <p>{gap.gap_duration_min.toFixed(0)} min dark</p>
                  <p>{new Date(gap.gap_start).toLocaleString()} → {new Date(gap.gap_end).toLocaleString()}</p>
                  {gap.overlaps_spill_window && <p>Overlaps the estimated spill window.</p>}
                  <p className="mt-1 italic text-slate-500">
                    Possible transponder inactivity — not proof of intent.
                  </p>
                </div>
              </Popup>
            </Marker>
          </Fragment>
        ))}

        {track.map((p, i) => (
          <CircleMarker
            key={i}
            center={[p.lat, p.lon]}
            radius={3}
            pathOptions={{ color: "#ef4444", fillColor: "#0a0e14", fillOpacity: 1, weight: 1.5 }}
          >
            <Popup>
              <div className="font-sans text-xs leading-relaxed">
                <p className="font-bold">{vesselName}</p>
                <p>{new Date(p.time).toLocaleString()}</p>
                <p>SOG: {p.sog !== null ? `${p.sog.toFixed(1)} kn` : "—"}</p>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {nearestApproach && (
          <Marker position={[nearestApproach.lat, nearestApproach.lon]} icon={nearestApproachIcon}>
            <Popup>
              <div className="font-sans text-xs leading-relaxed">
                <p className="font-bold">Nearest Approach</p>
                <p>{nearestApproach.distance_km.toFixed(2)} km from spill</p>
                <p>{new Date(nearestApproach.time).toLocaleString()}</p>
              </div>
            </Popup>
          </Marker>
        )}

        <FitToTrack track={track} spillCentroid={spillCentroid} />
      </MapContainer>

      {/* Legend */}
      <div className="pointer-events-none absolute bottom-4 left-4 z-[500] rounded-lg border border-line bg-panel/90 px-3 py-2 backdrop-blur-sm">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Legend</p>
        <div className="flex flex-col gap-1 text-[11px] text-slate-300">
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-3.5 bg-red" />
            Suspect track
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-yellow shadow-[0_0_6px_2px_rgba(255,221,0,0.8)]" />
            Spill centroid (approx. footprint)
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold leading-none text-red">◎</span>
            Nearest approach
          </div>
          {aisGaps.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="h-0.5 w-3.5 border-t-2 border-dashed border-slate-400" />
              AIS gap (interpolated, no data)
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
