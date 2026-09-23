import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { getCurrentRisk } from "../../api/systemApi";
import { getIncidents, getRegions, getVillages } from "../../api/scenarioApi";
import type { AlertResponse, FloodBand } from "../../types/api";
import { INDIA_BOUNDS, INDIA_CENTER } from "../../lib/places";
import { cn } from "../../lib/cn";
import { formatRelative } from "../../lib/format";
import { FLOOD_BAND_COLOR, FLOOD_BAND_LABEL } from "../ui/FloodBandChip";
import { DATA_MODE_LABEL } from "../ui/PredictionMeta";
import { BaseTiles } from "./BaseTiles";

type LayerKey = "rainfall" | "rivers" | "villages" | "districts" | "history" | "alerts";

const LAYERS: { key: LayerKey; label: string }[] = [
  { key: "rainfall", label: "Rainfall" },
  { key: "rivers", label: "Rivers" },
  { key: "villages", label: "Villages" },
  { key: "districts", label: "Districts" },
  { key: "history", label: "Historical floods" },
  { key: "alerts", label: "Current alerts" },
];

const RISK_COLOR: Record<string, string> = { low: "#3f7d56", moderate: "#b08a1f", heavy: "#c8612a", extreme: "#b3342b" };
const HYDRO_OVERLAY =
  "https://tiles.arcgis.com/tiles/P3ePLMYs2RVChkJx/arcgis/rest/services/Esri_Hydro_Reference_Overlay/MapServer/tile/{z}/{y}/{x}";

function FitView({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join("|");
  const [size, setSize] = useState("");
  // Leaflet measures its container once; re-measure when the layout settles or resizes.
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const el = map.getContainer();
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      setSize(`${el.clientWidth}x${el.clientHeight}`);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => {
    // Defer one frame: on first paint the container may not have its final
    // height yet, and fitting against a stale size leaves the map zoomed out.
    const fit = () => {
      map.invalidateSize();
      if (!points.length) {
        map.fitBounds(INDIA_BOUNDS);
        return;
      }
      const lats = points.map((p) => p[0]);
      const lons = points.map((p) => p[1]);
      map.fitBounds(
        [[Math.min(...lats) - 0.8, Math.min(...lons) - 0.8], [Math.max(...lats) + 0.8, Math.max(...lons) + 0.8]],
        { padding: [30, 30], maxZoom: 8 },
      );
    };
    const raf = requestAnimationFrame(fit);
    const timer = window.setTimeout(fit, 250);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timer);
    };
  }, [key, size, map]); // only when the focus set or map size changes, so user panning isn't undone
  return null;
}

/**
 * Operational map with optional layers: rainfall, rivers, villages (current risk),
 * district HQs, historical floods and current alerts, plus a legend.
 */
export function LayeredMap({
  alerts = [],
  selectedAlertId,
  onSelectAlert,
  className,
  initialLayers = ["villages", "alerts", "rainfall"],
}: {
  alerts?: AlertResponse[];
  selectedAlertId?: number | null;
  onSelectAlert?: (alert: AlertResponse) => void;
  className?: string;
  initialLayers?: LayerKey[];
}) {
  const [on, setOn] = useState<Set<LayerKey>>(new Set(initialLayers));
  // On a phone the panel would cover half the map, so it starts collapsed.
  const [panelOpen, setPanelOpen] = useState(() => (typeof window === "undefined" ? true : window.innerWidth >= 640));
  const toggle = (k: LayerKey) =>
    setOn((s) => {
      const next = new Set(s);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  const riskQuery = useQuery({ queryKey: ["current-risk"], queryFn: getCurrentRisk, refetchInterval: 60000 });
  const regionsQuery = useQuery({ queryKey: ["regions"], queryFn: getRegions, staleTime: Infinity });
  const villagesQuery = useQuery({ queryKey: ["geo-villages"], queryFn: getVillages, staleTime: Infinity });
  const incidentsQuery = useQuery({ queryKey: ["geo-incidents"], queryFn: getIncidents, staleTime: Infinity, enabled: on.has("history") });

  const snapshots = riskQuery.data ?? [];
  const assessedIds = new Set(snapshots.flatMap((s) => s.villages.map((v) => v.id)));
  const unassessed = (villagesQuery.data ?? []).filter((v) => !assessedIds.has(v.id));

  const history = useMemo(() => {
    const byName = new Map((villagesQuery.data ?? []).map((v) => [v.name.toLowerCase(), v]));
    const out = new Map<string, { lat: number; lon: number; name: string; events: string[] }>();
    for (const inc of incidentsQuery.data ?? []) {
      for (const name of inc.villages) {
        const v = byName.get(name.toLowerCase());
        if (!v) continue;
        const entry = out.get(v.id) ?? { lat: v.lat, lon: v.lon, name: v.name, events: [] };
        entry.events.push(`${inc.name} (${inc.date.slice(0, 4)})`);
        out.set(v.id, entry);
      }
    }
    return [...out.values()];
  }, [incidentsQuery.data, villagesQuery.data]);

  const focus: [number, number][] = alerts.length
    ? alerts.map((a) => [a.location.latitude, a.location.longitude])
    : snapshots.flatMap((s) => s.villages.map((v) => [v.lat, v.lon] as [number, number]));

  return (
    <div className={cn("map-shell relative isolate min-h-[22rem] w-full overflow-hidden rounded-xl border border-stone-200/80 shadow-card", className)}>
      <MapContainer bounds={INDIA_BOUNDS} center={INDIA_CENTER} className="map-container h-full min-h-[22rem] w-full" minZoom={4} scrollWheelZoom zoom={5}>
        <BaseTiles />
        {on.has("rivers") && <TileLayer attribution="Hydro &copy; Esri" opacity={0.9} url={HYDRO_OVERLAY} />}
        <FitView points={focus} />

        {on.has("rainfall") && regionsQuery.data && snapshots.map((s) => {
          const r = regionsQuery.data!.find((x) => x.name === s.region);
          if (!r) return null;
          return (
            <Circle
              center={[r.lat, r.lon]}
              key={`rain-${s.region}`}
              pathOptions={{ color: "#2a6f8f", fillColor: "#4b93b1", fillOpacity: 0.12, weight: 1, dashArray: "4 4" }}
              radius={Math.min(20000 + s.rain_event_mm * 250, 260000)}
            >
              <Tooltip direction="center" permanent={false}>
                <span className="text-xs"><b>{s.region}</b>: {s.rain_event_mm.toFixed(0)} mm / {s.duration_days} d · {DATA_MODE_LABEL[s.data_mode] ?? s.data_mode}, {formatRelative(s.data_as_of)}</span>
              </Tooltip>
            </Circle>
          );
        })}

        {on.has("districts") && regionsQuery.data?.flatMap((r) => r.districts.map((d) => (
          <CircleMarker center={[d.lat, d.lon]} key={`d-${r.name}-${d.name}`} pathOptions={{ color: "#1c1917", fillColor: "#ffffff", fillOpacity: 1, weight: 1.5 }} radius={4}>
            <Tooltip><span className="text-xs"><b>{d.name}</b> district HQ<br />{d.collector_office}</span></Tooltip>
          </CircleMarker>
        )))}

        {on.has("history") && history.map((h) => (
          <CircleMarker center={[h.lat, h.lon]} key={`h-${h.name}`} pathOptions={{ color: "#6d28d9", fillOpacity: 0, weight: 2, dashArray: "2 3" }} radius={12}>
            <Tooltip><span className="text-xs"><b>{h.name}</b>: flooded before<br />{h.events.slice(0, 3).join("; ")}</span></Tooltip>
          </CircleMarker>
        ))}

        {on.has("villages") && unassessed.map((v) => (
          <CircleMarker center={[v.lat, v.lon]} key={`u-${v.id}`} pathOptions={{ color: "#ffffff", fillColor: "#a8a29e", fillOpacity: 0.8, weight: 1 }} radius={4}>
            <Tooltip><span className="text-xs"><b>{v.name}</b>: no current assessment</span></Tooltip>
          </CircleMarker>
        ))}

        {on.has("villages") && snapshots.flatMap((s) => s.villages.map((v) => (
          <CircleMarker
            center={[v.lat, v.lon]}
            key={`v-${v.id}`}
            pathOptions={{ color: "#ffffff", fillColor: FLOOD_BAND_COLOR[v.band as FloodBand], fillOpacity: 0.95, weight: 1.5 }}
            radius={4 + v.probability * 5}
          >
            <Popup>
              <div className="min-w-[13rem] text-[12.5px] leading-5">
                <p className="text-[13.5px] font-semibold">{v.name}</p>
                <p className="text-stone-500">{v.district}, {s.region}</p>
                <p className="mt-1">
                  <b style={{ color: FLOOD_BAND_COLOR[v.band as FloodBand] }}>{FLOOD_BAND_LABEL[v.band as FloodBand]}</b> flood risk · {(v.probability * 100).toFixed(0)}%
                </p>
                <p>~{v.depth_m} m water · river +{v.river_rise_m} m <i>(modelled)</i>{v.landslide_risk ? " · landslide risk" : ""}</p>
                {v.reasons[0] && <p className="mt-1 text-stone-600">{v.reasons[0]}</p>}
                <p className="mt-1 text-[11px] text-stone-400">Data: {DATA_MODE_LABEL[s.data_mode] ?? s.data_mode}, {formatRelative(s.data_as_of)}</p>
              </div>
            </Popup>
          </CircleMarker>
        )))}

        {on.has("alerts") && alerts.map((a) => {
          const selected = selectedAlertId === a.id;
          return (
            <CircleMarker
              center={[a.location.latitude, a.location.longitude]}
              eventHandlers={{ click: () => onSelectAlert?.(a) }}
              key={`a-${a.id}`}
              pathOptions={{ color: selected ? "#10303f" : "#1c1917", fillColor: RISK_COLOR[a.risk_level], fillOpacity: 0.95, weight: selected ? 3.5 : 2 }}
              radius={selected ? 13 : 10}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                <span className="text-xs"><b>{a.district}</b> · {a.flood_level} alert · {(a.probability * 100).toFixed(0)}%</span>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <div className="absolute right-3 top-3 z-[400] w-40 rounded-lg border border-stone-200 bg-white/95 text-[12px] shadow-sm sm:w-44">
        <button
          aria-expanded={panelOpen}
          className="flex w-full items-center justify-between px-3 py-2 font-semibold text-stone-800"
          onClick={() => setPanelOpen((o) => !o)}
          type="button"
        >
          Map layers <span className="text-stone-400">{panelOpen ? "−" : "+"}</span>
        </button>
        {panelOpen && (
          <div className="space-y-1 border-t border-stone-100 px-3 pb-2.5 pt-2">
            {LAYERS.map((l) => (
              <label className="flex cursor-pointer items-center gap-2 text-stone-700" key={l.key}>
                <input checked={on.has(l.key)} className="accent-brand-700" onChange={() => toggle(l.key)} type="checkbox" />
                {l.label}
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="pointer-events-none absolute bottom-3 left-3 z-[400] hidden max-w-[calc(100%-1.5rem)] rounded-lg border border-stone-200 bg-white/95 px-3 py-2 text-[11px] text-stone-600 shadow-sm sm:block">
        <p className="mb-1 font-semibold text-stone-800">Flood risk</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {(["low", "moderate", "high", "severe"] as const).map((b) => (
            <span className="flex items-center gap-1" key={b}>
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: FLOOD_BAND_COLOR[b] }} /> {FLOOD_BAND_LABEL[b]}
            </span>
          ))}
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-stone-400" /> Not assessed</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full border-2 border-stone-900" /> Alert (district)</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full border-2 border-dashed border-violet-700" /> Flooded before</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full border border-stone-900 bg-white" /> District HQ</span>
        </div>
        {riskQuery.data && riskQuery.data.length === 0 && (
          <p className="mt-1 text-stone-500">Villages turn coloured once a region is assessed (monitor, Evaluate now or demo).</p>
        )}
      </div>
    </div>
  );
}
