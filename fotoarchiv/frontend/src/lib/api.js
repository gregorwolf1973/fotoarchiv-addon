// Alle Pfade relativ, damit die Oberfläche hinter dem Ingress-Präfix funktioniert.

async function request(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(body?.detail || response.statusText);
  return body;
}

export const api = {
  state: () => request('api/state'),
  index: () => request('api/assets'),
  asset: (id) => request(`api/assets/${id}`),
  importStatus: () => request('api/import'),
  startImport: (mode) =>
    request('api/import', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mode }),
    }),
};

// item = [id, ts, w, h, video, rev]
export const thumbUrl = (item) => `api/assets/${item[0]}/thumb?r=${item[5]}`;
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
