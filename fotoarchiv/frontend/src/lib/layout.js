// Galerie-Layout: Bilder je Tag gruppiert, Zeilen im Blocksatz (wie Google Fotos).
// Ein Eintrag ist [id, ts, breite, höhe, video, rev]; ts = Ortszeit als Sekunden (UTC gerechnet).

const DAY = 86400;

const dayFormat = new Intl.DateTimeFormat('de-DE', {
  weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
});
const monthFormat = new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric', timeZone: 'UTC' });

export const dayLabel = (ts) => dayFormat.format(ts * 1000);
export const monthLabel = (ts) => monthFormat.format(ts * 1000);
const yearOf = (ts) => new Date(ts * 1000).getUTCFullYear();

function ratio(item) {
  const w = item[2];
  const h = item[3];
  if (!w || !h) return 1;
  return Math.min(Math.max(w / h, 0.25), 5); // extreme Panoramen begrenzen
}

function pushRow(rows, items, indices, top, height, width, gap, stretch) {
  const cells = [];
  let x = 0;
  indices.forEach((index, k) => {
    let w = Math.round(ratio(items[index]) * height);
    if (stretch && k === indices.length - 1) w = Math.max(1, width - x); // Rundung ausgleichen
    cells.push({ index, left: x, width: w });
    x += w + gap;
  });
  rows.push({ type: 'photos', top, height, cells, ts: items[indices[0]][1] });
}

/**
 * @returns {{rows: object[], height: number, years: {year: number, top: number}[]}}
 *   rows sind nach top sortiert: Tagesüberschriften und Bildzeilen.
 */
export function buildLayout(items, width, { rowHeight = 200, gap = 4, headerHeight = 48, groupGap = 12 } = {}) {
  const rows = [];
  const years = [];
  let y = 0;
  let i = 0;
  if (width <= 0) return { rows, height: 0, years };

  while (i < items.length) {
    const day = Math.floor(items[i][1] / DAY);
    const year = yearOf(items[i][1]);
    if (!years.length || years[years.length - 1].year !== year) years.push({ year, top: y });

    const header = { type: 'header', top: y, height: headerHeight, ts: items[i][1], first: i, last: i };
    rows.push(header);
    y += headerHeight;

    let indices = [];
    let sum = 0;
    for (; i < items.length && Math.floor(items[i][1] / DAY) === day; i++) {
      indices.push(i);
      sum += ratio(items[i]);
      if (sum * rowHeight + gap * (indices.length - 1) >= width) {
        const height = Math.max(1, Math.round((width - gap * (indices.length - 1)) / sum));
        pushRow(rows, items, indices, y, height, width, gap, true);
        y += height + gap;
        indices = [];
        sum = 0;
      }
    }
    header.last = i - 1;
    if (indices.length) {
      pushRow(rows, items, indices, y, rowHeight, width, gap, false);
      y += rowHeight + gap;
    }
    y += groupGap;
  }
  return { rows, height: y, years };
}

/** Index der letzten Zeile, die bei offset oder darüber beginnt. */
export function rowAt(rows, offset) {
  let lo = 0;
  let hi = rows.length - 1;
  let found = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].top <= offset) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

/** Zeile, die das Bild mit diesem Listenindex enthält. */
export function rowOfItem(rows, index) {
  const first = (row) => (row.type === 'photos' ? row.cells[0].index : row.first);
  let lo = 0;
  let hi = rows.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (first(rows[mid]) <= index) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  // Eine Überschrift teilt ihren Startindex mit der folgenden Bildzeile
  return found >= 0 && rows[found].type === 'header' ? found + 1 : found;
}

/** Jahreszahlen auf der Zeitleiste; zu dicht liegende werden ausgelassen. */
export function yearMarks(layout, viewport, barHeight, minGap = 18) {
  const scrollable = Math.max(1, layout.height - viewport);
  const marks = [];
  let last = -Infinity;
  for (const { year, top } of layout.years) {
    const pos = Math.min(1, top / scrollable) * barHeight;
    if (pos - last >= minGap && pos <= barHeight - 8) {
      marks.push({ year, pos });
      last = pos;
    }
  }
  return marks;
}
