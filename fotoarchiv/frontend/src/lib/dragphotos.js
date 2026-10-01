// Fotos aus der Galerie per Drag & Drop in einen Favoritenordner ziehen.
// Eigener Datentyp: Der Upload-Bereich reagiert nur auf "Files" und bleibt so unbeteiligt.
export const PHOTO_IDS = 'application/x-fotoarchiv-ids';

// Ziehen nur mit Maus/Touchpad; am Touchscreen startet langes Drücken die Auswahl
export const canDrag = () => globalThis.matchMedia?.('(hover: hover) and (pointer: fine)').matches ?? false;

export const isPhotoDrag = (e) => e.dataTransfer?.types?.includes(PHOTO_IDS) ?? false;

export function readPhotoIds(e) {
  try {
    const ids = JSON.parse(e.dataTransfer.getData(PHOTO_IDS) || '[]');
    return Array.isArray(ids) ? ids.filter(Number.isInteger) : [];
  } catch {
    return [];
  }
}

export function startPhotoDrag(e, ids) {
  e.dataTransfer.setData(PHOTO_IDS, JSON.stringify(ids));
  e.dataTransfer.effectAllowed = 'link';
  if (ids.length > 1) {
    // Statt eines einzelnen Vorschaubilds anzeigen, wie viele Fotos mitkommen
    const ghost = document.createElement('div');
    ghost.textContent = `${ids.length} Fotos`;
    ghost.style.cssText =
      'position:fixed;top:-100px;left:0;padding:6px 12px;border-radius:14px;background:#03a9f4;color:#fff;font:500 14px system-ui';
    document.body.append(ghost);
    e.dataTransfer.setDragImage(ghost, 10, 10);
    setTimeout(() => ghost.remove());
  }
}
