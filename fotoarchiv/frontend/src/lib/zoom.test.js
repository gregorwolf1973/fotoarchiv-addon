import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clampView, MAX_SCALE, RESET, zoomAt } from './zoom.js';

// Querformat 800×400 in einer Bühne 1000×1000: mittig mit 300 px Rand oben und unten
const stage = { width: 1000, height: 1000 };
const frame = { left: 0, top: 300, width: 1000, height: 400 };
const at = (view, x, y) => [view.x + view.scale * x, view.y + view.scale * y]; // Bühnenpunkt nach dem Zoom

test('Maßstab 1 bleibt unverschoben', () => {
  assert.deepEqual(clampView(RESET, frame, stage), { scale: 1, x: 0, y: 0 });
  assert.deepEqual(clampView({ scale: 1, x: 250, y: -80 }, frame, stage), { scale: 1, x: 0, y: 0 });
});

test('Der Punkt unter dem Finger bleibt stehen', () => {
  const view = zoomAt(RESET, 2, 400, 500, frame, stage);
  assert.equal(view.scale, 2);
  const [x, y] = at(view, 400, 500);
  assert.ok(Math.abs(x - 400) < 1e-9 && Math.abs(y - 500) < 1e-9);
});

test('Kein Rand neben dem Bild, solange es größer als die Bühne ist', () => {
  const view = clampView({ scale: 3, x: 500, y: 5000 }, frame, stage);
  assert.equal(view.x, 0); // linke Bildkante an der Bühnenkante
  assert.equal(view.y, -900); // obere Bildkante (300 × 3) an der Bühnenkante
  const far = clampView({ scale: 3, x: -99999, y: -99999 }, frame, stage);
  assert.equal(far.x + 3 * 1000, 1000); // rechte Kante bündig
  assert.equal(far.y + 3 * 700, 1000); // untere Kante bündig
});

test('Kleiner als die Bühne: mittig in dieser Richtung', () => {
  // Maßstab 2: Bildhöhe 800 < 1000 → vertikal mittig
  const view = clampView({ scale: 2, x: 0, y: 12345 }, frame, stage);
  assert.equal(view.y + 2 * 300, 100);
});

test('Maßstab wird begrenzt', () => {
  assert.equal(zoomAt(RESET, 100, 500, 500, frame, stage).scale, MAX_SCALE);
  assert.deepEqual(zoomAt({ scale: 2, x: -300, y: -500 }, 0.2, 500, 500, frame, stage), { scale: 1, x: 0, y: 0 });
});
