<script>
  import { monthLabel, rowAt, yearMarks } from '../lib/layout.js';

  let { layout, scrollTop, viewport, width, onscroll } = $props();

  const INSET = 14; // Abstand oben/unten, damit Jahreszahlen nicht abgeschnitten werden

  let bar = $state();
  let barHeight = $state(0);
  let hoverY = $state(null);
  let dragging = $state(false);
  let recentlyScrolled = $state(false);

  const scrollable = $derived(Math.max(1, layout.height - viewport));
  const track = $derived(Math.max(1, barHeight - 2 * INSET));
  const markerY = $derived(INSET + Math.min(1, scrollTop / scrollable) * track);
  const marks = $derived(yearMarks(layout, viewport, track).map((m) => ({ ...m, pos: m.pos + INSET })));

  const offsetAt = (y) => Math.min(1, Math.max(0, (y - INSET) / track)) * scrollable;
  // Datum der ersten Bilder, die im sichtbaren Bereich wirklich zu sehen sind
  const labelAt = (offset) =>
    layout.rows.length ? monthLabel(layout.rows[rowAt(layout.rows, offset + Math.min(120, viewport / 4))].ts) : '';

  const bubble = $derived.by(() => {
    if (dragging) return { y: markerY, text: labelAt(scrollTop) };
    if (hoverY !== null) return { y: Math.min(Math.max(hoverY, INSET), INSET + track), text: labelAt(offsetAt(hoverY)) };
    if (recentlyScrolled) return { y: markerY, text: labelAt(scrollTop) };
    return null;
  });

  // Beim Scrollen kurz das aktuelle Datum zeigen
  let previous = 0;
  let timer;
  $effect(() => {
    if (Math.abs(scrollTop - previous) < 1) return;
    previous = scrollTop;
    recentlyScrolled = true;
    clearTimeout(timer);
    timer = setTimeout(() => (recentlyScrolled = false), 900);
  });

  const localY = (e) => e.clientY - bar.getBoundingClientRect().top;

  function down(e) {
    if (e.button !== 0) return;
    dragging = true;
    try {
      bar.setPointerCapture(e.pointerId);
    } catch {
      /* synthetische Ereignisse haben keinen echten Zeiger */
    }
    onscroll(offsetAt(localY(e)));
    e.preventDefault();
  }
  function move(e) {
    hoverY = localY(e);
    if (dragging) onscroll(offsetAt(hoverY));
  }
  function up(e) {
    dragging = false;
    if (bar.hasPointerCapture(e.pointerId)) bar.releasePointerCapture(e.pointerId);
    if (e.pointerType !== 'mouse') hoverY = null;
  }
  function keydown(e) {
    const step = { PageDown: viewport, PageUp: -viewport, Home: -Infinity, End: Infinity }[e.key];
    if (step === undefined) return;
    onscroll(Math.min(scrollable, Math.max(0, scrollTop + step)));
    e.preventDefault();
  }
</script>

{#if layout.height > viewport}
  <div
    class="timeline"
    class:dragging
    style:width="{width}px"
    bind:this={bar}
    bind:clientHeight={barHeight}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
    onpointerleave={() => !dragging && (hoverY = null)}
    onkeydown={keydown}
    role="scrollbar"
    aria-controls="gallery-scroller"
    aria-orientation="vertical"
    aria-valuemin="0"
    aria-valuemax="100"
    aria-valuenow={Math.round((scrollTop / scrollable) * 100)}
    tabindex="0"
  >
    <div class="rail"></div>
    {#each marks as mark (mark.year)}
      <span class="year" style:top="{mark.pos}px">{mark.year}</span>
    {/each}
    {#if hoverY !== null && !dragging}
      <div class="ghost" style:top="{Math.min(Math.max(hoverY, INSET), INSET + track)}px"></div>
    {/if}
    <div class="marker" style:top="{markerY}px"></div>
    {#if bubble}
      <div class="bubble" style:top="{bubble.y}px">{bubble.text}</div>
    {/if}
  </div>
{/if}

<style>
  .timeline {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    cursor: ns-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    background: var(--timeline-bg);
    outline: none;
  }
  .rail {
    position: absolute;
    top: 14px;
    bottom: 14px;
    right: 6px;
    width: 2px;
    border-radius: 1px;
    background: var(--border);
  }
  .year {
    position: absolute;
    right: 14px;
    transform: translateY(-50%);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    pointer-events: none;
  }
  .year::after {
    content: '';
    position: absolute;
    right: -9px;
    top: 50%;
    width: 6px;
    height: 1px;
    background: var(--muted);
  }
  .ghost,
  .marker {
    position: absolute;
    right: 0;
    width: 16px;
    height: 0;
    pointer-events: none;
  }
  .ghost {
    border-top: 1px dashed var(--muted);
  }
  .marker {
    border-top: 2px solid var(--accent);
    margin-top: -1px;
  }
  .marker::after {
    content: '';
    position: absolute;
    right: 2px;
    top: -6px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 3px var(--timeline-bg);
  }
  .dragging .marker::after {
    transform: scale(1.3);
  }
  .bubble {
    position: absolute;
    right: calc(100% + 6px);
    transform: translateY(-50%);
    padding: 5px 10px;
    border-radius: 14px;
    background: var(--accent);
    color: var(--on-accent);
    font-size: 13px;
    font-weight: 500;
    white-space: nowrap;
    pointer-events: none;
    box-shadow: 0 2px 8px rgb(0 0 0 / 0.25);
  }
  .timeline:focus-visible .rail {
    background: var(--accent);
  }
</style>
