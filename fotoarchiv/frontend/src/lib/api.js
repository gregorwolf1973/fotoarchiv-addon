// Alle Pfade relativ, damit die Oberfläche hinter dem Ingress-Präfix funktioniert.

// Internetzugang: CSRF-Token der Sitzung für alle ändernden Anfragen; 401 meldet die Abmeldung an die App
export const auth = { csrf: null, onUnauthorized: () => {} };

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && auth.csrf) {
    options = { ...options, headers: { ...(options.headers || {}), 'X-CSRF-Token': auth.csrf } };
  }
  const response = await fetch(path, options);
  // Eine Sicherheitsabfrage von Cloudflare (WAF-Regel, Bot-Schutz) lässt sich nur beim Aufruf einer
  // ganzen Seite lösen, nicht bei einer Anfrage im Hintergrund – sonst käme nur "Forbidden"
  if (response.headers.get('cf-mitigated') === 'challenge') {
    throw new Error(
      'Cloudflare hat die Anfrage mit einer Sicherheitsabfrage abgefangen. Eine WAF-Regel oder der Bot-Schutz ' +
        `trifft diesen Pfad (${path.split('?')[0]}); er muss dort ausgenommen werden.`,
    );
  }
  if (response.status === 401 && !path.startsWith('api/auth/')) auth.onUnauthorized();
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
  session: () => request('api/auth/session'),
  login: (username, password) => request('api/auth/login', send('POST', { username, password })),
  logout: () => request('api/auth/logout', { method: 'POST' }),
  changePassword: (current, next) => request('api/auth/password', send('POST', { current, new: next })),
  state: () => request('api/state'),
  index: (filters, trash, extra) => request(`api/assets?${filterQuery(filters, trash, extra)}`),
  largest: (kind, minMb, order) =>
    request(`api/largest?${new URLSearchParams({ kind, min_mb: String(minMb), order })}`),
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
  knownFiles: (files) => request('api/upload/known', send('POST', { files })),
  requestDelete: (ids, reason) => request('api/delete-requests', send('POST', { ids, reason })),
  dismissDeleteRequests: (ids) => request('api/delete-requests/dismiss', send('POST', { ids })),
  dismissConvertErrors: () => request('api/convert/dismiss', { method: 'POST' }),
  faceStatus: () => request('api/faces/status'),
  people: () => request('api/people'),
  groupFaces: (id) => request(`api/groups/${id}/faces`),
  nameGroup: (id, name) => request(`api/groups/${id}/name`, send('POST', { name })),
  hideGroup: (id) => request(`api/groups/${id}/hide`, { method: 'POST' }),
  personFaces: (id) => request(`api/persons/${id}/faces`),
  renamePerson: (id, name) => request(`api/persons/${id}/rename`, send('POST', { name })),
  mergePerson: (id, targetId) => request(`api/persons/${id}/merge`, send('POST', { target_id: targetId })),
  deletePerson: (id) => request(`api/persons/${id}/delete`, { method: 'POST' }),
  assetFaces: (id) => request(`api/assets/${id}/faces`),
  assignFace: (id, name) => request(`api/faces/${id}/assign`, send('POST', { name })),
  removeFace: (id) => request(`api/faces/${id}/remove`, { method: 'POST' }),
  duplicates: () => request('api/duplicates'),
  resolveDuplicates: (groups, transfer) => request('api/duplicates/resolve', send('POST', { groups, transfer })),
  ignoreDuplicates: (ids) => request('api/duplicates/ignore', send('POST', { ids })),
  admin: {
    access: () => request('api/admin/access'),
    users: () => request('api/admin/users'),
    createUser: (user) => request('api/admin/users', send('POST', user)),
    updateUser: (id, changes) => request(`api/admin/users/${id}`, send('PATCH', changes)),
    deleteUser: (id) => request(`api/admin/users/${id}`, { method: 'DELETE' }),
    sessions: () => request('api/admin/sessions'),
    revokeSession: (id) => request(`api/admin/sessions/${id}`, { method: 'DELETE' }),
    locks: () => request('api/admin/locks'),
    unlock: (key) => request('api/admin/locks/unlock', send('POST', { key })),
    log: (event) => request(`api/admin/log?limit=300${event ? `&event=${event}` : ''}`),
    clearLog: () => request('api/admin/log', { method: 'DELETE' }),
    crowdsec: () => request('api/admin/crowdsec'),
    installCrowdsec: () => request('api/admin/crowdsec/install', { method: 'POST' }),
  },
  importStatus: () => request('api/import'),
  startImport: (mode, deep = false) => request('api/import', send('POST', { mode, deep })),
  cancelImport: () => request('api/import/cancel', { method: 'POST' }),
};

// Kennung der Datenbank aus api/state: Bild-URLs werden lange gecacht, nach einem Neuaufbau ändern sie sich
export const cache = { instance: '' };

// item = [id, ts, w, h, video, rev]
export const cropUrl = (faceId) => `api/faces/${faceId}/crop?i=${cache.instance}`;
export const thumbUrl = (item, small = false) =>
  `api/assets/${item[0]}/thumb?r=${item[5]}&i=${cache.instance}${small ? '&size=small' : ''}`;
export const previewUrl = (item) => `api/assets/${item[0]}/preview?r=${item[5]}&i=${cache.instance}`;
export const originalUrl = (item, download = false) =>
  `api/assets/${item[0]}/original?r=${item[5]}&i=${cache.instance}${download ? '&download=true' : ''}`;

// Große Dateien in Stücken: Cloudflare lässt im kostenlosen Tarif nur 100 MB je Anfrage durch,
// und am Handy reißt die Verbindung öfter ab – dann geht es mit dem fehlenden Stück weiter
const CHUNK = 32 * 1024 * 1024;
const RETRIES = 6;
const RETRY_STATUS = new Set([0, 408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]);

const CANCELLED = { status: 'cancelled', message: 'abgebrochen' };

/** Upload mit Fortschritt; löst immer auf, Fehler stehen im Ergebnis. signal: AbortSignal zum Abbrechen. */
export function upload(file, onprogress, signal) {
  return file.size > CHUNK ? uploadChunked(file, onprogress, signal) : uploadWhole(file, onprogress, signal);
}

function put(url, body, onprogress, signal) {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve({ status: -1, json: null, text: 'abgebrochen' });
    const xhr = new XMLHttpRequest();
    signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.onabort = () => resolve({ status: -1, json: null, text: 'abgebrochen' });
    xhr.open('PUT', url);
    if (auth.csrf) xhr.setRequestHeader('X-CSRF-Token', auth.csrf);
    xhr.upload.onprogress = (e) => e.lengthComputable && onprogress(e.loaded);
    xhr.onload = () => {
      let json = null;
      try {
        json = JSON.parse(xhr.responseText);
      } catch {
        /* keine JSON-Antwort, z. B. Fehlerseite des Proxys */
      }
      if (xhr.status === 401) auth.onUnauthorized();
      resolve({ status: xhr.status, json, text: xhr.statusText });
    };
    xhr.onerror = () => resolve({ status: 0, json: null, text: 'Netzwerkfehler' });
    xhr.send(body);
  });
}

const failed = (r) => ({
  status: 'error',
  message: r.json?.detail || (r.status === 413 ? 'Datei zu groß für den Proxy' : r.text || 'Netzwerkfehler'),
});

async function uploadWhole(file, onprogress, signal) {
  const query = new URLSearchParams({ name: file.name, mtime: String(file.lastModified || '') });
  const r = await put(`api/upload?${query}`, file, (loaded) => onprogress(loaded / file.size), signal);
  if (r.status === -1) return CANCELLED;
  return r.json && !r.json.detail ? r.json : failed(r);
}

function uploadId() {
  // crypto.randomUUID gibt es nur über HTTPS; Home Assistant läuft im Heimnetz oft über http
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function uploadChunked(file, onprogress, signal) {
  const id = uploadId();
  let offset = 0;
  let failures = 0;
  while (offset < file.size) {
    const end = Math.min(offset + CHUNK, file.size);
    const query = new URLSearchParams({
      upload_id: id, name: file.name, offset: String(offset), total: String(file.size), mtime: String(file.lastModified || ''),
    });
    const start = offset;
    const r = await put(`api/upload/chunk?${query}`, file.slice(start, end), (loaded) => onprogress((start + loaded) / file.size), signal);
    if (r.status === -1 || signal?.aborted) return CANCELLED; // Teildatei räumt der Server nach einem Tag weg
    if (r.status === 202) {
      offset = r.json.received;
      failures = 0;
    } else if (r.status === 409 && typeof r.json?.received === 'number') {
      offset = r.json.received; // Server nennt den Stand: dort weitermachen
      if (++failures > RETRIES) return failed(r);
    } else if (RETRY_STATUS.has(r.status) && !r.json?.status) {
      // Funkloch oder Proxy: ob das Stück ankam, klärt der nächste Versuch (409 mit dem Stand)
      if (++failures > RETRIES) return failed(r);
      await new Promise((resolve) => setTimeout(resolve, 1500 * failures));
    } else {
      return r.json && !r.json.detail ? r.json : failed(r); // letztes Stück: Ergebnis des Imports
    }
  }
  return { status: 'error', message: 'Upload unvollständig' };
}

export const SUPPORTED = /\.(jpe?g|png|gif|webp|tiff?|hei[cf]|avif|mp4|m4v|mov|3gp|mkv|webm|avi|m2?ts)$/i;
