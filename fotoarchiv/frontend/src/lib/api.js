// Alle Pfade relativ, damit die Oberfläche hinter dem Ingress-Präfix funktioniert.

async function request(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    if (!response.ok) throw new Error(response.statusText || `Fehler ${response.status}`);
  }
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : detail || response.statusText);
  }
  return body;
}

const send = (method, body) => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
});

/** Filter -> Query-String; Listen werden als wiederholte Parameter übergeben. */
export function filterQuery({ tags = [], persons = [], start = '', end = '', q = '' } = {}, trash = false, extra = {}) {
  const params = new URLSearchParams();
  for (const t of tags) params.append('tag', t.id);
  for (const p of persons) params.append('person', p.id);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (q) params.set('q', q);
  if (trash) params.set('trash', 'true');
  for (const [key, value] of Object.entries(extra)) params.set(key, String(value));
  return params.toString();
}

export const api = {
  state: () => request('api/state'),
  index: (filters, trash, extra) => request(`api/assets?${filterQuery(filters, trash, extra)}`),
  geo: (filters) => request(`api/geo?${filterQuery(filters)}`),
  labels: () => request('api/labels'),
  asset: (id) => request(`api/assets/${id}`),
  update: (id, changes) => request(`api/assets/${id}`, send('PATCH', changes)),
  rotate: (id, degrees) => request(`api/assets/${id}/rotate`, send('POST', { degrees })),
  remove: (id) => request(`api/assets/${id}`, { method: 'DELETE' }),
  restore: (id) => request(`api/assets/${id}/restore`, { method: 'POST' }),
  batch: (body) => request('api/batch', send('POST', body)),
  tasks: () => request('api/tasks'),
  emptyTrash: () => request('api/trash/empty', { method: 'POST' }),
  removeMissing: () => request('api/library/remove-missing', { method: 'POST' }),
  importStatus: () => request('api/import'),
  startImport: (mode) => request('api/import', send('POST', { mode })),
};

// item = [id, ts, w, h, video, rev]
export const thumbUrl = (item, small = false) => `api/assets/${item[0]}/thumb?r=${item[5]}${small ? '&size=small' : ''}`;
export const previewUrl = (item) => `api/assets/${item[0]}/preview?r=${item[5]}`;
export const originalUrl = (item, download = false) =>
  `api/assets/${item[0]}/original?r=${item[5]}${download ? '&download=true' : ''}`;

/** Upload mit Fortschritt; löst immer auf, Fehler stehen im Ergebnis. */
export function upload(file, onprogress) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const query = new URLSearchParams({ name: file.name, mtime: String(file.lastModified || '') });
    xhr.open('PUT', `api/upload?${query}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onprogress(e.loaded / e.total);
    xhr.onload = () => {
      let body;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = { status: 'error', message: xhr.status === 413 ? 'Datei zu groß für den Proxy' : xhr.statusText };
      }
      if (body.detail) body = { status: 'error', message: body.detail };
      resolve(body);
    };
    xhr.onerror = () => resolve({ status: 'error', message: 'Netzwerkfehler' });
    xhr.send(file);
  });
}

export const SUPPORTED = /\.(jpe?g|png|gif|webp|tiff?|hei[cf]|avif|mp4|m4v|mov|3gp|mkv|webm|avi|m2?ts)$/i;
