import { useEffect } from "react";
import { CircleMarker, MapContainer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { AlertResponse, GeoPoint } from "../../types/api";
import { INDIA_BOUNDS, INDIA_CENTER } from "../../lib/places";
import { cn } from "../../lib/cn";
import { BaseTiles } from "./BaseTiles";

const RISK_COLOR: Record<string, string> = {
  low: "#3f7d56",
  moderate: "#b08a1f",
  heavy: "#c8612a",
  extreme: "#b3342b",
};

/** Zoom to the alerts when there are any, otherwise show all of India. */
function FitView({ alerts }: { alerts: AlertResponse[] }) {
  const map = useMap();
  const key = alerts.map((a) => a.id).join(",");
  useEffect(() => {
    if (!alerts.length) {
      map.fitBounds(INDIA_BOUNDS);
      return;
    }
    const lats = alerts.map((a) => a.location.latitude);
    const lons = alerts.map((a) => a.location.longitude);
    map.fitBounds(
      [
        [Math.min(...lats) - 1, Math.min(...lons) - 1],
        [Math.max(...lats) + 1, Math.max(...lons) + 1],
      ],
      { padding: [30, 30], maxZoom: 8 },
    );
  }, [key, map]); // only when the set of alerts changes, so user panning isn't undone
  return null;
}

function ClickHandler({ onClick }: { onClick?: (point: GeoPoint) => void }) {
  useMapEvents({
    click(event) {
      onClick?.({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    },
  });
  return null;
}

export function IndiaMap({
  alerts = [],
  selectedId,
  onSelectAlert,
  onMapClick,
  selection,
  className,
}: {
  alerts?: AlertResponse[];
  selectedId?: number | null;
  onSelectAlert?: (alert: AlertResponse) => void;
  onMapClick?: (point: GeoPoint) => void;
  selection?: GeoPoint | null;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "map-shell relative isolate min-h-[22rem] w-full overflow-hidden rounded-xl border border-stone-200/80 shadow-card",
        onMapClick && "cursor-crosshair",
        className,
      )}
    >
      <MapContainer
        bounds={INDIA_BOUNDS}
        center={INDIA_CENTER}
        className="map-container h-full min-h-[22rem] w-full"
        maxBounds={INDIA_BOUNDS}
        maxBoundsViscosity={0.7}
        minZoom={4}
        scrollWheelZoom
        zoom={5}
      >
        <BaseTiles />
        {!onMapClick && <FitView alerts={alerts} />}
        <ClickHandler onClick={onMapClick} />
        {alerts.map((alert) => {
          const selected = selectedId === alert.id;
          return (
            <CircleMarker
              center={[alert.location.latitude, alert.location.longitude]}
              eventHandlers={{ click: () => onSelectAlert?.(alert) }}
              key={alert.id}
              pathOptions={{
                color: selected ? "#10303f" : "#ffffff",
                fillColor: RISK_COLOR[alert.risk_level],
                fillOpacity: 0.9,
                weight: selected ? 3 : 2,
              }}
              radius={selected ? 11 : 8}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <span className="text-xs">
                  <b>{alert.district ?? alert.region_name}</b>
                  {alert.flood_level ? ` · ${alert.flood_level} flood risk` : ""} · {(alert.probability * 100).toFixed(0)}%
                </span>
              </Tooltip>
            </CircleMarker>
          );
        })}
        {selection && (
          <CircleMarker
            center={[selection.latitude, selection.longitude]}
            pathOptions={{ color: "#ffffff", fillColor: "#1a4f69", fillOpacity: 1, weight: 3 }}
            radius={9}
          />
        )}
      </MapContainer>
    </div>
  );
}
