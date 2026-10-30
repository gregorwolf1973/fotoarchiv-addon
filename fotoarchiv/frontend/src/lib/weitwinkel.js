// Weitwinkel- und Fischaugenfotos entzerren: Für jeden Bildschirmpunkt wird die Blickrichtung
// berechnet und über das Linsenmodell auf das Foto zurückgerechnet. Dieselbe Rechnung steckt
// im Shader (SHADER unten); die JS-Fassung dient den Grenzen der Ansicht und den Tests.
//
// Viele Action-Kameras (GoPro „SuperView“ u. ä.) speichern 16:9-Fotos, die zusätzlich waagerecht
// ungleichmäßig gestreckt sind: in der Mitte gestaucht, zum Rand hin gedehnt. Das bildet stretch ab;
// ohne es bleiben Kanten auch mit dem richtigen Bildwinkel gebogen. tilt gleicht eine nach unten
// (positiv) bzw. oben geneigte Kamera aus, damit Senkrechte bei waagrechtem Blick senkrecht stehen.

const DEG = Math.PI / 180;

/** Linsenmodelle: Abstand r vom Bildmittelpunkt bei Winkel θ zur Achse, Brennweite f = 1. */
export const MODELS = {
  equidistant: { label: 'Fischauge (winkeltreu)', r: (t) => t, theta: (r) => r },
  equisolid: { label: 'Fischauge (flächentreu)', r: (t) => 2 * Math.sin(t / 2), theta: (r) => 2 * Math.asin(Math.min(1, r / 2)) },
  stereographic: { label: 'Fischauge (stereografisch)', r: (t) => 2 * Math.tan(t / 2), theta: (r) => 2 * Math.atan(r / 2) },
  rectilinear: { label: 'Normales Weitwinkel', r: (t) => Math.tan(t), theta: (r) => Math.atan(r) },
};
export const MODEL_IDS = Object.keys(MODELS);
export const MODEL_INDEX = Object.fromEntries(MODEL_IDS.map((id, i) => [id, i]));

/** Grenzen des Bildwinkels der Kamera (waagerecht, in Grad); normale Objektive enden vor 180°. */
export function fovLimits(model) {
  return model === 'rectilinear' ? { min: 60, max: 150 } : { min: 90, max: 260 };
}
export const STRETCH_MAX = 0.3; // darüber kippt die Streckung am Rand um (Ableitung < 0)
export const TILT_MAX = 45;

/** Kamera-Vorgaben; „Action-Kamera“ ist an einem GoPro-SuperView-Foto vermessen. */
export const PRESETS = {
  action: { label: 'Action-Kamera (GoPro SuperView u. ä.)', model: 'equidistant', fov: 120, stretch: 0.2, tilt: 0 },
  fisheye: { label: 'Fischauge 180°', model: 'equidistant', fov: 180, stretch: 0, tilt: 0 },
  wide: { label: 'Normales Weitwinkel', model: 'rectilinear', fov: 100, stretch: 0, tilt: 0 },
};
const { label: _label, ...ACTION } = PRESETS.action;
export const DEFAULTS = { preset: 'action', ...ACTION };

/** Gespeicherte Einstellungen prüfen; Unbrauchbares durch die Vorgabe ersetzen. */
export function sanitize(s) {
  if (!s || !MODELS[s.model]) return { ...DEFAULTS };
  const num = (v, min, max, fallback) => (Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : fallback);
  const { min, max } = fovLimits(s.model);
  return {
    preset: PRESETS[s.preset] ? s.preset : 'custom',
    model: s.model,
    fov: num(s.fov, min, max, DEFAULTS.fov),
    stretch: num(s.stretch, 0, STRETCH_MAX, 0),
    tilt: num(s.tilt, -TILT_MAX, TILT_MAX, 0),
  };
}

/**
 * Kamera beschreiben: Brennweite in Pixeln, sodass der linke und rechte Bildrand bei halbem
 * Bildwinkel liegen, dazu der größte Winkel nach oben/unten (für die Grenzen beim Schwenken).
 */
export function lens({ model, fov, stretch = 0, tilt = 0 }, width, height) {
  const m = MODELS[model] ?? MODELS.equidistant;
  const half = (fov / 2) * DEG;
  const f = width / 2 / m.r(half);
  return { model, f, width, height, stretch, tilt: tilt * DEG, halfH: half, halfV: m.theta(height / 2 / f) };
}

/** Streckung umkehren: entzerrte Koordinate X (−1…1, Rand bleibt Rand) → Koordinate im Foto. */
export function unstretch(X, s) {
  if (!s) return X;
  // X = x (1 − s x²) / (1 − s); Newton ab x = X, für |x| ≤ 1 und s ≤ 0,3 streng monoton
  let x = X;
  for (let i = 0; i < 6; i++) x -= (x - s * x ** 3 - X * (1 - s)) / (1 - 3 * s * x * x);
  return x;
}
export const stretchOf = (x, s) => (x * (1 - s * x * x)) / (1 - s);

/** Panini-Stärke: bis 70° normale Perspektive, ab 130° volle Panini (Senkrechte bleiben gerade). */
export const paniniStrength = (outFovDeg) => Math.min(1, Math.max(0, (outFovDeg - 70) / 60));

/** Waagerechte Bildschirmkoordinate am Rand bei Bildwinkel fov und Panini-Stärke d. */
export function paniniEdge(outFovDeg, d) {
  const h = (outFovDeg / 2) * DEG;
  return ((d + 1) / (d + Math.cos(h))) * Math.sin(h);
}

/** Bildschirmpunkt (Panini-Ebene) → Länge und Breite relativ zur Blickrichtung. */
export function paniniInverse(x, y, d) {
  const k = (x * x) / ((d + 1) * (d + 1));
  const dscr = k * k * d * d - (k + 1) * (k * d * d - 1);
  const clon = (-k * d + Math.sqrt(dscr)) / (k + 1);
  const s = (d + 1) / (d + clon);
  return { lon: Math.atan2(x, s * clon), lat: Math.atan2(y, s) };
}

/**
 * Blickrichtung (Einheitsvektor, y nach oben, z nach vorn) in Kamerakoordinaten: erst Neigen
 * (pitch) und Schwenken (yaw) in der waagrechten Welt, dann die Neigung der Kamera (tilt) ausgleichen.
 */
export function direction(lon, lat, yaw, pitch, tilt = 0) {
  let x = Math.cos(lat) * Math.sin(lon);
  let y = Math.sin(lat);
  let z = Math.cos(lat) * Math.cos(lon);
  [y, z] = [y * Math.cos(pitch) + z * Math.sin(pitch), -y * Math.sin(pitch) + z * Math.cos(pitch)];
  [x, z] = [x * Math.cos(yaw) + z * Math.sin(yaw), -x * Math.sin(yaw) + z * Math.cos(yaw)];
  [y, z] = [y * Math.cos(tilt) + z * Math.sin(tilt), -y * Math.sin(tilt) + z * Math.cos(tilt)];
  return [x, y, z];
}

/** Richtung (Kamerakoordinaten) → Pixel im Foto (null, wenn sie außerhalb des Fotos liegt). */
export function project(v, cam) {
  const m = MODELS[cam.model] ?? MODELS.equidistant;
  const len = Math.hypot(v[0], v[1]);
  const theta = Math.atan2(len, v[2]); // in Achsnähe genauer als acos
  if (cam.model === 'rectilinear' ? theta >= Math.PI / 2 - 1e-6 : theta > 3.1) return null;
  const r = cam.f * m.r(theta);
  const [dx, dy] = len > 1e-12 ? [v[0] / len, v[1] / len] : [0, 0];
  const X = (dx * r) / (cam.width / 2);
  if (Math.abs(X) > 1) return null;
  const u = cam.width / 2 + unstretch(X, cam.stretch) * (cam.width / 2);
  const w = cam.height / 2 - dy * r;
  return w < 0 || w > cam.height ? null : [u, w];
}

/** Ansicht in erlaubte Grenzen bringen: nicht weiter schwenken, als das Foto reicht. */
export function clampView(view, cam) {
  const maxFov = Math.min(150, (2 * cam.halfH) / DEG);
  const fov = Math.min(maxFov, Math.max(20, view.fov));
  const yawMax = Math.max(0, cam.halfH - (fov / 2) * DEG * 0.5);
  const pitchMax = Math.max(0, cam.halfV - (fov / 4) * DEG);
  const center = -cam.tilt; // Kamera nach unten geneigt: ihre Achse liegt unter dem Horizont
  return {
    fov,
    yaw: Math.min(yawMax, Math.max(-yawMax, view.yaw)),
    pitch: Math.min(center + pitchMax, Math.max(center - pitchMax, view.pitch)),
  };
}

/** Anfangsansicht: waagrecht geradeaus (bzw. so nah wie möglich), so weit wie möglich, höchstens 140°. */
export const startView = (cam) => clampView({ fov: Math.min(140, (2 * cam.halfH) / DEG), yaw: 0, pitch: 0 }, cam);

export const VERTEX = `
attribute vec2 pos;
varying vec2 p;
void main() { p = pos; gl_Position = vec4(pos, 0.0, 1.0); }`;

export const SHADER = `
precision highp float;
uniform sampler2D img;
uniform vec2 size;     // Foto in Pixeln
uniform float aspect;  // Höhe / Breite der Ansicht
uniform float edge;    // Panini-Koordinate am Rand
uniform float d;       // Panini-Stärke
uniform float f;       // Brennweite in Pixeln
uniform int model;     // Reihenfolge wie MODEL_IDS
uniform float stretch; // waagerechte Streckung der Kamera (0 … 0,3)
uniform float yaw;
uniform float pitch;
uniform float tilt;    // Neigung der Kamera (positiv = nach unten)
varying vec2 p;
void main() {
  float x = p.x * edge;
  float y = p.y * edge * aspect;
  float k = x * x / ((d + 1.0) * (d + 1.0));
  float dscr = k * k * d * d - (k + 1.0) * (k * d * d - 1.0);
  float clon = (-k * d + sqrt(dscr)) / (k + 1.0);
  float s = (d + 1.0) / (d + clon);
  float lon = atan(x, s * clon);
  float lat = atan(y, s);
  vec3 v = vec3(cos(lat) * sin(lon), sin(lat), cos(lat) * cos(lon));
  v = vec3(v.x, v.y * cos(pitch) + v.z * sin(pitch), -v.y * sin(pitch) + v.z * cos(pitch));
  v = vec3(v.x * cos(yaw) + v.z * sin(yaw), v.y, -v.x * sin(yaw) + v.z * cos(yaw));
  v = vec3(v.x, v.y * cos(tilt) + v.z * sin(tilt), -v.y * sin(tilt) + v.z * cos(tilt));
  float len = length(v.xy);
  float t = atan(len, v.z);
  float r;
  bool outside = t > 3.1;
  if (model == 0) r = t;
  else if (model == 1) r = 2.0 * sin(t * 0.5);
  else if (model == 2) r = 2.0 * tan(t * 0.5);
  else { outside = t > 1.5707; r = tan(min(t, 1.5707)); }
  vec2 dir = len > 1e-6 ? v.xy / len : vec2(0.0);
  float X = dir.x * r * f / (size.x * 0.5);
  outside = outside || abs(X) > 1.0;
  float xs = X;
  for (int i = 0; i < 6; i++) xs -= (xs - stretch * xs * xs * xs - X * (1.0 - stretch)) / (1.0 - 3.0 * stretch * xs * xs);
  vec2 uv = vec2(0.5 + xs * 0.5, 0.5 - dir.y * r * f / size.y);
  if (outside || uv.y < 0.0 || uv.y > 1.0) gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
  else gl_FragColor = texture2D(img, uv);
}`;
