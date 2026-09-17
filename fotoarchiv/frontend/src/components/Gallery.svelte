<script>
  import { untrack } from 'svelte';
  import { buildLayout, dayLabel, rowAt, rowOfItem } from '../lib/layout.js';
  import { thumbUrl } from '../lib/api.js';
  import Icon from './Icon.svelte';
  import Timeline from './Timeline.svelte';

  let { items, onopen } = $props();

  let scroller = $state();
  let width = $state(0);
  let viewport = $state(0);
  let scrollTop = $state(0);

  const compact = $derived(width < 640);
  const pad = $derived(compact ? 4 : 16);
  const timelineWidth = $derived(compact ? 44 : 64);
  const layout = $derived(
    buildLayout(items, Math.max(0, width - pad - timelineWidth), {
      rowHeight: compact ? 110 : 200,
      gap: compact ? 2 : 4,
      headerHeight: compact ? 40 : 52,
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
      if (!scroller || !rows.length || scroller.scrollTop === 0) return;
      const k = rowOfItem(rows, Math.min(anchor, items.length - 1));
      if (k >= 0) scroller.scrollTop = rows[k].top;
    });
  });

  function scrollTo(offset) {
    scroller.scrollTop = offset;
  }

  function broken(event) {
    event.currentTarget.parentElement.classList.add('broken');
  }
</script>

<div class="gallery">
  <div class="scroller" id="gallery-scroller" bind:this={scroller} bind:clientWidth={width} bind:clientHeight={viewport} {onscroll}>
    <div class="content" style:height="{layout.height}px">
      {#each visible.headers as header (header.top)}
        <h2 class="day" style:top="{header.top}px" style:left="{pad}px" style:height="{header.height}px">
          {dayLabel(header.ts)}
        </h2>
      {/each}
      {#each visible.cells as cell (cell.item[0])}
        <button
          class="cell"
          style:top="{cell.top}px"
          style:left="{pad + cell.left}px"
          style:width="{cell.width}px"
          style:height="{cell.height}px"
          onclick={() => onopen(cell.index)}
        >
          <img src={thumbUrl(cell.item)} alt="" loading="lazy" decoding="async" draggable="false" onerror={broken} />
          {#if cell.item[4]}<span class="badge"><Icon name="play" size={compact ? 14 : 18} /></span>{/if}
        </button>
      {/each}
    </div>
  </div>
  <Timeline {layout} {scrollTop} {viewport} width={timelineWidth} onscroll={scrollTo} />
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
    margin: 0;
    display: flex;
    align-items: flex-end;
    padding-bottom: 8px;
    box-sizing: border-box;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
  }
  .cell {
    position: absolute;
    display: block;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: var(--placeholder);
    cursor: pointer;
    overflow: hidden;
  }
  .cell img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.15s ease, filter 0.15s ease;
  }
  .cell:hover img {
    filter: brightness(0.88);
  }
  .cell:focus-visible {
    outline: 3px solid var(--accent);
    outline-offset: -3px;
  }
  .cell:global(.broken) img {
    visibility: hidden;
  }
  .badge {
    position: absolute;
    right: 6px;
    top: 6px;
    color: #fff;
    background: rgb(0 0 0 / 0.45);
    border-radius: 50%;
    padding: 3px;
  }
  @media (max-width: 639px) {
    .day {
      font-size: 0.85rem;
      padding-bottom: 6px;
    }
  }
</style>
