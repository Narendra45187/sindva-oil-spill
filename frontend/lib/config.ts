// Set NEXT_PUBLIC_API_URL in the deploy environment (e.g. Netlify) to
// point at the live backend; falls back to localhost for local dev when
// the var isn't set.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const DEFAULT_SCENE = {
  name: "Visakhapatnam Port, Bay of Bengal",
  sensor: "Sentinel-1 IW GRD (VV)",
  timestamp: "2026-09-05T00:21:39Z",
  center: { lat: 17.68, lon: 83.33 },
};
