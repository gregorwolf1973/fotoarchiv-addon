// Alle Pfade relativ, damit die Oberfläche hinter dem Ingress-Präfix funktioniert.

// Internetzugang: CSRF-Token der Sitzung für alle ändernden Anfragen; 401 meldet die Abmeldung an die App
export const auth = { csrf: null, onUnauthorized: () => {} };

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && auth.csrf) {
    options = { ...options, headers: { ...(options.headers || {}), 'X-CSRF-Token': auth.csrf } };
  }
  const response = await fetch(path, options);
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
  state: () => request('api/state'),
  index: (filters, trash, extra) => request(`api/assets?${filterQuery(filters, trash, extra)}`),
  largest: (kind, minMb) => request(`api/largest?${new URLSearchParams({ kind, min_mb: String(minMb) })}`),
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

/** Upload mit Fortschritt; löst immer auf, Fehler stehen im Ergebnis. */
export function upload(file, onprogress) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const query = new URLSearchParams({ name: file.name, mtime: String(file.lastModified || '') });
    xhr.open('PUT', `api/upload?${query}`);
    if (auth.csrf) xhr.setRequestHeader('X-CSRF-Token', auth.csrf);
    xhr.upload.onprogress = (e) => e.lengthComputable && onprogress(e.loaded / e.total);
    xhr.onload = () => {
      let body;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = { status: 'error', message: xhr.status === 413 ? 'Datei zu groß für den Proxy' : xhr.statusText };
      }
      if (xhr.status === 401) auth.onUnauthorized();
      if (body.detail) body = { status: 'error', message: body.detail };
      resolve(body);
    };
    xhr.onerror = () => resolve({ status: 'error', message: 'Netzwerkfehler' });
    xhr.send(file);
  });
}

export const SUPPORTED = /\.(jpe?g|png|gif|webp|tiff?|hei[cf]|avif|mp4|m4v|mov|3gp|mkv|webm|avi|m2?ts)$/i;
