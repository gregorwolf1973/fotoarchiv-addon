// Installierbare App für den Internetzugang: Service Worker, geteilte Dateien aus dem Teilen-Menü.
// Über Home Assistant (Ingress) bleibt das aus – dort ist das Fotoarchiv eine Seite in Home Assistant.

const INBOX = 'share-inbox'; // gleicher Name wie in public/sw.js

export function registerServiceWorker() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
}

/** Läuft die Seite als installierte App (Startbildschirm)? */
export const standalone = () =>
  window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true;

export const isIos = () =>
  /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

/** Wurde die Seite aus dem Teilen-Menü geöffnet? Dann liegen die Dateien im Cache des Service Workers. */
export const openedFromShare = () => new URLSearchParams(location.search).has('shared');

export async function takeShared() {
  history.replaceState(null, '', location.pathname); // beim Neuladen nicht noch einmal
  if (!('caches' in window)) return [];
  const cache = await caches.open(INBOX);
  const files = [];
  for (const request of await cache.keys()) {
    const response = await cache.match(request);
    if (response) {
      const name = decodeURIComponent(response.headers.get('x-name') || 'geteilt');
      const modified = Number(response.headers.get('x-modified')) || Date.now();
      const blob = await response.blob();
      files.push(new File([blob], name, { type: blob.type, lastModified: modified }));
    }
    await cache.delete(request);
  }
  return files;
}
