const number = new Intl.NumberFormat('de-DE');
const dateTime = new Intl.DateTimeFormat('de-DE', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
  timeZone: 'UTC',
});

export const formatNumber = (n) => number.format(n);

export function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const k = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** k).toLocaleString('de-DE', { maximumFractionDigits: k > 1 ? 1 : 0 })} ${units[k]}`;
}

export function formatDuration(seconds) {
  if (!seconds) return '';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`;
}

/** taken_at ist Ortszeit ohne Zone; als UTC formatieren, damit nichts verschoben wird. */
export const formatTaken = (takenAt) => dateTime.format(new Date(`${takenAt}Z`));

export const DATE_SOURCES = {
  exif: '',
  filename: 'aus dem Dateinamen',
  mtime: 'Dateidatum – unsicher',
};
