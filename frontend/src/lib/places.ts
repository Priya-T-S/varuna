export const PLACE_PRESETS = [
  { name: "Mumbai", latitude: 19.076, longitude: 72.8777 },
  { name: "Kochi", latitude: 9.9312, longitude: 76.2673 },
  { name: "Chennai", latitude: 13.0827, longitude: 80.2707 },
  { name: "Kolkata", latitude: 22.5726, longitude: 88.3639 },
  { name: "Guwahati", latitude: 26.1445, longitude: 91.7362 },
  { name: "Delhi", latitude: 28.6139, longitude: 77.209 },
] as const;

export const INDIA_CENTER: [number, number] = [22.5, 79.0];
export const INDIA_BOUNDS: [[number, number], [number, number]] = [
  [6.5, 68.0],
  [36.0, 97.5],
];
