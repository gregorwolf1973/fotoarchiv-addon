<script>
  import { onMount } from 'svelte';
  import { originalUrl, previewUrl } from '../lib/api.js';
  import { clampView, MAX_SCALE, RESET, zoomAt } from '../lib/zoom.js';
  import Icon from './Icon.svelte';

  // Ganzes Foto zu einem Gesicht, um vor dem Zuordnen genau hinzusehen. Das Gesicht ist markiert.
  // Zoomen mit Mausrad, zwei Fingern, Doppeltippen/-klick oder +/-; verschieben mit Maus bzw. Finger;
  // ungezoomt wischen oder ←/→ blättert durch die Gesichter.
  // faces: [{ id, asset_id, rev, x, y, w, h, mime, size, taken_ts }] (x … h: 0..1 im angezeigten Bild)
  // heading: Snippet für die Kopfzeile; actions(face): Knöpfe für das gezeigte Gesicht
  let { faces, index = 0, heading, actions, onclose } = $props();

  // Browser zeigen HEIC/TIFF nicht an; sehr große Originale lohnen das Nachladen nicht (wie in der Einzelansicht)
  const HIRES_TYPES = /^image\/(jpeg|png|webp|gif|avif)$/;
  const HIRES_MAX = 60 * 1024 * 1024;
  const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeZone: 'UTC' });

  // Startgesicht bewusst nur einmal übernehmen, danach blättert die Lupe selbst
  // svelte-ignore state_referenced_locally
  let i = $state(Math.max(0, Math.min(index, faces.length - 1)));
  const face = $derived(faces[i]);
  const item = $derived([face.asset_id, face.taken_ts, 0, 0, 0, face.rev]);
  const key = $derived(`${face.asset_id}-${face.rev}`);

  let stage = $state(null);
  let stageWidth = $state(0);
  let stageHeight = $state(0);
  let natural = $state({ width: 0, height: 0 });
  let loadedKey = $state(null);
  let hiresFor = $state(null);
  let hiresReady = $state(null);
  let view = $state(RESET);

  const frame = $derived.by(() => {
    if (!natural.width || !stageWidth || loadedKey !== key) return null;
    const scale = Math.min(stageWidth / natural.width, stageHeight / natural.height);
    const width = natural.width * scale;
    const height = natural.height * scale;
    return { left: (stageWidth - width) / 2, top: (stageHeight - height) / 2, width, height };
  });
  const stageSize = $derived({ width: stageWidth, height: stageHeight });
  const zoomed = $derived(view.scale > 1.01);
  const transform = $derived(`translate(${view.x}px, ${view.y}px) scale(${view.scale})`);
  const hiresAllowed = $derived(HIRES_TYPES.test(face.mime ?? '') && (face.size ?? Infinity) <= HIRES_MAX);

  $effect(() => {
    key; // anderes Foto: ungezoomt beginnen
    view = RESET;
  });
  $effect(() => {
    if (zoomed && hiresAllowed) hiresFor = key;
  });

  function zoomTo(scale, x, y) {
    if (frame) view = zoomAt(view, scale, x, y, frame, stageSize);
  }
  const toggleZoom = (x, y) => (zoomed ? (view = RESET) : zoomTo(2.5, x, y));

  /** So weit hineinzoomen, dass das Gesicht gut ein Drittel der Höhe füllt, und es in die Mitte rücken. */
  function zoomToFace() {
    if (!frame) return;
    const scale = Math.min(MAX_SCALE, Math.max(1, (stageHeight * 0.35) / (face.h * frame.height)));
    const cx = frame.left + (face.x + face.w / 2) * frame.width;
    const cy = frame.top + (face.y + face.h / 2) * frame.height;
    view = clampView({ scale, x: stageWidth / 2 - cx * scale, y: stageHeight / 2 - cy * scale }, frame, stageSize);
  }

  function go(step) {
    const next = i + step;
    if (next >= 0 && next < faces.length) i = next;
  }

  function local(e) {
    const rect = stage.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  onMount(() => {
    // Mausrad und Touchpad-Geste; muss preventDefault können, darum nicht passiv
    const wheel = (e) => {
      if (!frame) return;
      e.preventDefault();
      const [x, y] = local(e);
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomTo(view.scale * Math.exp(-delta * 0.002), x, y);
    };
    // Safari (iOS) zoomt sonst die ganze Seite statt des Fotos
    const blockPageZoom = (e) => e.preventDefault();
    stage.addEventListener('wheel', wheel, { passive: false });
    for (const type of ['gesturestart', 'gesturechange']) document.addEventListener(type, blockPageZoom);
    return () => {
      stage.removeEventListener('wheel', wheel);
      for (const type of ['gesturestart', 'gesturechange']) document.removeEventListener(type, blockPageZoom);
    };
  });

  function keydown(e) {
    if (e.target.closest?.('input, textarea')) return;
    if (e.key === 'Escape') onclose();
    else if (e.key === 'ArrowLeft' && !zoomed) go(-1);
    else if (e.key === 'ArrowRight' && !zoomed) go(1);
    else if (e.key === '+' || e.key === '=') zoomTo(view.scale * 1.5, stageWidth / 2, stageHeight / 2);
    else if (e.key === '-') zoomTo(view.scale / 1.5, stageWidth / 2, stageHeight / 2);
    else if (e.key === '0') view = RESET;
    else return;
    e.preventDefault();
  }

  // Gesten wie in der Einzelansicht: zwei Finger zoomen, ein Finger bzw. die Maus verschiebt das gezoomte Bild,
  // ungezoomt wischt man zum nächsten Gesicht, Doppeltippen zoomt hinein und wieder heraus
  const pointers = new Map();
  let gesture = null;
  let lastTap = null;
  const spread = () => {
    const [a, b] = [...pointers.values()];
    return [Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  };

  function pointerdown(e) {
    if (e.target.closest('button')) return;
    const [x, y] = local(e);
    pointers.set(e.pointerId, [x, y]);
    if (pointers.size === 2 && frame) {
      gesture = { type: 'pinch', dist: spread()[0], scale: view.scale };
    } else if (pointers.size === 1) {
      gesture = { type: zoomed ? 'pan' : 'swipe', sx: x, sy: y, x, y, touch: e.pointerType !== 'mouse' };
      try {
        stage.setPointerCapture(e.pointerId);
      } catch {
        /* Zeiger schon wieder weg */
      }
    }
  }

  function pointermove(e) {
    if (!pointers.has(e.pointerId)) return;
    const [x, y] = local(e);
    pointers.set(e.pointerId, [x, y]);
    if (gesture?.type === 'pinch' && pointers.size === 2) {
      const [dist, cx, cy] = spread();
      zoomTo((gesture.scale * dist) / gesture.dist, cx, cy);
    } else if (gesture?.type === 'pan' && frame) {
      view = clampView({ scale: view.scale, x: view.x + x - gesture.x, y: view.y + y - gesture.y }, frame, stageSize);
      gesture.x = x;
      gesture.y = y;
      gesture.moved = true;
    }
  }

  function pointerup(e) {
    if (!pointers.has(e.pointerId)) return;
    const [x, y] = local(e);
    pointers.delete(e.pointerId);
    const done = gesture;
    if (pointers.size) {
      const [rest] = pointers.values();
      gesture = zoomed ? { type: 'pan', x: rest[0], y: rest[1], moved: true } : null;
      return;
    }
    gesture = null;
    if (!done || done.type === 'pinch' || e.type === 'pointercancel') return;
    const dx = x - done.sx;
    const dy = y - done.sy;
    if (done.type === 'swipe' && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
      go(dx < 0 ? 1 : -1);
      return;
    }
    // Doppeltippen am Touchscreen; mit der Maus übernimmt das dblclick
    if (done.touch && !done.moved && Math.hypot(dx, dy) < 10) {
      const now = performance.now();
      if (lastTap && now - lastTap.time < 300 && Math.hypot(x - lastTap.x, y - lastTap.y) < 30) {
        toggleZoom(x, y);
        lastTap = null;
      } else {
        lastTap = { time: now, x, y };
      }
    }
  }

  function dblclick(e) {
    if (e.target.closest('button')) return;
    const [x, y] = local(e);
    toggleZoom(x, y);
  }
</script>

<svelte:window onkeydown={keydown} />

<div class="lupe" role="dialog" aria-modal="true" aria-label="Ganzes Foto">
  <header>
    <div class="title">
      {@render heading?.()}
      <span class="meta">{dateFormat.format(face.taken_ts * 1000)}{#if faces.length > 1} · {i + 1} von {faces.length}{/if}</span>
    </div>
    <button class="icon" onclick={zoomToFace} disabled={!frame} title="Zum Gesicht zoomen"><Icon name="face" /></button>
    <button class="icon" onclick={() => (view = RESET)} disabled={!zoomed} title="Ganzes Foto (0)"><Icon name="images" /></button>
    <button class="icon" onclick={onclose} title="Schließen (Esc)"><Icon name="close" /></button>
  </header>

  <div
    class="stage"
    class:zoomed
    bind:this={stage}
    bind:clientWidth={stageWidth}
    bind:clientHeight={stageHeight}
    onpointerdown={pointerdown}
    onpointermove={pointermove}
    onpointerup={pointerup}
    onpointercancel={pointerup}
    ondblclick={dblclick}
    role="presentation"
  >
    {#key key}
      <div class="layer" style:transform>
        <img
          src={previewUrl(item)}
          alt=""
          draggable="false"
          onload={(e) => {
            natural = { width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight };
            loadedKey = key;
          }}
        />
        {#if hiresFor === key}
          <!-- Beim Hineinzoomen das Original darüberlegen, sobald es geladen ist -->
          <img class="hires" class:ready={hiresReady === key} src={originalUrl(item)} alt="" draggable="false"
            onload={() => (hiresReady = key)} />
        {/if}
        {#if frame}
          <span
            class="mark"
            style:left="{frame.left + face.x * frame.width}px"
            style:top="{frame.top + face.y * frame.height}px"
            style:width="{face.w * frame.width}px"
            style:height="{face.h * frame.height}px"
            style:border-width="{2 / view.scale}px"
          ></span>
        {/if}
      </div>
    {/key}
    {#if faces.length > 1}
      <button class="nav prev" onclick={() => go(-1)} disabled={i === 0} title="Vorheriges Gesicht (←)"><Icon name="left" /></button>
      <button class="nav next" onclick={() => go(1)} disabled={i === faces.length - 1} title="Nächstes Gesicht (→)"><Icon name="right" /></button>
    {/if}
  </div>

  {#if actions}
    <footer>{@render actions(face)}</footer>
  {/if}
</div>

<style>
  .lupe {
    position: fixed;
    inset: 0;
    z-index: 80; /* über den Dialogen */
    display: flex;
    flex-direction: column;
    background: #000;
    color: #fff;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgb(0 0 0 / 0.85);
  }
  footer {
    flex-wrap: wrap;
    justify-content: center;
    padding-bottom: max(8px, env(safe-area-inset-bottom));
  }
  .title {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 10px;
  }
  .meta {
    color: rgb(255 255 255 / 0.7);
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }
  header .icon {
    color: #fff;
  }
  .stage {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow: hidden;
    touch-action: none; /* alle Gesten übernimmt die Seite */
  }
  .stage.zoomed {
    cursor: grab;
  }
  .stage.zoomed:active {
    cursor: grabbing;
  }
  .layer {
    position: absolute;
    inset: 0;
    transform-origin: 0 0;
    will-change: transform;
  }
  .layer img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
    user-select: none;
    -webkit-user-drag: none;
  }
  .hires {
    opacity: 0;
    transition: opacity 0.2s;
  }
  .hires.ready {
    opacity: 1;
  }
  .mark {
    position: absolute;
    box-sizing: border-box;
    border: 2px solid #ffd54f;
    border-radius: 6px;
    box-shadow: 0 0 0 1px rgb(0 0 0 / 0.5);
    pointer-events: none;
  }
  .nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 44px;
    min-height: 0;
    padding: 0;
    border-radius: 50%;
    background: rgb(0 0 0 / 0.45);
    color: #fff;
  }
  .nav:disabled {
    opacity: 0.25;
  }
  .prev {
    left: 8px;
  }
  .next {
    right: 8px;
  }
</style>
