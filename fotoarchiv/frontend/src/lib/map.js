// Gemeinsames für Karten: Leaflet mit OpenStreetMap, Stecknadel, Ortssuche (Nominatim).

import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';
const PIN = 'M12,11.5A2.5,2.5 0 0,1 9.5,9A2.5,2.5 0 0,1 12,6.5A2.5,2.5 0 0,1 14.5,9A2.5,2.5 0 0,1 12,11.5M12,2A7,7 0 0,0 5,9C5,14.25 12,22 12,22C12,22 19,14.25 19,9A7,7 0 0,0 12,2Z';

export { L };

export function createMap(element, options = {}) {
  const map = L.map(element, { worldCopyJump: true, minZoom: 2, zoomControl: true, ...options });
  L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
  return map;
}

export const pinIcon = () =>
  L.divIcon({
    className: 'map-pin',
    html: `<svg viewBox="0 0 24 24" width="40" height="40"><path d="${PIN}"/></svg>`,
    iconSize: [40, 40],
    iconAnchor: [20, 38],
  });

/** Ortssuche über OpenStreetMap Nominatim (nur auf ausdrücklichen Wunsch, keine Autovervollständigung). */
export async function searchPlaces(query) {
  const params = new URLSearchParams({ q: query, format: 'jsonv2', limit: '6', 'accept-language': 'de' });
  const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!response.ok) throw new Error('Ortssuche nicht erreichbar');
  const results = await response.json();
  return results.map((r) => ({
    name: r.display_name,
    lat: Number(r.lat),
    lon: Number(r.lon),
    // boundingbox: [süd, nord, west, ost]
    bounds: r.boundingbox ? [[Number(r.boundingbox[0]), Number(r.boundingbox[2])], [Number(r.boundingbox[1]), Number(r.boundingbox[3])]] : null,
  }));
}
