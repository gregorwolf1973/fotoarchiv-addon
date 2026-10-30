import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  clampView, DEFAULTS, direction, lens, MODEL_IDS, MODELS, paniniEdge, paniniInverse, paniniStrength, project, sanitize, startView,
  stretchOf, unstretch,
} from './weitwinkel.js';

const DEG = Math.PI / 180;
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} ≠ ${b}`);

test('Die Mitte der Ansicht zeigt die Mitte des Fotos', () => {
  for (const model of MODEL_IDS) {
    const cam = lens({ model, fov: 120 }, 1708, 956);
    const [u, v] = project(direction(0, 0, 0, 0), cam);
    near(u, 854);
    near(v, 478);
  }
});

test('Bei halbem Bildwinkel liegt der Blick genau am Bildrand', () => {
  for (const model of MODEL_IDS) {
    const cam = lens({ model, fov: 120 }, 1000, 600);
    const [u, v] = project(direction(60 * DEG - 1e-9, 0, 0, 0), cam);
    near(u, 1000, 1e-4);
    near(v, 300);
    const [left] = project(direction(-60 * DEG + 1e-9, 0, 0, 0), cam);
    near(left, 0, 1e-4);
  }
});

test('Linsenmodelle sind umkehrbar', () => {
  for (const id of MODEL_IDS) {
    for (const t of [0.1, 0.5, 1.0, 1.4]) near(MODELS[id].theta(MODELS[id].r(t)), t, 1e-9);
  }
});

test('Ohne Panini ist die Ansicht eine normale Perspektive', () => {
  const { lon, lat } = paniniInverse(0.7, -0.3, 0);
  near(lon, Math.atan(0.7));
  near(lat, Math.atan(-0.3 / Math.hypot(1, 0.7)));
});

test('Am Bildschirmrand liegt der halbe Bildwinkel der Ansicht', () => {
  for (const fov of [60, 100, 140]) {
    const d = paniniStrength(fov);
    near(paniniInverse(paniniEdge(fov, d), 0, d).lon, (fov / 2) * DEG);
  }
});

test('Panini-Stärke wächst mit dem Bildwinkel', () => {
  assert.equal(paniniStrength(60), 0);
  assert.equal(paniniStrength(100), 0.5);
  assert.equal(paniniStrength(150), 1);
});

test('Schwenken nach rechts zeigt die rechte Bildhälfte, nach oben die obere', () => {
  const cam = lens({ model: 'equidistant', fov: 180 }, 1708, 956);
  const [u] = project(direction(0, 0, 30 * DEG, 0), cam);
  assert.ok(u > 854);
  const [, v] = project(direction(0, 0, 0, 20 * DEG), cam);
  assert.ok(v < 478);
});

test('Außerhalb des Fotos gibt es keinen Bildpunkt', () => {
  const cam = lens({ model: 'equidistant', fov: 120 }, 1000, 600);
  assert.equal(project(direction(80 * DEG, 0, 0, 0), cam), null);
  assert.equal(project([0, 0, -1], lens({ model: 'rectilinear', fov: 100 }, 1000, 600)), null);
});

test('Die Ansicht bleibt in den Grenzen des Fotos', () => {
  const cam = lens({ model: 'equidistant', fov: 180 }, 1708, 956);
  const start = startView(cam);
  assert.deepEqual(start, { fov: 140, yaw: 0, pitch: 0 });
  const wild = clampView({ fov: 500, yaw: 9, pitch: -9 }, cam);
  assert.equal(wild.fov, 150);
  assert.ok(wild.yaw <= cam.halfH && wild.yaw >= 0);
  assert.ok(wild.pitch >= -cam.halfV && wild.pitch <= 0);
  assert.equal(clampView({ fov: 1, yaw: 0, pitch: 0 }, cam).fov, 20);
  // schmales Objektiv: höchstens so weit wie das Foto
  assert.equal(clampView({ fov: 140, yaw: 0, pitch: 0 }, lens({ model: 'rectilinear', fov: 90 }, 1000, 600)).fov, 90);
});

test('Streckung: Rand bleibt Rand, Umkehrung stimmt', () => {
  for (const s of [0, 0.1, 0.2, 0.3]) {
    near(stretchOf(1, s), 1);
    near(stretchOf(-1, s), -1);
    for (const x of [-1, -0.7, -0.2, 0, 0.3, 0.9, 1]) near(unstretch(stretchOf(x, s), s), x, 1e-9);
  }
  // In der Mitte ist das Foto gestaucht: entzerrt liegt ein mittiger Punkt weiter außen
  assert.ok(stretchOf(0.3, 0.2) > 0.3);
});

test('Mit Streckung liegt der Rand weiter bei halbem Bildwinkel', () => {
  const cam = lens({ model: 'equidistant', fov: 120, stretch: 0.2 }, 1000, 600);
  const [u] = project(direction(60 * DEG - 1e-9, 0, 0, 0), cam);
  near(u, 1000, 1e-3);
  const [mid] = project(direction(20 * DEG, 0, 0, 0), cam);
  const [plain] = project(direction(20 * DEG, 0, 0, 0), lens({ model: 'equidistant', fov: 120 }, 1000, 600));
  assert.ok(mid < plain); // gestauchte Mitte: im Foto näher an der Bildmitte
});

test('Geneigte Kamera: Blick um die Neigung nach unten trifft die Bildmitte', () => {
  const cam = lens({ model: 'equidistant', fov: 120, tilt: 12 }, 1000, 600);
  const [u, v] = project(direction(0, 0, 0, -12 * DEG, cam.tilt), cam);
  near(u, 500);
  near(v, 300);
  // waagrechter Blick liegt im Foto oberhalb der Mitte
  assert.ok(project(direction(0, 0, 0, 0, cam.tilt), cam)[1] < 300);
  // Grenzen um die Kameraachse herum
  assert.ok(clampView({ fov: 90, yaw: 0, pitch: -1 }, cam).pitch < clampView({ fov: 90, yaw: 0, pitch: -1 }, lens({ model: 'equidistant', fov: 120 }, 1000, 600)).pitch);
});

test('Gespeicherte Einstellungen werden geprüft', () => {
  assert.deepEqual(sanitize(null), DEFAULTS);
  assert.deepEqual(sanitize({ model: 'kaputt' }), DEFAULTS);
  const s = sanitize({ preset: 'x', model: 'rectilinear', fov: 999, stretch: 2, tilt: 'a' });
  assert.deepEqual(s, { preset: 'custom', model: 'rectilinear', fov: 150, stretch: 0.3, tilt: 0 });
});
