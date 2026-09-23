import { TileLayer } from "react-leaflet";

/**
 * Esri "Light Gray Canvas" basemap: calm, low-contrast, and needs no API key
 * (the previous CARTO tiles began requiring one). The reference layer draws
 * the place labels.
 */
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";

export function BaseTiles() {
  return (
    <>
      <TileLayer
        attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
        maxZoom={16}
        url={`${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`}
      />
      <TileLayer maxZoom={16} url={`${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`} />
    </>
  );
}
