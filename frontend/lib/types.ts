export interface Scene {
  name: string;
  sensor: string;
  timestamp: string;
  center: { lat: number; lon: number };
}

export interface Bounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

export type Classification = "LIKELY OIL SPILL" | "UNCERTAIN" | "POSSIBLE LOOK-ALIKE";

export interface DetectedRegion {
  oil_confidence: number; // 0-100, after the wind adjustment below
  classification: Classification;
  area_km2: number;
  length_km: number;
  width_km: number;
  elongation: number | null;
  edge_sharpness: number;
  homogeneity: number; // raw std -- lower is smoother/more homogeneous
  contrast: number;
  centroid: { lat: number; lon: number };
  wind_speed_ms: number | null; // null when the weather fetch failed -- adjustment falls back to neutral
  wind_adjustment: string; // e.g. "low-wind caution (-15%)", "high-wind support (+10%)", "neutral"
  low_wind_caution: boolean;
  perimeter_km: number; // contour perimeter
  orientation_deg: number; // slick's long-axis orientation, 0-180 deg
  estimated_volume_m3: number; // ROUGH estimate = area x assumed_thickness_m -- always show as an estimate
  assumed_thickness_m: number; // film-thickness assumption behind estimated_volume_m3
}

export interface DetectionMeta {
  detected: boolean;
  centroid: { lat: number; lon: number } | null;
  area_km2: number;
  region_count: number;
  regions: DetectedRegion[];
  timestamp: string;
}

export interface DetectResponse {
  meta: DetectionMeta;
  bounds: Bounds;
  scene: Scene;
  overlay_url: string;
  mask_url: string;
}

// --- Module 2: AIS vessel correlation ---

// AIS transmission gap ("dark vessel" period) -- an anomaly signal only,
// never proof of intent. Shared shape between Suspect (from /api/correlate)
// and the Investigation page's fuller analysis (from /api/investigation).
export interface AisGap {
  gap_start: string;
  gap_end: string;
  gap_duration_min: number;
  last_position_before: { lat: number; lon: number };
  first_position_after: { lat: number; lon: number };
  overlaps_spill_window: boolean;
}

// Culprit Correlation Index -- one entry per weighted factor (D/T/R/A/G/V).
// `contribution` is always round(subscore * weight, 2), and the CCI total
// is defined as the sum of these same contributions -- never recompute it
// independently, just sum/display what the backend already rounded.
export interface CciFactor {
  factor: "D" | "T" | "R" | "A" | "G" | "V";
  label: string;
  subscore: number; // 0-100
  weight: number; // e.g. 0.25
  contribution: number; // subscore * weight, rounded
}

export interface Suspect {
  mmsi: number;
  vessel_name: string;
  vessel_type: string;
  confidence: number; // 0-100 -- alias of `cci`, kept for backward compatibility
  cci: number; // Culprit Correlation Index, 0-100 -- ranking is by this field
  cci_breakdown: CciFactor[];
  cci_note: string; // honest "correlation, not proof" framing -- show verbatim
  min_distance_km: number;
  time_gap_min: number; // positive = minutes BEFORE detection, negative = after
  intersects: boolean;
  // AIS-derived vessel parameters (static hull fields + dynamic fields at
  // this vessel's nearest-approach point to the spill centroid).
  length_m: number | null;
  width_m: number | null;
  draft_m: number | null;
  speed_sog: number | null;
  course_cog: number | null;
  heading: number | null;
  // AIS gap ("dark vessel") analysis -- see ais_gaps note above.
  ais_gaps: AisGap[];
  dark_vessel_flag: boolean;
  total_dark_minutes: number;
}

export interface AisPoint {
  lat: number;
  lon: number;
  time: string;
  sog: number | null;
  cog: number | null;
  heading: number | null;
}

export interface AisTrack {
  mmsi: number;
  name: string;
  type: string;
  points: AisPoint[];
}

export interface CorrelateResponse {
  suspects: Suspect[];
  ais_tracks: AisTrack[];
}

// --- Evidence fusion (overall attribution confidence, display only) ---

export type ConfidenceCategory = "HIGH" | "MEDIUM" | "LOW";

export interface FusionStage {
  name: string;
  value: number | null; // 0-100, null when this stage hasn't produced a value yet
  available: boolean;
}

export interface FusionAvailable {
  available: true;
  overall_confidence: number; // 0-100 -- always the geometric mean of the available stages[].value
  category: ConfidenceCategory;
  method: string;
  stages: FusionStage[];
  reduced_certainty: boolean;
  missing_stages: string[];
  note: string; // honest "not proof of guilt" framing -- show verbatim
}

export interface FusionUnavailable {
  available: false;
  message: string;
}

export type FusionResponse = FusionAvailable | FusionUnavailable;

// --- AIS Investigation (behavioral case file, display only) ---

export interface SpeedProfilePoint {
  time: string;
  sog: number | null;
}

export interface SpeedStats {
  min_speed_kn: number | null;
  max_speed_kn: number | null;
  avg_speed_kn: number | null;
}

export interface SlowdownAt {
  time: string;
  lat: number;
  lon: number;
  sog: number | null;
}

export interface CourseChange {
  time: string;
  lat: number;
  lon: number;
  from_deg: number;
  to_deg: number;
  change_deg: number;
}

export interface LoiteringAt {
  time: string;
  lat: number;
  lon: number;
}

export interface NearestApproach {
  time: string;
  lat: number;
  lon: number;
  sog: number | null;
  distance_km: number;
  time_gap_min: number;
  before_detection: boolean;
}

export interface VoyageContext {
  entry_time: string | null;
  exit_time: string | null;
  entry_position: { lat: number; lon: number } | null;
  exit_position: { lat: number; lon: number } | null;
  time_in_area_min: number | null;
}

export interface InvestigationAvailable {
  available: true;
  vessel: { mmsi: number; name: string; vessel_type: string };
  attribution: {
    confidence: number;
    min_distance_km: number;
    time_gap_min: number;
    intersects: boolean;
    length_m: number | null;
    width_m: number | null;
    draft_m: number | null;
  };
  // Culprit Correlation Index -- the same breakdown that determined this
  // vessel's rank in ais/correlate.py, passed through unchanged.
  cci: number;
  cci_breakdown: CciFactor[];
  cci_note: string;
  speed_profile: SpeedProfilePoint[];
  speed_stats: SpeedStats;
  slowdown_detected: boolean;
  slowdown_at: SlowdownAt | null;
  course_change_detected: boolean;
  course_changes: CourseChange[];
  loitering_detected: boolean;
  loitering_points: number;
  loitering_at: LoiteringAt | null;
  nearest_approach: NearestApproach | null;
  voyage_context: VoyageContext;
  // AIS gap ("dark vessel") analysis -- an anomaly signal only, never
  // proof of intent. dark_vessel_note is the honest framing to display
  // verbatim wherever this is shown.
  ais_gaps: AisGap[];
  dark_vessel_flag: boolean;
  total_dark_minutes: number;
  dark_vessel_note: string;
  track_points: AisPoint[];
  investigation_summary: string;
  spill: {
    centroid: { lat: number; lon: number } | null;
    area_km2: number | null;
    classification: Classification | null;
  };
}

export interface InvestigationUnavailable {
  available: false;
  message: string;
}

export type InvestigationResponse = InvestigationAvailable | InvestigationUnavailable;

// --- Origin estimation (back-drift, display only) ---
// A probability ZONE + release TIME WINDOW, not a single point/second --
// see backend/origin/estimate_origin.py.

export interface OriginZone {
  center_lat: number;
  center_lon: number;
  radius_km: number;
}

export interface ReleaseWindow {
  start_time: string; // ISO 8601
  end_time: string; // ISO 8601
  display: string; // human-readable range, e.g. "2026-09-04 23:36 – 00:06 UTC"
}

export interface OriginCandidate {
  label: "min" | "nominal" | "max";
  drift_minutes: number;
  lat: number;
  lon: number;
  distance_km: number;
}

export interface OriginAvailable {
  available: true;
  // Backward-compatible fields -- always the nominal candidate.
  origin_lat: number;
  origin_lon: number;
  drift_distance_km: number;
  drift_bearing_deg: number; // direction the slick is drifting TOWARDS (downstream)
  drift_minutes: number;
  net_drift_speed_ms: number;
  method_note: string;
  // Zone + window + confidence.
  nominal_origin: { lat: number; lon: number };
  origin_zone: OriginZone;
  release_window: ReleaseWindow | null;
  origin_confidence: number; // 0-100 -- the same value evidence fusion's Origin Reconstruction stage reads
  min_drift_minutes: number;
  max_drift_minutes: number;
  candidates: OriginCandidate[];
}

export interface OriginUnavailable {
  available: false;
  message: string;
}

export type OriginEstimate = OriginAvailable | OriginUnavailable;

// --- Drift forecast (forward projection, display only) ---
// The forward counterpart to origin estimation above -- same drift model,
// run forward instead of backward. Named "DriftForecast*" (not
// "Forecast*") to avoid colliding with the unrelated weather-forecast
// types further below.

export interface DriftForecastPoint {
  t_offset_min: number;
  lat: number;
  lon: number;
  uncertainty_km: number; // grows with lead time -- never presented as exact
}

export interface DriftForecastAvailable {
  available: true;
  horizon_hours: number;
  step_minutes: number;
  drift_bearing_deg: number; // direction of travel (downstream) -- opposite the origin hindcast's placement bearing
  net_drift_speed_ms: number;
  total_displacement_km: number;
  points: DriftForecastPoint[];
  method_note: string;
}

export interface DriftForecastUnavailable {
  available: false;
  message: string;
}

export type DriftForecastResponse = DriftForecastAvailable | DriftForecastUnavailable;

// --- Weather & ocean conditions (Open-Meteo, display only) ---
// Three-tier fallback (see backend/weather/weather.py): `source` says
// honestly which tier actually supplied these values -- never present
// "cached"/"default" as "live". Fields are never blank/null when a value
// exists at any tier (which is always true for "default"), but the type
// keeps `| null` since a field can still be null in genuinely
// exceptional cases (e.g. a corrupt/partial cache with no default to
// fall back on for that one field -- doesn't happen in practice today).

export type WeatherSource = "live" | "cached" | "default";

export interface WeatherConditions {
  wind_speed_ms: number | null;
  wind_direction: number | null; // degrees, meteorological (FROM direction)
  wave_height_m: number | null;
  current_velocity_ms: number | null;
  current_direction: number | null; // degrees
  temperature_c: number | null;
  surface_pressure_hpa: number | null;
  source: WeatherSource;
  fetched_at: string; // for "cached", the ORIGINAL live read's time, not now
  notes: string[]; // e.g. "marine data unavailable (...)" -- empty when everything succeeded live
}

export interface ForecastHour {
  time: string; // ISO 8601, no timezone offset (Open-Meteo default: UTC)
  wind_speed_ms: number | null;
  wave_height_m: number | null;
}

export interface ForecastResponse {
  hours: ForecastHour[];
  notes: string[];
}

// --- Consolidated incident report (/api/report/latest) ---

export type Severity = "None" | "Minor" | "Moderate" | "Severe";

export interface ReportSpill {
  classification: Classification;
  oil_confidence: number;
  area_km2: number;
  length_km: number;
  width_km: number;
  centroid: { lat: number; lon: number };
  severity: Severity;
  regions: DetectedRegion[];
  wind_context: string;
}

export interface ReportWeather {
  wind_speed_ms: number | null;
  wind_direction: number | null;
  wave_height_m: number | null;
  current_velocity_ms: number | null;
  temperature_c: number | null;
  pressure_hpa: number | null;
}

export interface ReportSuspect {
  name: string;
  mmsi: number;
  type: string;
  confidence: number;
  distance_km: number;
  time_before_min: number; // positive = before detection, negative = after
  intersects: boolean;
}

export interface ReportAttribution {
  likely_offender: ReportSuspect;
  ranking: ReportSuspect[];
}

export interface ReportAvailable {
  available: true;
  generated_at: string;
  scene: Scene;
  spill: ReportSpill;
  weather: ReportWeather | null;
  attribution: ReportAttribution;
  overlay_url: string;
}

export interface ReportUnavailable {
  available: false;
  message: string;
}

export type ReportResponse = ReportAvailable | ReportUnavailable;

// --- Incident history (Alerts page) ---

export type IncidentStatus = "New" | "Reviewed" | "Under Investigation";

export interface IncidentSummary {
  incident_id: string;
  logged_at: string;
  region: string;
  centroid: { lat: number; lon: number };
  severity: Severity;
  classification: Classification;
  oil_confidence: number;
  likely_offender_name: string;
  attribution_confidence: number;
  status: IncidentStatus;
}

// The full record has the same shape as ReportAvailable minus
// available/generated_at, plus incident_id/logged_at/status.
export interface IncidentFull {
  incident_id: string;
  logged_at: string;
  status: IncidentStatus;
  scene: Scene;
  spill: ReportSpill;
  weather: ReportWeather | null;
  attribution: ReportAttribution;
  overlay_url: string;
}
