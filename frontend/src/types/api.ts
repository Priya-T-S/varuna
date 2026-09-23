/**
 * Types mirrored from FastAPI OpenAPI (`GET /openapi.json`) and
 * `backend/app/schemas/{prediction,alert}.py`. Field names are not renamed.
 *
 * Documented HTTP contracts:
 * - GET  /api/v1/health
 * - POST /api/v1/predictions          → 200 PredictionResponse | 422 | 501
 * - GET  /api/v1/predictions/model-info
 * - GET  /api/v1/alerts               → AlertResponse[] (no query params)
 * - GET  /api/v1/alerts/stream        → text/event-stream of AlertStreamEvent
 * - POST /api/v1/alerts/evaluate | /alerts/test, CRUD /recipients, /alert-rules
 * - POST /api/v1/scenarios/simulate   → ScenarioResult
 * - POST /api/v1/chat                 → ChatResponse | 503 (assistant not configured)
 *
 * 501 is raised as FastAPI HTTPException when PredictionService has no
 * loaded model (see backend tests). OpenAPI does not list 501 because the
 * route does not declare it; the runtime body is `{ "detail": string }`.
 *
 * Auth: none.
 * Pagination / list filters: none on any endpoint.
 *
 * Missing backend routes (do not call):
 * // TODO: backend endpoint missing — GET /api/v1/predictions/{id}
 * // TODO: backend endpoint missing — prediction history / sessions
 * // TODO: backend endpoint missing — similar historical cases
 *
 * Implemented satellite Grad-CAM route:
 * POST /api/v1/predictions/explain-image → 200 GradCamResponse | 422
 */

export type RiskLevel = "low" | "moderate" | "heavy" | "extreme";

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

/** Surface meteorology. Units from WeatherFeatures Field descriptions. All optional. */
export interface WeatherFeatures {
  /** Surface air temperature, °C */
  temperature_c?: number | null;
  /** Relative humidity, % (0–100) */
  humidity_pct?: number | null;
  /** Mean sea-level pressure, hPa */
  pressure_hpa?: number | null;
  /** Wind speed, m/s (≥ 0) */
  wind_speed_ms?: number | null;
  /** Total cloud cover, % (0–100) */
  cloud_cover_pct?: number | null;
}

export interface PredictionRequest {
  location: GeoPoint;
  /** Human-readable place name, e.g. 'Kerala' */
  region_name?: string | null;
  /** Forecast lead time in hours (1–72), default 12 */
  horizon_hours?: number;
  weather?: WeatherFeatures | null;
  /** Attach SHAP/Grad-CAM explanation payload, default true */
  include_explanation?: boolean;
}

export interface FeatureAttribution {
  feature: string;
  /** The input value the model saw */
  value?: number | null;
  /** Signed SHAP value (log-odds or probability units) */
  contribution: number;
}

export interface ImageExplanation {
  satellite_image_id: string;
  /** URL of the Grad-CAM overlay rendered by the backend */
  heatmap_url: string;
  /** Plain-language summary of highlighted regions */
  description: string;
}

export interface HistoricalMatch {
  event: string;
  region: string;
  date: string;
  observed_category: number;
  observed_rainfall_mm: number;
  similarity: number;
  similarity_pct: number;
}

export interface HistoricalExplanation {
  reference_events: number;
  closest_match?: HistoricalMatch | null;
  matches?: HistoricalMatch[];
  notes?: string[];
}

export interface ConfidenceFactors {
  model_agreement?: number | null;
  historical_similarity?: number | null;
  data_quality: string;
  data_quality_score: number;
}

export interface ConfidenceExplanation {
  confidence_pct: number;
  confidence: string;
  factors: ConfidenceFactors;
  components?: Record<string, any>;
}

export interface Explanation {
  feature_attributions?: FeatureAttribution[];
  image_explanation?: ImageExplanation | null;
  /** Human-readable sentence explaining the main drivers of the prediction */
  narrative?: string;
  historical_explanation?: HistoricalExplanation | null;
  confidence_explanation?: ConfidenceExplanation | null;
  caveats?: string[];
  provenance?: ProvenanceItem[];
}

export interface PredictionResponse {
  location: GeoPoint;
  region_name: string | null;
  generated_at: string;
  horizon_hours: number;
  /** Probability of a high-impact rain event (0–1) */
  probability: number;
  risk_level: RiskLevel;
  /** Model confidence score (0–1) */
  confidence: number;
  model_version: string;
  explanation?: Explanation | null;
}

export interface AlertResponse {
  id: number;
  region_name: string;
  location: GeoPoint;
  risk_level: RiskLevel;
  probability: number;
  valid_from: string;
  valid_until: string;
  /** Human-readable warning text, including the AI's reasoning */
  message: string;
  issued_at: string;
  is_active: boolean;
  // --- flood-alert details (backend/app/schemas/alert.py) ---
  region: string;
  district: string;
  flood_level: FloodLevel;
  title: string;
  rain_probability?: number | null;
  rain_event_mm: number;
  rain_duration_days: number;
  top_drivers: string[];
  affected_villages: AffectedVillage[];
  similar_incident?: { id: string; name: string; date: string; summary: string; deaths?: number | null } | null;
  source: "monitor" | "manual" | "scenario" | "test" | string;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  deliveries: AlertDelivery[];
  // --- confidence, freshness, horizon (optional: older alerts lack them) ---
  confidence_pct?: number | null;
  confidence_label?: ConfidenceLabel | null;
  horizon_hours?: number;
  data_mode?: DataMode | null;
  data_as_of?: string | null;
  // --- explanation, projection, actions ---
  why?: WhyItem[];
  model_drivers?: ModelDriver[];
  timeline?: TimelinePoint[];
  actions?: RecommendedAction[];
  // --- lifecycle ---
  status?: AlertStatus;
  resolved_at?: string | null;
  resolved_by?: string | null;
  supersedes_id?: number | null;
  provenance?: ProvenanceItem[];
  events?: AlertEvent[];
}

/** Which component produced part of an answer, and whether it really ran. */
export interface ProvenanceItem {
  component: string;
  kind: "trained" | "tuned" | "algorithmic" | "rule-based" | "llm" | string;
  status: "ran" | "estimated" | "not_run" | string;
  detail: string;
}

export interface AiComponent {
  name: string;
  kind: ProvenanceItem["kind"];
  method: string;
  artifact: string;
  runs: string;
  evidence: string | null;
  loaded: boolean;
}

export type ConfidenceLabel = "High" | "Medium" | "Low";
export type DataMode = "observed" | "climatology" | "demo" | "scenario" | "test";
export type AlertStatus = "active" | "acknowledged" | "resolved" | "superseded";
export type LifecycleStage =
  | "detected" | "generated" | "reviewed" | "sent" | "acknowledged" | "severity_changed" | "note" | "resolved";

export interface WhyItem {
  icon: "rain" | "soil" | "river" | "terrain" | "dam" | "tide" | "drainage" | "history" | "ai" | string;
  text: string;
  modelled?: boolean;
}

export interface ModelDriver {
  feature: string;
  label: string;
  value?: number | null;
  contribution: number;
}

export interface TimelinePoint {
  offset_h: number;
  band: FloodBand;
  probability: number;
  beyond_window?: boolean;
}

export interface RecommendedAction {
  text: string;
  priority: string;
  owner: string;
}

export interface AlertEvent {
  id: number;
  stage: LifecycleStage | string;
  at: string;
  actor: string;
  detail: string;
  data?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// System transparency (GET /api/v1/system/*) and demo (POST /api/v1/demo/run)
// ---------------------------------------------------------------------------
export interface SystemComponent {
  state: string;
  label: string;
  detail: string;
  age_minutes?: number;
  mode?: string;
  failures_last_hour?: number;
  last_run?: string | null;
}

export interface Degradation {
  component: string;
  severity: "warning" | "critical";
  title: string;
  message: string;
}

export interface SystemStatus {
  generated_at: string;
  prototype_mode?: boolean;
  prototype_notice?: string;
  components: Record<"ai_model" | "weather_data" | "river_data" | "notifications" | "monitor", SystemComponent>;
  degradations: Degradation[];
  faults: Record<FaultComponent, boolean>;
}

export type FaultComponent = "rainfall_feed" | "ai_model" | "notifications";

export interface DataSource {
  input: string;
  source: string;
  mode: "live" | "manual" | "cached" | "historical" | "modelled" | "simulated" | "demo" | "static" | "unavailable";
  last_update: string | null;
  note: string;
}

export interface SnapshotVillage {
  id: string;
  name: string;
  district: string;
  lat: number;
  lon: number;
  band: FloodBand;
  probability: number;
  depth_m: number;
  river_rise_m: number;
  landslide_risk: boolean;
  reasons: string[];
}

export interface RegionRiskSnapshot {
  region: string;
  data_mode: DataMode;
  data_as_of: string;
  age_minutes: number;
  rain_event_mm: number;
  duration_days: number;
  rain_probability: number | null;
  confidence_label: ConfidenceLabel | null;
  villages: SnapshotVillage[];
}

export interface DemoStage {
  key: string;
  label: string;
  detail: string;
}

export interface DemoRunResult {
  scenario: string;
  title: string;
  region: string;
  stages: DemoStage[];
  alerts_created: number[];
  top_alert_id: number | null;
  elapsed_ms: number;
}

export interface ClassMetrics {
  accuracy: number;
  precision_macro: number;
  recall_macro: number;
  f1_macro: number;
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  confusion_matrix: number[][];
}

export interface WarningMetrics {
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
  heavy_recall: number | null;
  heavy_precision: number | null;
  missed_event_rate: number | null;
  false_alarm_rate: number | null;
  heavy_days: number;
  normal_days: number;
}

export interface ModelPerformance {
  components?: AiComponent[];
  model_name: string;
  model_version: string;
  approach: string;
  training_date: string;
  task: string;
  validation: ClassMetrics | null;
  test: ClassMetrics | null;
  single_modality_test: Record<string, ClassMetrics> | null;
  warning_metrics: { validation: WarningMetrics | null; test: WarningMetrics | null };
  dataset: {
    rows: number;
    regions: string[];
    date_range: [string, string];
    target_counts: Record<string, number>;
    splits: Record<string, number>;
    source: string;
  } | null;
  caveats: string[];
}

export type FloodLevel = "moderate" | "high" | "severe";
export type FloodBand = "low" | FloodLevel;
export type AlertChannel = "telegram" | "email" | "sms" | "whatsapp";

export interface AffectedVillage {
  name: string;
  band: FloodBand;
  probability: number;
  depth_m: number;
  reasons: string[];
  /** MODELLED river rise above normal, metres (not a gauge reading) */
  river_rise_m?: number | null;
}

export interface AlertDelivery {
  id: number;
  recipient_name: string;
  channel: AlertChannel | "inapp" | "console" | string;
  target?: string | null;
  status: "sent" | "failed" | "skipped" | string;
  error?: string | null;
  attempts: number;
  sent_at: string;
}

export interface Recipient {
  id: number;
  name: string;
  role: "collector" | "adm" | "sdma" | "control_room" | "other";
  region: string;
  district?: string | null;
  phone?: string | null;
  whatsapp?: string | null;
  email?: string | null;
  telegram_chat_id?: string | null;
  channels: AlertChannel[];
  min_level: FloodLevel;
  active: boolean;
  created_at?: string;
}

export type RecipientInput = Omit<Recipient, "id" | "created_at">;

export interface AlertRule {
  id: number;
  region?: string | null;
  district?: string | null;
  min_level: FloodLevel;
  min_probability: number;
  cooldown_minutes: number;
  active: boolean;
}

export interface ProviderStatus {
  channel: string;
  name: string;
  enabled: boolean;
  cost: string;
  missing_config: string[];
}

export interface EvaluateRequest {
  region: string;
  rain_24h_mm?: number | null;
  rain_event_mm?: number | null;
  duration_days?: number;
  antecedent?: Antecedent;
  dam_release?: boolean;
  high_tide?: boolean;
  dispatch?: boolean;
  ignore_cooldown?: boolean;
}

export interface EvaluateResponse {
  region: string;
  rain_event_mm: number;
  rain_probability?: number | null;
  districts: { district: string; level: FloodBand; flood_probability: number; villages_at_risk: string[]; action: string }[];
  alerts_created: number[];
  deliveries: Record<string, { channel: string; recipient: string; status: string; error?: string | null }[]>;
}

export interface TestAlertRequest {
  region: string;
  district?: string | null;
  level?: FloodLevel;
  recipient_ids?: number[] | null;
  channels?: AlertChannel[] | null;
}

/** Events pushed on GET /api/v1/alerts/stream (Server-Sent Events). */
export type AlertStreamEvent =
  | { type: "hello" }
  | { type: "alert"; alert_id: number; level: FloodLevel; title: string; district: string; region: string; message: string }
  | { type: "deliveries"; alert_id: number; deliveries: { channel: string; recipient: string; status: string }[] }
  | { type: "acknowledged"; alert_id: number; by: string }
  | { type: "snapshot"; region: string }
  | { type: "reviewed" | "severity_changed" | "resolved" | "note"; alert_id: number };

// ---------------------------------------------------------------------------
// What-if simulator (POST /api/v1/scenarios/simulate) and assistant (POST /api/v1/chat)
// ---------------------------------------------------------------------------

export type Antecedent = "dry" | "normal" | "saturated";

export interface ScenarioRequest {
  region: string;
  rainfall_change_pct?: number | null;
  rainfall_mm?: number | null;
  duration_days?: number;
  antecedent?: Antecedent;
  dam_release?: boolean;
  high_tide?: boolean;
  humidity_pct?: number | null;
  cloud_cover_pct?: number | null;
  district?: string | null;
}

export interface FactorContribution {
  factor: string;
  label: string;
  value: number;
  contribution: number;
  detail: string;
}

export interface VillageImpact {
  id: string;
  name: string;
  district: string;
  region: string;
  lat: number;
  lon: number;
  population: number;
  baseline_probability: number;
  flood_probability: number;
  baseline_band: FloodBand;
  band: FloodBand;
  band_increased: boolean;
  runoff_mm: number;
  expected_depth_m: number;
  landslide_risk: boolean;
  /** MODELLED river rise above normal, metres (not a gauge reading) */
  river_rise_m?: number;
  factors: FactorContribution[];
  reasons: string[];
  timeline?: TimelinePoint[];
}

export interface DriverChange {
  feature: string;
  label: string;
  baseline_value: number | null;
  scenario_value: number | null;
  baseline_contribution: number;
  scenario_contribution: number;
  delta: number;
}

export interface ModelRisk {
  probability: number;
  risk_level: string;
  confidence: number;
  confidence_label?: ConfidenceLabel;
  horizon_hours?: number;
  class_probabilities: Record<string, number>;
}

export interface RainfallInputs {
  rain_1d_mm: number;
  rain_3d_mm: number;
  rain_7d_mm: number;
  rain_30d_mm: number;
  event_total_mm: number;
  duration_days: number;
  change_pct: number;
}

export interface IncidentMatch {
  id: string;
  name: string;
  date: string;
  region: string;
  districts: string[];
  villages: string[];
  rainfall_mm: number;
  rainfall_window_days: number;
  deaths?: number | null;
  displaced?: number | null;
  causes: string[];
  summary: string;
  source: string;
  similarity?: number;
  why_similar?: string[];
}

export interface ScenarioResult {
  region: string;
  scenario: ScenarioRequest;
  baseline_rain: RainfallInputs;
  scenario_rain: RainfallInputs;
  baseline_model: ModelRisk | null;
  scenario_model: ModelRisk | null;
  model_delta: number | null;
  driver_changes: DriverChange[];
  villages: VillageImpact[];
  summary: {
    villages_assessed: number;
    villages_high_or_severe: number;
    newly_at_risk: number;
    population_at_risk: number;
    districts_at_risk: string[];
    headline: string;
  };
  timeline?: TimelinePoint[];
  actions?: RecommendedAction[];
  data_mode?: DataMode;
  generated_at?: string | null;
  provenance?: ProvenanceItem[];
  similar_incidents: IncidentMatch[];
  model_analogues: { region: string; date: string; observed_rainfall_mm: number; similarity_pct: number }[];
  assumptions: string[];
  caveats: string[];
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
}

export interface ChatResponse {
  session_id: string;
  reply_markdown: string;
  scenario?: ScenarioResult | null;
  incidents: IncidentMatch[];
  villages: Record<string, unknown>[];
  alert_preview?: string | null;
  tools_used: string[];
  model: string;
}

export interface RegionProfile {
  name: string;
  state: string;
  lat: number;
  lon: number;
  peak_month: number;
  heavy_spell: { rain_1d: number; rain_3d: number };
  districts: { name: string; collector_office: string; lat: number; lon: number }[];
}

/** Runtime shape of GET /api/v1/health (untyped dict in OpenAPI). */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

/** Runtime shape of GET /api/v1/predictions/model-info (untyped dict in OpenAPI). */
export interface ModelInfoResponse {
  model_loaded: boolean;
  artifact_dir: string;
  expected_models: {
    tabular: string;
    vision: string;
    hybrid: string;
  };
}

export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface HTTPValidationError {
  detail: ValidationErrorItem[];
}


/** FastAPI HTTPException body (501 and other raised HTTP errors). */
export interface HTTPExceptionBody {
  detail: string;
}

// ---------------------------------------------------------------------------
// Grad-CAM image explanation types (POST /api/v1/predictions/explain-image)
// ---------------------------------------------------------------------------

/** One named high-attention region extracted from the Grad-CAM heatmap. */
export interface GradCamRegion {
  name: string;
  /** Normalised bounding box [x0, y0, x1, y1] in scene coordinates */
  bbox: number[];
  /** Share of the whole scene this region covers */
  area_share: number;
  /** Mean normalised attribution inside the region */
  intensity: number;
  /** Plain-language position within the scene */
  position: string;
}

/**
 * Real Grad-CAM explanation from the trained satellite CNN (satellite_model_v1.pt).
 * Returned by POST /api/v1/predictions/explain-image.
 * Both image URLs are base64 PNG data URLs — no static file server required.
 */
export interface GradCamResponse {
  /** Always "real" — distinguishes from simulator Grad-CAM */
  source: "real";
  model_name: string;
  model_version: string;
  /** Convolutional layer used for attribution (e.g. 'features.3') */
  target_layer: string;
  predicted_category: number;
  class_probabilities: Record<string, number>;
  satellite_risk_score: number;
  high_influence_coverage: number;
  coverage_label: string;
  regions: GradCamRegion[];
  /** Normalised heatmap as a PNG data URL (data:image/png;base64,…) */
  heatmap_data_url: string;
  /** Side-by-side overlay (original scene + heatmap) as a PNG data URL */
  overlay_data_url: string;
  notes: string[];
}
