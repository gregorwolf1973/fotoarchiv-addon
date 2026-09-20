<script>
  import { SvelteSet } from 'svelte/reactivity';
  import { thumbUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import Icon from './Icon.svelte';

  // items: Bilder ohne Ort. ondragmove(x, y) -> liegt der Punkt über der Karte? ondrop(ids, x, y)
  let { items, collapsed = false, ontoggle, ondragmove, ondrop, onopen } = $props();

  const GAP = 4;
  const LONG_PRESS = 350;
  const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeZone: 'UTC' });

  const selected = new SvelteSet();
  let grid = $state();
  let width = $state(0);
  let height = $state(0);
  let scrollTop = $state(0);
  let drag = $state(null); // { ids, item, x, y, over }

  const tile = $derived(width < 400 ? 76 : 96);
  const columns = $derived(Math.max(1, Math.floor((width - GAP) / (tile + GAP))));
  const rows = $derived(Math.ceil(items.length / columns));
  const firstRow = $derived(Math.max(0, Math.floor(scrollTop / (tile + GAP)) - 2));
  const lastRow = $derived(Math.min(rows, Math.ceil((scrollTop + height) / (tile + GAP)) + 2));
  const visible = $derived(items.slice(firstRow * columns, lastRow * columns).map((item, k) => ({ item, index: firstRow * columns + k })));

  // Auswahl von Bildern bereinigen, die inzwischen einen Ort haben
  $effect(() => {
    const ids = new Set(items.map((i) => i[0]));
    for (const id of [...selected]) if (!ids.has(id)) selected.delete(id);
  });

  // ── Ziehen: Maus sofort, Touch nach langem Drücken ──────────────
  let press = null;
  let suppressClick = false;
  let lastClicked = null; // Index des zuletzt angeklickten Bildes, Anker für Shift+Klick

  function pointerdown(e, item) {
    if (e.button !== 0) return;
    press = { x: e.clientX, y: e.clientY, item, pointerId: e.pointerId, target: e.currentTarget, touch: e.pointerType !== 'mouse' };
    if (press.touch) {
      const current = press;
      current.timer = setTimeout(() => begin(current, current.x, current.y), LONG_PRESS);
    }
  }

  function begin(start, x, y) {
    clearTimeout(start.timer);
    const id = start.item[0];
    const ids = selected.has(id) ? [...selected] : [id];
    drag = { ids, item: start.item, x, y, over: false };
    try {
      start.target.setPointerCapture(start.pointerId);
    } catch {
      /* ohne Capture kommen die Ereignisse trotzdem über window */
    }
    navigator.vibrate?.(15);
  }

  function pointermove(e) {
    if (drag) {
      drag.x = e.clientX;
      drag.y = e.clientY;
      drag.over = ondragmove(e.clientX, e.clientY);
      return;
    }
    if (!press) return;
    const distance = Math.hypot(e.clientX - press.x, e.clientY - press.y);
    if (press.touch && distance > 10) cancel();
    else if (!press.touch && distance > 6) begin(press, e.clientX, e.clientY);
  }

  function pointerup(e) {
    if (drag) {
      if (drag.over) ondrop(drag.ids, e.clientX, e.clientY);
      drag = null;
      ondragmove(-1, -1);
      suppressClick = true;
    }
    cancel();
  }

  function cancel() {
    if (press) clearTimeout(press.timer);
    press = null;
  }

  function click(e, item, index) {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (e.shiftKey && lastClicked !== null) {
      // Bereich vom letzten Klick bis hier, wie in der Galerie
      const [from, to] = lastClicked < index ? [lastClicked, index] : [index, lastClicked];
      for (let i = from; i <= to; i++) selected.add(items[i][0]);
      window.getSelection?.()?.removeAllRanges(); // Shift+Klick markiert sonst Text
    } else if (selected.has(item[0])) {
      selected.delete(item[0]);
    } else {
      selected.add(item[0]);
    }
    lastClicked = index;
  }

  // Während des Ziehens darf die Liste nicht scrollen (touchmove muss dafür nicht-passiv sein)
  $effect(() => {
    const block = (e) => drag && e.cancelable && e.preventDefault();
    window.addEventListener('touchmove', block, { passive: false });
    return () => window.removeEventListener('touchmove', block);
  });
</script>

<svelte:window onpointermove={pointermove} onpointerup={pointerup} onpointercancel={pointerup} />

<aside class="panel" class:collapsed>
  <header>
    <button class="toggle" onclick={ontoggle} title={collapsed ? 'Fenster öffnen' : 'Fenster schließen'}>
      <Icon name="marker" size={20} />
      <strong>Ohne Ort</strong>
      <span class="count">{formatNumber(items.length)}</span>
      <span class="grow"></span>
      <Icon name={collapsed ? 'left' : 'right'} size={20} />
    </button>
  </header>

  {#if !collapsed}
    {#if items.length}
      <div class="bar">
        {#if selected.size}
          <span>{formatNumber(selected.size)} ausgewählt</span>
          <button class="link" onclick={() => selected.clear()}>Aufheben</button>
        {:else}
          <span class="muted">Fotos auf die Karte ziehen. Klick wählt aus, Shift+Klick einen Bereich.</span>
        {/if}
        <span class="grow"></span>
        {#if selected.size < items.length}
          <button class="link" onclick={() => items.forEach((i) => selected.add(i[0]))}>Alle</button>
        {/if}
      </div>
      <div class="grid" bind:this={grid} bind:clientWidth={width} bind:clientHeight={height} onscroll={() => (scrollTop = grid.scrollTop)}>
        <div class="content" style:height="{rows * (tile + GAP)}px">
          {#each visible as { item, index } (item[0])}
            <button
              class="tile"
              class:selected={selected.has(item[0])}
              class:dragging={drag?.ids.includes(item[0])}
              style:width="{tile}px"
              style:height="{tile}px"
              style:left="{(index % columns) * (tile + GAP) + GAP}px"
              style:top="{Math.floor(index / columns) * (tile + GAP)}px"
              title={dateFormat.format(item[1] * 1000)}
              onpointerdown={(e) => pointerdown(e, item)}
              onclick={(e) => click(e, item, index)}
              ondblclick={() => onopen(items.map((i) => i[0]), item[0])}
              oncontextmenu={(e) => e.preventDefault()}
            >
              <img src={thumbUrl(item)} alt="" loading="lazy" draggable="false" />
              {#if selected.has(item[0])}<span class="check"><Icon name="checkCircle" size={22} /></span>{/if}
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <p class="done">Alle bearbeitbaren Fotos haben einen Aufnahmeort.</p>
    {/if}
  {/if}
</aside>

{#if drag}
  <div class="ghost" class:over={drag.over} style:left="{drag.x}px" style:top="{drag.y}px">
    <img src={thumbUrl(drag.item)} alt="" />
    {#if drag.ids.length > 1}<span class="badge">{drag.ids.length}</span>{/if}
  </div>
{/if}

<style>
  .panel {
    display: flex;
    flex-direction: column;
    width: 340px;
    min-height: 0;
    border-left: 1px solid var(--border);
    background: var(--surface);
  }
  .panel.collapsed {
    width: auto;
  }
  header {
    border-bottom: 1px solid var(--border);
  }
  .toggle {
    width: 100%;
    min-height: 48px;
    border: 0;
    border-radius: 0;
    background: transparent;
  }
  .count {
    padding: 0 8px;
    border-radius: 10px;
    background: var(--chip);
    font-size: 0.8rem;
  }
  @media (min-width: 720px) {
    /* eingeklappt als schmale Leiste am rechten Rand */
    .collapsed .toggle strong,
    .collapsed .toggle .count {
      display: none;
    }
  }
  .grow {
    flex: 1;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 40px;
    padding: 0 12px;
    font-size: 0.85rem;
  }
  .muted {
    color: var(--muted);
  }
  button.link {
    min-height: 28px;
    padding: 0 6px;
    border: 0;
    background: transparent;
    color: var(--accent);
  }
  .grid {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }
  .content {
    position: relative;
  }
  .tile {
    position: absolute;
    display: block;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 4px;
    overflow: hidden;
    background: var(--placeholder);
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }
  .tile img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    pointer-events: none;
  }
  .tile.selected {
    outline: 3px solid var(--accent);
    outline-offset: -3px;
  }
  .tile.dragging {
    opacity: 0.4;
  }
  .check {
    position: absolute;
    top: 3px;
    left: 3px;
    color: var(--accent);
    background: #fff;
    border-radius: 50%;
  }
  .done {
    padding: 16px;
    color: var(--muted);
  }
  .ghost {
    position: fixed;
    z-index: 90;
    width: 72px;
    height: 72px;
    margin: -36px 0 0 -36px;
    border: 3px solid #fff;
    border-radius: 8px;
    box-shadow: 0 6px 20px rgb(0 0 0 / 0.4);
    pointer-events: none;
    transform: rotate(-4deg);
    opacity: 0.85;
  }
  .ghost.over {
    border-color: var(--accent);
    opacity: 1;
  }
  .ghost img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 5px;
  }
  .badge {
    position: absolute;
    top: -10px;
    right: -10px;
    min-width: 22px;
    padding: 0 6px;
    border-radius: 11px;
    background: var(--accent);
    color: var(--on-accent);
    font-size: 0.8rem;
    font-weight: 600;
    line-height: 22px;
    text-align: center;
  }
  @media (max-width: 719px) {
    .panel {
      width: auto;
      height: 40vh;
      border-left: 0;
      border-top: 1px solid var(--border);
    }
    .panel.collapsed {
      height: auto;
    }
    .toggle > :global(svg:last-child) {
      transform: rotate(90deg); /* Fenster liegt unten: Pfeil nach unten/oben */
    }
  }
</style>
