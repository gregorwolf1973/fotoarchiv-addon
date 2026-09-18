// Zoom der Einzelansicht. Das Bild liegt per object-fit: contain in der Bühne; gezoomt wird mit
// transform: translate(x, y) scale(scale) und transform-origin 0 0.
// frame = { left, top, width, height }: sichtbare Bildfläche bei Maßstab 1; stage = { width, height }.

export const MIN_SCALE = 1;
export const MAX_SCALE = 8;
export const RESET = Object.freeze({ scale: 1, x: 0, y: 0 });

const limit = (scale) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

/** Verschiebung begrenzen: kein Rand neben dem Bild, solange es größer als die Bühne ist, sonst mittig. */
export function clampView(view, frame, stage) {
  const scale = limit(view.scale);
  const axis = (offset, start, size, full) => {
    const scaled = size * scale;
    if (scaled <= full) return (full - scaled) / 2 - start * scale + 0; // + 0 macht aus -0 eine 0
    return Math.min(-start * scale, Math.max(full - (start + size) * scale, offset)) + 0;
  };
  return {
    scale,
    x: axis(view.x, frame.left, frame.width, stage.width),
    y: axis(view.y, frame.top, frame.height, stage.height),
  };
}

/** Auf einen neuen Maßstab zoomen; der Punkt (px, py) der Bühne bleibt unter dem Finger bzw. Mauszeiger. */
export function zoomAt(view, scale, px, py, frame, stage) {
  const next = limit(scale);
  return clampView(
    {
      scale: next,
      x: px - ((px - view.x) / view.scale) * next,
      y: py - ((py - view.y) / view.scale) * next,
    },
    frame,
    stage,
  );
}
