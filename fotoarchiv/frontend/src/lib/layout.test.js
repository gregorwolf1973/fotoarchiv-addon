import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildLayout, rowAt, rowOfItem, yearMarks } from './layout.js';

const ts = (iso) => Date.parse(`${iso}Z`) / 1000;
const photo = (id, iso, w = 400, h = 300) => [id, ts(iso), w, h, 0, 1];

test('Zeilen füllen die Breite exakt, letzte Zeile des Tages bleibt ungestreckt', () => {
  const items = Array.from({ length: 7 }, (_, k) => photo(k, `2024-05-01T1${k}:00:00`));
  const { rows } = buildLayout(items, 1000, { rowHeight: 200, gap: 4, headerHeight: 40 });
  const photos = rows.filter((r) => r.type === 'photos');
  assert.equal(rows[0].type, 'header');
  for (const row of photos.slice(0, -1)) {
    const last = row.cells.at(-1);
    assert.equal(last.left + last.width, 1000);
  }
  assert.equal(photos.at(-1).height, 200);
  assert.deepEqual(photos.flatMap((r) => r.cells.map((c) => c.index)), [0, 1, 2, 3, 4, 5, 6]);
});

test('Neuer Tag beginnt mit Überschrift, Jahre werden gemerkt', () => {
  const items = [photo(1, '2024-01-02T10:00:00'), photo(2, '2024-01-01T10:00:00'), photo(3, '2023-12-31T23:59:59')];
  const layout = buildLayout(items, 800);
  assert.equal(layout.rows.filter((r) => r.type === 'header').length, 3);
  assert.deepEqual(layout.years.map((y) => y.year), [2024, 2023]);
  assert.ok(layout.years[1].top > 0);
});

test('Fehlende Maße gelten als quadratisch, Breite 0 ergibt leeres Layout', () => {
  const layout = buildLayout([[1, ts('2024-01-01T00:00:00'), 0, 0, 0, 1]], 500, { rowHeight: 100 });
  assert.equal(layout.rows[1].cells[0].width, 100);
  assert.equal(buildLayout([photo(1, '2024-01-01T00:00:00')], 0).rows.length, 0);
});

test('Suche nach Position und Bild', () => {
  const items = Array.from({ length: 50 }, (_, k) => photo(k, `2024-05-${String(28 - (k % 20)).padStart(2, '0')}T12:00:00`))
    .sort((a, b) => b[1] - a[1]);
  const { rows, height } = buildLayout(items, 600, { rowHeight: 150 });
  assert.equal(rowAt(rows, -10), 0);
  assert.equal(rows[rowAt(rows, height)].top, rows.at(-1).top);
  for (let index = 0; index < items.length; index++) {
    const row = rows[rowOfItem(rows, index)];
    assert.ok(row.cells.some((c) => c.index === index), `Bild ${index}`);
  }
});

test('Jahresmarken halten Mindestabstand', () => {
  const layout = { height: 10000, years: [{ year: 2024, top: 0 }, { year: 2023, top: 50 }, { year: 2022, top: 5000 }] };
  assert.deepEqual(yearMarks(layout, 1000, 900).map((m) => m.year), [2024, 2022]);
});
