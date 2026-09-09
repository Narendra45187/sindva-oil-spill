"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import TopBar from "@/components/TopBar";
import NavBar from "@/components/NavBar";
import { API_BASE, DEFAULT_SCENE } from "@/lib/config";
import { getClassificationStyle } from "@/lib/classification";
import type { IncidentStatus, IncidentSummary } from "@/lib/types";

const STATUS_OPTIONS: IncidentStatus[] = ["New", "Reviewed", "Under Investigation"];

function severityStyle(severity: string): { color: string; dot: string } {
  if (severity === "Severe") return { color: "text-red", dot: "bg-red" };
  if (severity === "Moderate") return { color: "text-amber", dot: "bg-amber" };
  if (severity === "Minor") return { color: "text-green", dot: "bg-green" };
  return { color: "text-slate-500", dot: "bg-slate-500" };
}

function statusStyle(status: IncidentStatus): string {
  if (status === "New") return "border-accent/40 bg-accent/10 text-accent";
  if (status === "Under Investigation") return "border-amber/40 bg-amber/10 text-amber";
  return "border-line bg-white/[0.03] text-slate-400";
}

export default function AlertsPage() {
  const router = useRouter();
  const [incidents, setIncidents] = useState<IncidentSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/incidents`);
        if (!res.ok) throw new Error(`Incidents service returned ${res.status}`);
        const data: IncidentSummary[] = await res.json();
        if (!cancelled) setIncidents(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? `Could not load incidents — ${err.message}` : "Could not load incidents.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const changeStatus = async (incidentId: string, status: IncidentStatus) => {
    setUpdatingId(incidentId);
    const previous = incidents;
    // Optimistic update -- reverted below if the request fails.
    setIncidents((prev) => prev?.map((inc) => (inc.incident_id === incidentId ? { ...inc, status } : inc)) ?? prev);
    try {
      const res = await fetch(`${API_BASE}/api/incidents/${incidentId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`Status update returned ${res.status}`);
    } catch {
      setIncidents(previous ?? null);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar timestamp={DEFAULT_SCENE.timestamp} />
      <NavBar />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 p-4">
        <div>
          <h1 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">Alerts</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Incident register — every completed detection + AIS correlation run on the Dashboard.
          </p>
        </div>

        {loading && <p className="py-16 text-center text-sm text-accent">Loading incidents…</p>}

        {error && !loading && (
          <p className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
        )}

        {incidents && !loading && incidents.length === 0 && (
          <p className="py-16 text-center text-sm text-slate-500">
            No incidents logged yet. Run detection + AIS correlation on the Dashboard to log an incident.
          </p>
        )}

        {incidents && incidents.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-line bg-panel/40">
            <table className="w-full min-w-[900px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3 font-medium">Incident ID</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Classification</th>
                  <th className="px-4 py-3 font-medium">Likely Offender</th>
                  <th className="px-4 py-3 text-right font-medium">Attribution</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => {
                  const sev = severityStyle(inc.severity);
                  const cls = getClassificationStyle(inc.classification);
                  return (
                    <tr
                      key={inc.incident_id}
                      onClick={() => router.push(`/reports?id=${inc.incident_id}`)}
                      className="cursor-pointer border-b border-line/60 transition hover:bg-white/[0.02]"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-slate-300">{inc.incident_id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">
                        {new Date(inc.logged_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <p className="text-xs text-slate-300">{inc.region}</p>
                        <p className="font-mono text-[11px] text-slate-500">
                          {inc.centroid.lat.toFixed(4)}°, {inc.centroid.lon.toFixed(4)}°
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`flex items-center gap-1.5 text-xs font-semibold ${sev.color}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${sev.dot}`} />
                          {inc.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${cls.bg} ${cls.ring} ${cls.color}`}
                        >
                          {inc.classification}
                        </span>
                        <p className="mt-1 font-mono text-[11px] text-slate-500">
                          {inc.oil_confidence.toFixed(1)}%
                        </p>
                      </td>
                      <td className="px-4 py-3 text-xs font-medium text-slate-200">
                        {inc.likely_offender_name}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs font-semibold text-slate-200">
                        {inc.attribution_confidence.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <select
                          value={inc.status}
                          disabled={updatingId === inc.incident_id}
                          onChange={(e) => changeStatus(inc.incident_id, e.target.value as IncidentStatus)}
                          className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide outline-none transition disabled:opacity-50 ${statusStyle(inc.status)}`}
                        >
                          {STATUS_OPTIONS.map((s) => (
                            <option key={s} value={s} className="bg-panel text-slate-200">
                              {s}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
