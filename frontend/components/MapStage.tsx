"use client";

import { MapContainer, TileLayer, ImageOverlay, Marker, Polyline, Circle, Popup, useMap } from "react-leaflet";
import L, { type LatLngBoundsExpression, type LatLngExpression } from "leaflet";
import { Fragment, useEffect } from "react";
import type { AisTrack, DetectResponse, DriftForecastResponse, OriginEstimate, Suspect } from "@/lib/types";
import { API_BASE } from "@/lib/config";
import { getSeverity } from "@/lib/severity";

interface MapStageProps {
  center: { lat: number; lon: number };
  result: DetectResponse | null;
  aisTracks: AisTrack[] | null;
  suspects: Suspect[] | null;
  selectedMmsi: number | null;
  onSelectVessel: (mmsi: number) => void;
  origin: OriginEstimate | null;
  forecast: DriftForecastResponse | null;
}

const spillIcon = L.divIcon({
  className: "",
  html: '<div class="spill-marker"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

// SkyTruth-style "Origin Point" marker -- a plain red X, deliberately
// distinct from every other marker shape on the map (circles/ship pins),
// so it never gets mistaken for a confirmed detection.
const originIcon = L.divIcon({
  className: "",
  html: `<svg viewBox="0 0 20 20" width="20" height="20" style="filter:drop-shadow(0 0 4px rgba(239,68,68,0.9))">
    <line x1="3" y1="3" x2="17" y2="17" stroke="#ef4444" stroke-width="3" stroke-linecap="round"/>
    <line x1="17" y1="3" x2="3" y2="17" stroke="#ef4444" stroke-width="3" stroke-linecap="round"/>
  </svg>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

// Forward drift-forecast marker -- a small cyan diamond, deliberately
// distinct from the origin point's red X and the yellow spill centroid,
// so "predicted future position" never reads as a confirmed detection.
const forecastPointIcon = L.divIcon({
  className: "",
  html: `<div style="width:9px;height:9px;background:#22d3ee;border:1.5px solid #0a0e14;transform:rotate(45deg);box-shadow:0 0 4px 1px rgba(34,211,238,0.8)"></div>`,
  iconSize: [9, 9],
  iconAnchor: [4, 4],
});

function shipIcon(headingDeg: number, tone: "top" | "other" | "selected") {
  const color = tone === "top" ? "#ef4444" : tone === "selected" ? "#22d3ee" : "#64748b";
  const glow = tone === "top" ? "0 0 6px 1px rgba(239,68,68,0.85)" : "none";
  return L.divIcon({
    className: "",
    html: `<div style="width:18px;height:18px;transform:rotate(${headingDeg}deg);filter:drop-shadow(${glow})">
      <svg viewBox="0 0 24 24" width="18" height="18">
        <path d="M12 2 L19 20 L12 16 L5 20 Z" fill="${color}" stroke="#0a0e14" stroke-width="1"/>
      </svg>
    </div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

// Fits to the spill bounds, then re-fits to include every AIS track point once
// correlation has run -- so vessels well outside the spill footprint (a
// distant, low-confidence suspect) are still visible on the map, not just
// present in the data.
function FitToBounds({
  result,
  aisTracks,
  origin,
  forecast,
}: {
  result: DetectResponse | null;
  aisTracks: AisTrack[] | null;
  origin: OriginEstimate | null;
  forecast: DriftForecastResponse | null;
}) {
  const map = useMap();
  useEffect(() => {
    if (!result) return;
    const combined = L.latLngBounds(
      [result.bounds.south, result.bounds.west],
      [result.bounds.north, result.bounds.east]
    );
    if (aisTracks) {
      for (const track of aisTracks) {
        for (const p of track.points) {
          combined.extend([p.lat, p.lon]);
        }
      }
    }
    if (origin?.available) {
      combined.extend([origin.origin_lat, origin.origin_lon]);
    }
    if (forecast?.available) {
      for (const p of forecast.points) {
        combined.extend([p.lat, p.lon]);
      }
    }
    map.fitBounds(combined, { padding: [40, 40] });
  }, [result, aisTracks, origin, forecast, map]);
  return null;
}

export default function MapStage({
  center,
  result,
  aisTracks,
  suspects,
  selectedMmsi,
  onSelectVessel,
  origin,
  forecast,
}: MapStageProps) {
  const bounds: LatLngBoundsExpression | null = result
    ? [
        [result.bounds.south, result.bounds.west],
        [result.bounds.north, result.bounds.east],
      ]
    : null;

  const severity = result ? getSeverity(result.meta.area_km2) : null;
  const topSuspectMmsi = suspects && suspects.length > 0 ? suspects[0].mmsi : null;
  const suspectByMmsi = new Map((suspects ?? []).map((s) => [s.mmsi, s]));

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-line shadow-2xl shadow-black/40">
      <MapContainer
        center={[center.lat, center.lon]}
        zoom={11}
        className="h-full w-full"
        zoomControl={true}
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        />

        {result && bounds && (
          <>
            <ImageOverlay url={`${API_BASE}${result.overlay_url}`} bounds={bounds} opacity={0.85} />
            {result.meta.centroid && (
              <Marker
                position={[result.meta.centroid.lat, result.meta.centroid.lon]}
                icon={spillIcon}
              />
            )}
          </>
        )}

        {/* Origin estimation: a back-drift ESTIMATE -- a probability ZONE
            (translucent circle) around the nominal origin point, plus a
            release TIME WINDOW shown in the panel, never an exact
            location/second. */}
        {origin?.available && result?.meta.centroid && (
          <>
            <Circle
              center={[origin.origin_zone.center_lat, origin.origin_zone.center_lon]}
              radius={origin.origin_zone.radius_km * 1000}
              pathOptions={{
                color: "#ef4444",
                weight: 1.25,
                opacity: 0.5,
                fillColor: "#ef4444",
                fillOpacity: 0.1,
              }}
            />
            <Polyline
              positions={[
                [origin.origin_lat, origin.origin_lon],
                [result.meta.centroid.lat, result.meta.centroid.lon],
              ]}
              pathOptions={{ color: "#ef4444", weight: 2, opacity: 0.8, dashArray: "6 5" }}
            />
            <Marker position={[origin.origin_lat, origin.origin_lon]} icon={originIcon}>
              <Popup>
                <div className="font-sans text-xs leading-relaxed">
                  <p className="font-bold">Estimated Origin Zone</p>
                  <p>
                    {origin.origin_zone.center_lat.toFixed(4)}°, {origin.origin_zone.center_lon.toFixed(4)}° · ±{" "}
                    {origin.origin_zone.radius_km.toFixed(2)} km
                  </p>
                  <p>Drift bearing: {origin.drift_bearing_deg.toFixed(0)}°</p>
                  {origin.release_window && <p>Release window: {origin.release_window.display}</p>}
                  <p>Origin confidence: {origin.origin_confidence.toFixed(0)}%</p>
                  <p className="mt-1 italic text-slate-500">Estimate only -- see method note.</p>
                </div>
              </Popup>
            </Marker>
          </>
        )}

        {/* Drift forecast: the forward counterpart to the origin back-drift
            above -- a PREDICTION with growing uncertainty over time, never
            a certain future track. Visually distinct (dashed cyan, forward)
            from the origin line (dashed red, backward). */}
        {forecast?.available && result?.meta.centroid && (
          <>
            <Polyline
              positions={[
                [result.meta.centroid.lat, result.meta.centroid.lon],
                ...forecast.points.map((p): LatLngExpression => [p.lat, p.lon]),
              ]}
              pathOptions={{ color: "#22d3ee", weight: 2, opacity: 0.85, dashArray: "3 6" }}
            />
            {forecast.points.map((p, i) => (
              <Fragment key={`forecast-${i}`}>
                {p.uncertainty_km > 0.1 && (
                  <Circle
                    center={[p.lat, p.lon]}
                    radius={p.uncertainty_km * 1000}
                    pathOptions={{
                      color: "#22d3ee",
                      weight: 1,
                      opacity: 0.25,
                      fillColor: "#22d3ee",
                      fillOpacity: 0.05,
                    }}
                  />
                )}
                <Marker position={[p.lat, p.lon]} icon={forecastPointIcon}>
                  <Popup>
                    <div className="font-sans text-xs leading-relaxed">
                      <p className="font-bold">Predicted Position (+{p.t_offset_min.toFixed(0)} min)</p>
                      <p>Uncertainty: ± {p.uncertainty_km.toFixed(2)} km</p>
                      <p className="mt-1 italic text-slate-500">Predicted only -- see method note.</p>
                    </div>
                  </Popup>
                </Marker>
              </Fragment>
            ))}
          </>
        )}

        <FitToBounds result={result} aisTracks={aisTracks} origin={origin} forecast={forecast} />

        {aisTracks &&
          aisTracks.map((track) => {
            const isTop = track.mmsi === topSuspectMmsi;
            const isSelected = track.mmsi === selectedMmsi && !isTop;
            const tone: "top" | "other" | "selected" = isTop
              ? "top"
              : isSelected
                ? "selected"
                : "other";
            const positions: LatLngExpression[] = track.points.map((p) => [p.lat, p.lon]);
            const last = track.points[track.points.length - 1];
            const suspect = suspectByMmsi.get(track.mmsi);

            return (
              <Fragment key={track.mmsi}>
                <Polyline
                  positions={positions}
                  pathOptions={{
                    color: isTop ? "#ef4444" : isSelected ? "#22d3ee" : "#3b5166",
                    weight: isTop ? 3 : 2,
                    opacity: isTop ? 0.95 : 0.65,
                    dashArray: isTop ? undefined : "4 4",
                  }}
                  eventHandlers={{ click: () => onSelectVessel(track.mmsi) }}
                />
                <Marker
                  position={[last.lat, last.lon]}
                  icon={shipIcon(last.heading ?? last.cog ?? 0, tone)}
                  eventHandlers={{ click: () => onSelectVessel(track.mmsi) }}
                >
                  <Popup>
                    <div className="font-sans text-xs leading-relaxed">
                      <p className="font-bold">{track.name}</p>
                      <p>MMSI {track.mmsi}</p>
                      <p>{track.type}</p>
                      {suspect && (
                        <>
                          <p>Distance to spill: {suspect.min_distance_km.toFixed(2)} km</p>
                          <p>Confidence: {suspect.confidence.toFixed(1)}%</p>
                        </>
                      )}
                    </div>
                  </Popup>
                </Marker>
              </Fragment>
            );
          })}
      </MapContainer>

      {/* Legend */}
      <div className="pointer-events-none absolute bottom-4 left-4 z-[500] rounded-lg border border-line bg-panel/90 px-3 py-2 backdrop-blur-sm">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Legend
        </p>
        <div className="flex flex-col gap-1 text-[11px] text-slate-300">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm border-2 border-yellow bg-yellow/10" />
            Likely oil spill
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm border-2 border-amber bg-amber/10" />
            Uncertain
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm border-2 border-dashed border-slate-400 bg-slate-400/10" />
            Possible look-alike
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-yellow shadow-[0_0_6px_2px_rgba(255,221,0,0.8)]" />
            Primary spill centroid
          </div>
          {origin?.available && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold leading-none text-red">✕</span>
              Estimated origin zone
            </div>
          )}
          {forecast?.available && (
            <div className="flex items-center gap-2">
              <span className="h-0.5 w-3.5 border-t-2 border-dashed border-accent" />
              Predicted drift (forecast)
            </div>
          )}
          {aisTracks && aisTracks.length > 0 && (
            <>
              <div className="flex items-center gap-2">
                <span className="h-0.5 w-3.5 bg-red" />
                Top suspect track
              </div>
              <div className="flex items-center gap-2">
                <span className="h-0.5 w-3.5 bg-slate-500" />
                Other vessel tracks
              </div>
            </>
          )}
        </div>
      </div>

      {/* Severity chip */}
      {severity && (
        <div
          className={`absolute right-4 top-4 z-[500] rounded-lg border px-3 py-1.5 text-xs font-bold uppercase tracking-wide backdrop-blur-sm ${severity.bg} ${severity.ring} ${severity.color}`}
        >
          {severity.label} spill
        </div>
      )}
    </div>
  );
}
