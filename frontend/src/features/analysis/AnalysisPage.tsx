import { useRef, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createPrediction, explainImage } from "../../api/predictionsApi";
import { ApiError } from "../../api/errors";
import { IndiaMap } from "../../components/map/IndiaMap";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { IconBrain, IconCheck, IconTarget, IconUpload } from "../../components/ui/Icons";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { PredictionMeta } from "../../components/ui/PredictionMeta";
import { ProvenanceList } from "../../components/ui/ProvenanceList";
import { RiskChip } from "../../components/ui/RiskChip";
import { SimulatedBanner } from "../../components/ui/SimulatedBanner";
import { ErrorState, Skeleton } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { featureLabel, featureUnit } from "../../lib/featureLabels";
import { formatCoordinate, formatDateTime, formatNumber, formatProbability } from "../../lib/format";
import { PLACE_PRESETS } from "../../lib/places";
import { simulatePrediction } from "../../lib/simulator";
import { validatePredictionRequest } from "../../lib/validation";
import { useUiStore } from "../../store/uiStore";
import type { FieldError } from "../../lib/validation";
import type { GeoPoint, GradCamResponse, WeatherFeatures } from "../../types/api";


const WEATHER_FIELDS: Array<{
  key: keyof WeatherFeatures;
  label: string;
  hint: string;
  step: string;
}> = [
  { key: "temperature_c", label: "Temperature (°C)", hint: "e.g. 27", step: "0.1" },
  { key: "humidity_pct", label: "Humidity (%)", hint: "0–100, e.g. 90", step: "0.1" },
  { key: "pressure_hpa", label: "Air pressure (hPa)", hint: "Sea-level, e.g. 1002", step: "0.1" },
  { key: "wind_speed_ms", label: "Wind speed (m/s)", hint: "e.g. 7", step: "0.1" },
  { key: "cloud_cover_pct", label: "Cloud cover (%)", hint: "0–100, e.g. 95", step: "0.1" },
];

/** Same thresholds as ai_models.fusion_model.utils.confidence_label. */
function confidenceLabelFor(confidence: number): "High" | "Medium" | "Low" {
  if (confidence >= 0.75) return "High";
  if (confidence >= 0.5) return "Medium";
  return "Low";
}

export function AnalysisPage() {
  const navigate = useNavigate();
  const draft = useUiStore((s) => s.analysisDraft);
  const patchDraft = useUiStore((s) => s.patchDraft);
  const setWeatherField = useUiStore((s) => s.setWeatherField);
  const simulatorMode = useUiStore((s) => s.simulatorMode);
  const setLastModelUnavailableDetail = useUiStore((s) => s.setLastModelUnavailableDetail);
  const setActiveAnalysis = useUiStore((s) => s.setActiveAnalysis);
  const addHistory = useUiStore((s) => s.addHistory);
  const activeAnalysis = useUiStore((s) => s.activeAnalysis);

  const [errors, setErrors] = useState<FieldError[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // --- Grad-CAM upload state -------------------------------------------
  const [gradCamFile, setGradCamFile] = useState<File | null>(null);
  const [gradCamResult, setGradCamResult] = useState<GradCamResponse | null>(null);
  const [gradCamError, setGradCamError] = useState<string | null>(null);
  const [showGradCamOverlay, setShowGradCamOverlay] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const errorMap = useMemo(() => Object.fromEntries(errors.map((e) => [e.field, e.message])), [errors]);

  const selection: GeoPoint | null = useMemo(() => {
    const lat = Number(draft.latitude);
    const lon = Number(draft.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
    return { latitude: lat, longitude: lon };
  }, [draft.latitude, draft.longitude]);

  const mutation = useMutation({
    mutationFn: async () => {
      const { errors: nextErrors, request } = validatePredictionRequest(draft);
      setErrors(nextErrors);
      if (!request) throw new Error("Fix the highlighted fields before running a prediction.");

      if (simulatorMode === "forced") {
        const response = simulatePrediction(request);
        return { request, response, simulated: true as const };
      }

      try {
        const response = await createPrediction(request);
        setLastModelUnavailableDetail(null);
        return { request, response, simulated: false as const };
      } catch (error) {
        if (error instanceof ApiError && error.code === "MODEL_NOT_DEPLOYED" && simulatorMode === "auto") {
          setLastModelUnavailableDetail(error.detail);
          const response = simulatePrediction(request);
          return { request, response, simulated: true as const };
        }
        throw error;
      }
    },
    onSuccess: (result) => {
      setSubmitError(null);
      setActiveAnalysis(result);
      addHistory(result);
    },
    onError: (error) => {
      setSubmitError(error instanceof Error ? error.message : "Prediction failed.");
    },
  });

  const gradCamMutation = useMutation({
    mutationFn: async (file: File) => explainImage(file),
    onSuccess: (result) => {
      setGradCamResult(result);
      setGradCamError(null);
    },
    onError: (error) => {
      setGradCamError(error instanceof Error ? error.message : "Grad-CAM failed.");
    },
  });

  return (
    <div className="space-y-6">
    <PageHeader
      description="Pick a place, add current weather if you have it, and get the AI's heavy-rain forecast with a full explanation. Empty weather fields use typical values."
      eyebrow="Forecast"
      title="Point analysis"
    />
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <div className="space-y-4">
        <Panel
          description="Click the map or pick a city, then fill in any weather you know."
          title="Location & weather"
        >
          <IndiaMap
            className="mb-3 min-h-[16rem]"
            onMapClick={(point) =>
              patchDraft({
                latitude: point.latitude.toFixed(4),
                longitude: point.longitude.toFixed(4),
              })
            }
            selection={selection}
          />
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] font-medium text-stone-500">Quick pick:</span>
            <div className="flex flex-wrap gap-1.5">
              {PLACE_PRESETS.map((place) => (
                <button
                  className={cn(
                    "rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors",
                    draft.region_name === place.name
                      ? "border-brand-600 bg-brand-700 text-white"
                      : "border-stone-300 bg-white text-stone-700 hover:border-brand-300 hover:bg-brand-50",
                  )}
                  key={place.name}
                  onClick={() =>
                    patchDraft({
                      region_name: place.name,
                      latitude: String(place.latitude),
                      longitude: String(place.longitude),
                    })
                  }
                  type="button"
                >
                  {place.name}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              error={errorMap.latitude}
              hint="−90 to 90"
              label="Latitude"
              name="latitude"
              onChange={(e) => patchDraft({ latitude: e.target.value })}
              required
              value={draft.latitude}
            />
            <Input
              error={errorMap.longitude}
              hint="−180 to 180"
              label="Longitude"
              name="longitude"
              onChange={(e) => patchDraft({ longitude: e.target.value })}
              required
              value={draft.longitude}
            />
            <Input
              hint="Optional, e.g. Kerala"
              label="Place name"
              name="region_name"
              onChange={(e) => patchDraft({ region_name: e.target.value })}
              value={draft.region_name}
            />
            <Input
              error={errorMap.horizon_hours}
              hint="How far ahead, 1–72 hours"
              label="Forecast horizon (hours)"
              name="horizon_hours"
              onChange={(e) => patchDraft({ horizon_hours: e.target.value })}
              value={draft.horizon_hours}
            />
          </div>
          <h3 className="mb-3 mt-6 border-t border-stone-100 pt-5 text-[13.5px] font-semibold text-stone-800">
            Current weather <span className="font-normal text-stone-500">(optional)</span>
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {WEATHER_FIELDS.map((field) => (
              <Input
                error={errorMap[field.key]}
                hint={field.hint}
                key={field.key}
                label={field.label}
                name={field.key}
                onChange={(e) => setWeatherField(field.key, e.target.value)}
                step={field.step}
                type="number"
                value={draft.weather[field.key]}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              data-testid="run-prediction"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate()}
              type="button"
            >
              {mutation.isPending ? "Forecasting…" : "Run forecast"}
            </Button>
            <p className="text-[12.5px] text-stone-500">Includes a full explanation of the result.</p>
          </div>
          {submitError && <div className="mt-3"><ErrorState body={submitError} title="Prediction did not complete" /></div>}
        </Panel>
      </div>

      <div className="space-y-4 lg:sticky lg:top-[5.5rem] lg:self-start">
        <Panel title="Forecast">
          {mutation.isPending && (
            <div className="space-y-3 py-2">
              <Skeleton className="h-10 w-2/3" />
              <Skeleton className="h-24" />
            </div>
          )}
          {!mutation.isPending && !activeAnalysis && (
            <div className="py-6">
              <div className="text-center">
                <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-full bg-brand-50 text-brand-600"><IconTarget size={20} /></div>
                <p className="text-[15px] font-semibold text-stone-800">No forecast yet</p>
                <p className="mx-auto mt-1 max-w-sm text-[13px] leading-6 text-stone-500">
                  Choose a location on the left and press <b>Run forecast</b>.
                </p>
              </div>
              <ul className="mx-auto mt-5 max-w-sm space-y-2 text-[13px] text-stone-600">
                {[
                  "Chance of heavy rain in the next 24 hours, with a confidence level",
                  "Which weather inputs pushed the forecast up or down (SHAP)",
                  "The most similar days in the historical record",
                  "Which model or rule produced each part of the answer",
                ].map((line) => (
                  <li className="flex items-start gap-2" key={line}>
                    <IconCheck className="mt-0.5 shrink-0 text-brand-500" size={14} /> {line}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {activeAnalysis && !mutation.isPending && (
            <div className="space-y-5">
              {activeAnalysis.simulated && <SimulatedBanner />}
              <PredictionMeta
                confidenceLabel={confidenceLabelFor(activeAnalysis.response.confidence)}
                confidencePct={activeAnalysis.response.confidence * 100}
                dataAsOf={activeAnalysis.response.generated_at}
                dataMode={activeAnalysis.simulated ? "scenario" : "entered"}
                horizon={`Next ${activeAnalysis.response.horizon_hours} hours`}
                probability={activeAnalysis.response.probability}
                probabilityLabel="Heavy-rain probability"
              />
              <ProvenanceList compact items={activeAnalysis.response.explanation?.provenance} />
              <div className="flex items-start justify-between gap-3 rounded-xl bg-stone-50 p-4">
                <div>
                  <p className="text-[12.5px] text-stone-500">Risk level</p>
                  <div className="mt-1.5">
                    <RiskChip level={activeAnalysis.response.risk_level} />
                  </div>
                  <p className="mt-2 text-[13px] text-stone-600">
                    {activeAnalysis.response.region_name || "Selected point"} · next {activeAnalysis.response.horizon_hours} h
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[12.5px] text-stone-500">Chance of heavy rain</p>
                  <p className="text-[34px] font-semibold leading-tight tabular-nums text-stone-900">
                    {formatProbability(activeAnalysis.response.probability)}
                  </p>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
                <dt className="text-stone-500">Model confidence</dt>
                <dd className="font-medium tabular-nums">{formatProbability(activeAnalysis.response.confidence)}</dd>
                <dt className="text-stone-500">Location</dt>
                <dd className="tabular-nums">
                  {formatCoordinate(activeAnalysis.response.location.latitude, 3)}, {formatCoordinate(activeAnalysis.response.location.longitude, 3)}
                </dd>
                <dt className="text-stone-500">Generated</dt>
                <dd>{formatDateTime(activeAnalysis.response.generated_at)}</dd>
                <dt className="text-stone-500">Model</dt>
                <dd className="text-stone-600">{activeAnalysis.response.model_version}</dd>
              </dl>
              {activeAnalysis.request.weather && (
                <div className="border-t border-stone-100 pt-4">
                  <p className="mb-2 text-[13px] font-semibold text-stone-800">Weather you entered</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(activeAnalysis.request.weather) as Array<keyof WeatherFeatures>).map((key) => (
                      <span className="rounded-full bg-stone-100 px-2.5 py-1 text-[12px] text-stone-700" key={key}>
                        {featureLabel(key)}: <b>{formatNumber(activeAnalysis.request.weather?.[key] ?? null, 1)}{featureUnit(key) ? ` ${featureUnit(key)}` : ""}</b>
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <Button onClick={() => navigate("/explainability")} type="button">
                <IconBrain /> Open explanation
              </Button>
            </div>
          )}
        </Panel>

        {/* Grad-CAM satellite image upload panel */}
        <Panel
          description="Upload an INSAT satellite image (PNG, JPEG or TIFF) to see which cloud areas the satellite model focuses on."
          title="Satellite image heatmap (Grad-CAM)"
        >
          <div className="space-y-3">
            {/* File picker */}
            <div className="flex flex-wrap items-center gap-3">
              <input
                accept="image/png,image/jpeg,image/tiff,image/*"
                aria-label="Upload INSAT satellite scene"
                className="hidden"
                id="gradcam-file-input"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  setGradCamFile(file);
                  setGradCamResult(null);
                  setGradCamError(null);
                }}
                ref={fileInputRef}
                type="file"
              />
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-dashed border-stone-300 bg-stone-50 px-4 py-2.5 text-[13.5px] text-stone-700 transition-colors hover:border-brand-400 hover:bg-brand-50"
                onClick={() => fileInputRef.current?.click()}
                type="button"
              >
                <IconUpload />
                {gradCamFile ? gradCamFile.name : "Choose a satellite image…"}
              </button>
              {gradCamFile && (
                <Button
                  disabled={gradCamMutation.isPending}
                  onClick={() => gradCamMutation.mutate(gradCamFile)}
                  type="button"
                >
                  {gradCamMutation.isPending ? "Analysing image…" : "Analyse image"}
                </Button>
              )}
              {gradCamFile && (
                <button
                  className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
                  onClick={() => {
                    setGradCamFile(null);
                    setGradCamResult(null);
                    setGradCamError(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  type="button"
                >
                  Clear
                </button>
              )}
            </div>

            {gradCamError && <ErrorState body={gradCamError} title="Grad-CAM failed" />}

            {/* Results */}
            {gradCamResult && (
              <div className="space-y-3 border-t border-stone-200 pt-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-500">
                    Real Grad-CAM · {gradCamResult.model_name} v{gradCamResult.model_version}
                  </p>
                  <label className="flex items-center gap-2 text-xs text-stone-600">
                    <input
                      checked={showGradCamOverlay}
                      onChange={(e) => setShowGradCamOverlay(e.target.checked)}
                      type="checkbox"
                    />
                    Overlay
                  </label>
                </div>
                <div className="relative max-w-md border border-stone-300 bg-stone-900">
                  <img
                    alt={showGradCamOverlay ? "Grad-CAM heatmap overlay" : "Grad-CAM heatmap"}
                    className="block w-full"
                    src={showGradCamOverlay ? gradCamResult.overlay_data_url : gradCamResult.heatmap_data_url}
                  />
                </div>
                {/* Colour scale legend */}
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-stone-500">Attention scale</p>
                  <div className="flex h-3 overflow-hidden border border-stone-300">
                    <div className="flex-1 bg-[#3d5a6c]" />
                    <div className="flex-1 bg-[#c06a2c]" />
                    <div className="flex-1 bg-[#a33b32]" />
                  </div>
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-stone-500">
                    <span>Lower attention</span>
                    <span>Higher attention</span>
                  </div>
                </div>
                {/* Metadata */}
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs">
                  <dt className="text-stone-500">Target layer</dt>
                  <dd>{gradCamResult.target_layer}</dd>
                  <dt className="text-stone-500">Predicted class</dt>
                  <dd>{gradCamResult.predicted_category}</dd>
                  <dt className="text-stone-500">Satellite risk</dt>
                  <dd>{(gradCamResult.satellite_risk_score * 100).toFixed(1)}%</dd>
                  <dt className="text-stone-500">Coverage</dt>
                  <dd>{gradCamResult.coverage_label} ({(gradCamResult.high_influence_coverage * 100).toFixed(1)}%)</dd>
                </dl>
                {/* Class probabilities */}
                {Object.keys(gradCamResult.class_probabilities).length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-stone-500">Class probabilities</p>
                    <div className="space-y-1.5">
                      {Object.entries(gradCamResult.class_probabilities).map(([label, prob]) => (
                        <div key={label} className="flex items-center gap-2">
                          <span className="w-24 flex-shrink-0 font-mono text-[10.5px] text-stone-600">{label}</span>
                          <div className="h-2 flex-1 overflow-hidden border border-stone-200">
                            <div
                              className="h-full bg-stone-700"
                              style={{ width: `${(prob * 100).toFixed(1)}%` }}
                            />
                          </div>
                          <span className="w-10 text-right font-mono text-[10.5px] text-stone-700">{(prob * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Regions */}
                {gradCamResult.regions.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-stone-500">High-attention regions</p>
                    <div className="space-y-1">
                      {gradCamResult.regions.map((region) => (
                        <div className="flex items-baseline gap-3 text-xs" key={region.name}>
                          <span className="font-mono text-stone-800">{region.name}</span>
                          <span className="text-stone-500">{region.position}</span>
                          <span className="ml-auto font-mono text-stone-600">
                            {(region.intensity * 100).toFixed(0)}% intensity
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Notes */}
                {gradCamResult.notes.length > 0 && (
                  <ul className="list-disc pl-4 text-[11px] text-stone-500 space-y-0.5">
                    {gradCamResult.notes.map((note, i) => <li key={i}>{note}</li>)}
                  </ul>
                )}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
    </div>
  );
}
