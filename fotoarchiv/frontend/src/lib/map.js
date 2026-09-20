// Gemeinsames für Karten: Leaflet mit OpenStreetMap oder Satellitenbild, Stecknadel, Ortssuche (Nominatim).

import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Aus der Add-on-Konfiguration (api/state): 'de' = deutscher Kartenstil (Namen auf Deutsch, Landessprache in
// Klammern), 'local' = openstreetmap.org (jedes Land in seiner Sprache – arabisch, griechisch, kyrillisch …)
export const mapSettings = { language: 'de' };

const OSM = {
  de: {
    url: 'https://tile.openstreetmap.de/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> · <a href="https://www.openstreetmap.de" target="_blank" rel="noopener">openstreetmap.de</a>',
  },
  local: {
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  },
};
// Satellitenbild von Esri (frei mit Quellenangabe), darüber Grenzen und Ortsnamen – die sind auf Englisch
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
const ESRI_IMAGERY = `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`;
const ESRI_LABELS = `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`;
const ESRI_ATTRIBUTION = 'Satellit: &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics';
const SATELLITE_KEY = 'fotoarchiv.map.satellite';

// Home Assistant sendet "Referrer-Policy: no-referrer". OpenStreetMap blockiert Anfragen ohne Referer,
// daher hier ausdrücklich nur den Ursprung (z. B. https://ha.example.org/) mitschicken – nie Pfad oder Ingress-Token.
const REFERRER_POLICY = 'strict-origin-when-cross-origin';
const PIN = 'M12,11.5A2.5,2.5 0 0,1 9.5,9A2.5,2.5 0 0,1 12,6.5A2.5,2.5 0 0,1 14.5,9A2.5,2.5 0 0,1 12,11.5M12,2A7,7 0 0,0 5,9C5,14.25 12,22 12,22C12,22 19,14.25 19,9A7,7 0 0,0 12,2Z';

export { L };

function readSatellite() {
  try {
    return localStorage.getItem(SATELLITE_KEY) === '1';
  } catch {
    return false;
  }
}

export function createMap(element, options = {}) {
  const map = L.map(element, { worldCopyJump: true, minZoom: 2, maxZoom: 19, zoomControl: true, ...options });
  const style = OSM[mapSettings.language] ?? OSM.de;
  const street = L.tileLayer(style.url, { maxZoom: 19, attribution: style.attribution, referrerPolicy: REFERRER_POLICY });
  const satellite = L.layerGroup([
    L.tileLayer(ESRI_IMAGERY, { maxZoom: 19, attribution: ESRI_ATTRIBUTION, referrerPolicy: REFERRER_POLICY }),
    L.tileLayer(ESRI_LABELS, { maxZoom: 19, referrerPolicy: REFERRER_POLICY }),
  ]);
  let onSatellite = readSatellite();
  (onSatellite ? satellite : street).addTo(map);

  // Umschalter oben rechts; die Wahl gilt für alle Karten auf diesem Gerät
  const control = L.control({ position: 'topright' });
  let button;
  const label = () => (button.textContent = onSatellite ? 'Karte' : 'Satellit');
  control.onAdd = () => {
    const box = L.DomUtil.create('div', 'leaflet-bar layer-toggle');
    button = L.DomUtil.create('button', '', box);
    button.type = 'button';
    button.title = 'Zwischen Karte und Satellitenbild wechseln';
    label();
    L.DomEvent.disableClickPropagation(box);
    L.DomEvent.on(button, 'click', () => map.setSatellite(!onSatellite));
    return box;
  };
  control.addTo(map);

  map.setSatellite = (on) => {
    if (on === onSatellite) return;
    map.removeLayer(onSatellite ? satellite : street);
    (on ? satellite : street).addTo(map);
    onSatellite = on;
    if (button) label();
    try {
      localStorage.setItem(SATELLITE_KEY, on ? '1' : '0');
    } catch {
      /* dann gilt die Wahl nur bis zum Neuladen */
    }
  };
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
  const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, { referrerPolicy: REFERRER_POLICY });
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
