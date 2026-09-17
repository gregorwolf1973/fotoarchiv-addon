<script>
  import { untrack } from 'svelte';
  import { buildLayout, dayLabel, monthLabel, rowAt, rowOfItem, ZOOM_LEVELS } from '../lib/layout.js';
  import { thumbUrl } from '../lib/api.js';
  import Icon from './Icon.svelte';
  import Timeline from './Timeline.svelte';

  // selected: SvelteSet mit Bild-IDs. Ist etwas ausgewählt, wählt ein Klick aus statt zu öffnen.
  // zoom: Index in ZOOM_LEVELS; onzoom(schritt) ändert ihn (+1 größer, -1 kleiner)
  let { items, selected, zoom, onopen, ontoggle, ontoggleday, onzoom } = $props();

  const LONG_PRESS = 450;

  let scroller = $state();
  let width = $state(0);
  let viewport = $state(0);
  let scrollTop = $state(0);

  const selecting = $derived(selected.size > 0);
  const compact = $derived(width < 640);
  const pad = $derived(compact ? 4 : 16);
  const timelineWidth = $derived(compact ? 44 : 64);
  const level = $derived(ZOOM_LEVELS[zoom] ?? ZOOM_LEVELS[2]);
  // Kleine Vorschaubilder (160 px) nur, wo sie bei dieser Pixeldichte noch scharf sind
  const small = $derived(level.rowHeight * (globalThis.devicePixelRatio || 1) <= 180);
  const layout = $derived(
    buildLayout(items, Math.max(0, width - pad - timelineWidth), {
      rowHeight: level.rowHeight,
      gap: level.rowHeight <= 120 ? 2 : 4,
      headerHeight: level.group === 'month' ? 44 : compact ? 40 : 52,
      group: level.group,
    }),
  );

  // Nur sichtbare Zeilen rendern (plus eine Bildschirmhöhe Puffer)
  const visible = $derived.by(() => {
    const { rows } = layout;
    const headers = [];
    const cells = [];
    if (!rows.length) return { headers, cells };
    const end = scrollTop + viewport * 2;
    for (let k = rowAt(rows, scrollTop - viewport); k < rows.length && rows[k].top <= end; k++) {
      const row = rows[k];
      if (row.type === 'header') headers.push(row);
      else for (const cell of row.cells) cells.push({ ...cell, top: row.top, height: row.height, item: items[cell.index] });
    }
    return { headers, cells };
  });

  const daySelected = (header) => {
    for (let i = header.first; i <= header.last; i++) if (!selected.has(items[i][0])) return false;
    return true;
  };

  // Beim Ändern der Breite oder neuen Bildern das oberste sichtbare Bild festhalten
  let anchor = 0;
  function onscroll() {
    scrollTop = scroller.scrollTop;
    const row = layout.rows[rowAt(layout.rows, scrollTop)];
    if (row) anchor = row.type === 'photos' ? row.cells[0].index : row.first;
  }
  $effect(() => {
    const { rows } = layout;
    untrack(() => {
      if (!scroller) return;
      if (rows.length && scroller.scrollTop > 0) {
        const k = rowOfItem(rows, Math.min(anchor, items.length - 1));
        // Erste Zeile einer Gruppe: Überschrift mit anzeigen
        if (k >= 0) scroller.scrollTop = rows[k - 1]?.type === 'header' ? rows[k - 1].top : rows[k].top;
      }
      scrollTop = scroller.scrollTop; // der Browser begrenzt die Position ohne Scroll-Ereignis
    });
  });

  // Langes Drücken auf Touch-Geräten startet die Auswahl
  let pressTimer;
  let pressed = false;
  function pointerdown(e, index) {
    if (e.pointerType === 'mouse') return;
    pressed = false;
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => {
      pressed = true;
      navigator.vibrate?.(20);
      ontoggle(index, e);
    }, LONG_PRESS);
  }
  const cancelPress = () => clearTimeout(pressTimer);

  function click(e, index) {
    if (pressed) {
      pressed = false;
      return;
    }
    if (selecting || e.shiftKey || e.ctrlKey || e.metaKey) ontoggle(index, e);
    else onopen(index);
  }

  // Zoomen: Strg + Mausrad (auch Zwei-Finger-Geste am Touchpad) und Zusammenziehen am Touchscreen
  $effect(() => {
    if (!scroller) return;
    let wheel = 0;
    let pinch = null;
    const distance = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);

    function onwheel(e) {
      if (!e.ctrlKey) return;
      e.preventDefault(); // sonst zoomt der Browser die ganze Seite
      wheel += e.deltaY;
      if (Math.abs(wheel) >= 60) {
        onzoom(wheel < 0 ? 1 : -1);
        wheel = 0;
      }
    }
    function ontouchstart(e) {
      if (e.touches.length === 2) pinch = distance(e.touches);
    }
    function ontouchmove(e) {
      if (e.touches.length !== 2 || pinch === null) return;
      e.preventDefault();
      const ratio = distance(e.touches) / pinch;
      if (ratio > 1.3 || ratio < 0.77) {
        onzoom(ratio > 1 ? 1 : -1);
        pinch = distance(e.touches);
      }
    }
    const ontouchend = (e) => e.touches.length < 2 && (pinch = null);

    scroller.addEventListener('wheel', onwheel, { passive: false });
    scroller.addEventListener('touchstart', ontouchstart, { passive: true });
    scroller.addEventListener('touchmove', ontouchmove, { passive: false });
    scroller.addEventListener('touchend', ontouchend);
    return () => {
      scroller.removeEventListener('wheel', onwheel);
      scroller.removeEventListener('touchstart', ontouchstart);
      scroller.removeEventListener('touchmove', ontouchmove);
      scroller.removeEventListener('touchend', ontouchend);
    };
  });

  function broken(event) {
    event.currentTarget.parentElement.classList.add('broken');
  }
</script>

<div class="gallery" class:selecting>
  <div class="scroller" id="gallery-scroller" bind:this={scroller} bind:clientWidth={width} bind:clientHeight={viewport} {onscroll}>
    <div class="content" style:height="{layout.height}px">
      {#each visible.headers as header (header.top)}
        {@const all = selecting && daySelected(header)}
        <div class="day" style:top="{header.top}px" style:left="{pad}px" style:height="{header.height}px">
          <button class="daycheck" class:on={all} onclick={() => ontoggleday(header.first, header.last, !all)} title={header.group === 'month' ? 'Ganzen Monat auswählen' : 'Ganzen Tag auswählen'}>
            <Icon name="checkCircle" size={20} />
          </button>
          <h2>{header.group === 'month' ? monthLabel(header.ts) : dayLabel(header.ts)}</h2>
        </div>
      {/each}
      {#each visible.cells as cell (cell.item[0])}
        {@const isSelected = selected.has(cell.item[0])}
        <div
          class="cell"
          class:selected={isSelected}
          style:top="{cell.top}px"
          style:left="{pad + cell.left}px"
          style:width="{cell.width}px"
          style:height="{cell.height}px"
        >
          <button
            class="open"
            onclick={(e) => click(e, cell.index)}
            onpointerdown={(e) => pointerdown(e, cell.index)}
            onpointerup={cancelPress}
            onpointermove={cancelPress}
            onpointercancel={cancelPress}
            oncontextmenu={(e) => e.pointerType !== 'mouse' && e.preventDefault()}
            aria-label={isSelected ? 'Ausgewählt' : 'Öffnen'}
          >
            <img src={thumbUrl(cell.item, small)} alt="" loading="lazy" decoding="async" draggable="false" onerror={broken} />
          </button>
          {#if cell.item[4]}<span class="badge"><Icon name="play" size={compact ? 14 : 18} /></span>{/if}
          <button class="check" onclick={(e) => ontoggle(cell.index, e)} title="Auswählen" aria-pressed={isSelected}>
            <Icon name="checkCircle" size={level.rowHeight <= 120 ? 18 : 24} />
          </button>
        </div>
      {/each}
    </div>
  </div>
  <div class="zoom" role="group" aria-label="Vorschaugröße">
    <button class="icon small" disabled={zoom <= 0} onclick={() => onzoom(-1)} title="Kleiner – mehr Fotos (Strg + Mausrad)">
      <Icon name="minus" size={20} />
    </button>
    <button class="icon small" disabled={zoom >= ZOOM_LEVELS.length - 1} onclick={() => onzoom(1)} title="Größer – weniger Fotos (Strg + Mausrad)">
      <Icon name="plus" size={20} />
    </button>
  </div>
  <Timeline {layout} {scrollTop} {viewport} width={timelineWidth} onscroll={(offset) => (scroller.scrollTop = offset)} />
</div>

<style>
  .gallery {
    position: relative;
    flex: 1;
    min-height: 0;
  }
  .scroller {
    position: absolute;
    inset: 0;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: none; /* die Zeitleiste ersetzt den Scrollbalken */
    overscroll-behavior: contain;
  }
  .scroller::-webkit-scrollbar {
    display: none;
  }
  .content {
    position: relative;
  }
  .day {
    position: absolute;
    display: flex;
    align-items: flex-end;
    gap: 6px;
    padding-bottom: 6px;
    box-sizing: border-box;
    white-space: nowrap;
  }
  .day h2 {
    margin: 0 0 2px;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text);
  }
  .daycheck {
    display: none;
    min-height: 0;
    width: 28px;
    height: 28px;
    padding: 0;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: var(--muted);
  }
  .daycheck.on {
    color: var(--accent);
  }
  .day:hover .daycheck,
  .selecting .daycheck {
    display: inline-flex;
  }
  .cell {
    position: absolute;
    overflow: hidden;
    background: var(--placeholder);
  }
  .open {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    -webkit-touch-callout: none;
    user-select: none;
  }
  .open img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.12s ease, filter 0.15s ease;
  }
  .cell:hover .open img {
    filter: brightness(0.88);
  }
  .open:focus-visible {
    outline: 3px solid var(--accent);
    outline-offset: -3px;
  }
  .cell:global(.broken) img {
    visibility: hidden;
  }
  .selected {
    background: color-mix(in srgb, var(--accent) 25%, var(--bg));
  }
  .selected .open img {
    transform: scale(0.86);
    border-radius: 4px;
  }
  .badge {
    position: absolute;
    right: 6px;
    top: 6px;
    color: #fff;
    background: rgb(0 0 0 / 0.45);
    border-radius: 50%;
    padding: 3px;
    pointer-events: none;
  }
  .zoom {
    position: absolute;
    left: 16px;
    bottom: 16px;
    z-index: 5;
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: 20px;
    background: var(--surface);
    box-shadow: 0 2px 10px rgb(0 0 0 / 0.25);
  }
  .zoom button {
    width: 36px;
    height: 36px;
  }
  .check {
    position: absolute;
    left: 2px;
    top: 2px;
    display: none;
    min-height: 0;
    width: 36px;
    height: 36px;
    padding: 0;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: rgb(255 255 255 / 0.85);
    filter: drop-shadow(0 1px 2px rgb(0 0 0 / 0.6));
  }
  .check:hover:not(:disabled) {
    background: transparent;
    color: #fff;
  }
  .cell:hover .check,
  .selecting .check {
    display: inline-flex;
  }
  .selected .check {
    color: var(--accent);
    filter: none;
  }
  @media (hover: none) {
    .cell:hover .check {
      display: none;
    }
    .selecting .check {
      display: inline-flex;
    }
  }
  @media (max-width: 639px) {
    .day h2 {
      font-size: 0.85rem;
    }
  }
</style>
