// Service Worker für die installierte App. Er nimmt nur Fotos aus dem Teilen-Menü (Android) entgegen
// und legt sie für die Seite bereit. Kein Offline-Cache: Das Archiv lebt vom Server.

const INBOX = 'share-inbox';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method === 'POST' && url.pathname.endsWith('/share-target')) {
    event.respondWith(receive(event.request));
  }
});

async function receive(request) {
  const scope = self.registration.scope;
  let count = 0;
  try {
    const data = await request.formData();
    const cache = await caches.open(INBOX);
    for (const file of data.getAll('files')) {
      if (!(file instanceof File)) continue;
      const headers = {
        'content-type': file.type || 'application/octet-stream',
        'x-name': encodeURIComponent(file.name),
        'x-modified': String(file.lastModified || ''),
      };
      await cache.put(new URL(`share-inbox/${Date.now()}-${count++}`, scope).href, new Response(file, { headers }));
    }
  } catch {
    /* Die Seite meldet dann einfach nichts Neues */
  }
  return Response.redirect(new URL(`./?shared=${count}`, scope).href, 303);
}
