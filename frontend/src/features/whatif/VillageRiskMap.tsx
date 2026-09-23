import { useEffect } from "react";
import { CircleMarker, MapContainer, Tooltip, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import type { VillageImpact } from "../../types/api";
import { BaseTiles } from "../../components/map/BaseTiles";
import { FLOOD_BAND_COLOR, FLOOD_BAND_LABEL } from "../../components/ui/FloodBandChip";
import { INDIA_BOUNDS, INDIA_CENTER } from "../../lib/places";
import { cn } from "../../lib/cn";

function FitToVillages({ villages }: { villages: VillageImpact[] }) {
  const map = useMap();
  const key = villages.map((v) => v.id).join(",");
  useEffect(() => {
    if (!villages.length) return;
    const lats = villages.map((v) => v.lat);
    const lons = villages.map((v) => v.lon);
    const bounds: LatLngBoundsExpression = [
      [Math.min(...lats) - 0.08, Math.min(...lons) - 0.08],
      [Math.max(...lats) + 0.08, Math.max(...lons) + 0.08],
    ];
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 11 });
  }, [key, map]); // re-fit only when the set of villages changes, not on every re-render
  return null;
}

export function VillageRiskMap({
  villages,
  selectedId,
  onSelect,
  className,
}: {
  villages: VillageImpact[];
  selectedId?: string | null;
  onSelect?: (village: VillageImpact) => void;
  className?: string;
}) {
  // Draw low-risk first so severe markers sit on top where they overlap.
  const ordered = [...villages].sort((a, b) => a.flood_probability - b.flood_probability);
  return (
    <div className={cn("map-shell relative isolate w-full overflow-hidden rounded-xl border border-stone-200/80 shadow-card", className)}>
      <MapContainer
        bounds={INDIA_BOUNDS}
        center={INDIA_CENTER}
        className="map-container h-full min-h-[20rem] w-full"
        minZoom={4}
        scrollWheelZoom
        zoom={5}
      >
        <BaseTiles />
        <FitToVillages villages={villages} />
        {ordered.map((v) => {
          const selected = v.id === selectedId;
          return (
            <CircleMarker
              center={[v.lat, v.lon]}
              eventHandlers={{ click: () => onSelect?.(v) }}
              key={v.id}
              pathOptions={{
                color: selected ? "#10303f" : "#ffffff",
                dashArray: v.band_increased && !selected ? "4 3" : undefined,
                fillColor: FLOOD_BAND_COLOR[v.band],
                fillOpacity: 0.92,
                weight: selected ? 3 : 2,
              }}
              radius={6 + v.flood_probability * 8}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <span className="text-xs">
                  <b>{v.name}</b> · {v.district}
                  <br />
                  {FLOOD_BAND_LABEL[v.baseline_band]} → <b>{FLOOD_BAND_LABEL[v.band]}</b> · {(v.flood_probability * 100).toFixed(0)}%
                  {v.expected_depth_m > 0 ? ` · ~${v.expected_depth_m} m deep` : ""}
                  {v.landslide_risk ? " · landslide risk" : ""}
                </span>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <div className="pointer-events-none absolute bottom-3 left-3 z-[400] flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-stone-200 bg-white/95 px-2.5 py-1.5 text-[11.5px] text-stone-600 shadow-sm">
        {(["low", "moderate", "high", "severe"] as const).map((band) => (
          <span className="flex items-center gap-1.5" key={band}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: FLOOD_BAND_COLOR[band] }} />
            {FLOOD_BAND_LABEL[band]}
          </span>
        ))}
        <span className="flex items-center gap-1.5 border-l border-stone-200 pl-3">
          <span className="h-2.5 w-2.5 rounded-full border border-dashed border-stone-700" /> Risk went up
        </span>
      </div>
    </div>
  );
}
