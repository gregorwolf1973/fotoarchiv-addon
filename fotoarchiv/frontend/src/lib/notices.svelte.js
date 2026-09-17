// Kurze Meldungen unten in der Mitte, optional mit Aktion (z. B. "Rückgängig").

let nextId = 1;
export const notices = $state([]);

export function dismiss(id) {
  const index = notices.findIndex((n) => n.id === id);
  if (index >= 0) notices.splice(index, 1);
}

export function notify(text, { kind = 'info', action = null, actionLabel = '', timeout = 5000 } = {}) {
  const id = nextId++;
  notices.push({ id, text, kind, action, actionLabel });
  if (timeout) setTimeout(() => dismiss(id), timeout);
  return id;
}

export const notifyError = (error) => notify(error?.message ?? String(error), { kind: 'error', timeout: 8000 });
