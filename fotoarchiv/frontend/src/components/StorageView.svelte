<script>
  import { SvelteSet } from 'svelte/reactivity';
  import { api, thumbUrl } from '../lib/api.js';
  import { formatBytes, formatDuration, formatNumber } from '../lib/format.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // Die größten Dateien zuerst, zum Aufräumen des Speicherplatzes.
  // onopen(list, id): Einzelansicht mit dieser Liste; onbatch(body, undo): Mehrfachaktion im Hintergrund
  // onconvert(ids, danach): Umwandeln mit Rückfrage; null = nicht erlaubt
  let { revision, canEdit = true, onopen, onbatch, onconvert = null } = $props();

  const KINDS = [
    ['all', 'Alle'],
    ['video', 'Videos'],
    ['image', 'Fotos'],
    ['damaged', 'Beschädigt'],
  ];
  const SIZES = [0, 10, 50, 100, 500, 1000];

  let kind = $state('all');
  let minMb = $state(0);
  let data = $state.raw(null);
  const selected = new SvelteSet();
  let lastIndex = null;

  // Eintrag: [id, ts, w, h, video, rev, size, name, duration]; die ersten sechs wie in der Galerie
  const items = $derived(data?.items ?? []);
  const largest = $derived(items[0]?.[6] || 1);
  const selectedBytes = $derived(items.reduce((sum, item) => sum + (selected.has(item[0]) ? item[6] : 0), 0));

  $effect(() => {
    revision; // nach dem Löschen neu laden
    const request = api.largest(kind, minMb);
    let cancelled = false;
    request.then((next) => {
      if (cancelled) return;
      data = next;
      const ids = new Set(next.items.map((item) => item[0]));
      for (const id of [...selected]) if (!ids.has(id)) selected.delete(id);
    }, notifyError);
    return () => (cancelled = true);
  });

  function toggle(index, event) {
    const id = items[index][0];
    if (event.shiftKey && lastIndex !== null) {
      const [a, b] = lastIndex < index ? [lastIndex, index] : [index, lastIndex];
      for (let i = a; i <= b; i++) selected.add(items[i][0]);
    } else if (selected.has(id)) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
    lastIndex = index;
  }

  function trash() {
    const ids = [...selected];
    onbatch({ ids, action: 'delete' }, () => onbatch({ ids, action: 'restore' }));
    selected.clear();
    lastIndex = null;
  }

  const date = (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { dateStyle: 'medium', timeZone: 'UTC' });
  const details = (item) =>
    [date(item[1]), item[4] && item[8] ? formatDuration(item[8]) : '', item[2] && item[3] ? `${item[2]} × ${item[3]}` : '']
      .filter(Boolean)
      .join(' · ');
</script>

<div class="storage">
  <div class="controls">
    <div class="segmented" role="group" aria-label="Art">
      {#each KINDS as [value, label] (value)}
        <button class:active={kind === value} onclick={() => ((kind = value), (lastIndex = null))}>{label}</button>
      {/each}
    </div>
    <label>
      Größe
      <select bind:value={minMb} onchange={() => (lastIndex = null)}>
        {#each SIZES as size (size)}
          <option value={size}>{size ? `ab ${size >= 1000 ? `${size / 1000} GB` : `${size} MB`}` : 'alle'}</option>
        {/each}
      </select>
    </label>
    {#if kind === 'damaged'}
      <p class="hint">
        Dateien, aus denen sich kein Vorschaubild erzeugen ließ – meist abgebrochen kopiert oder hochgeladen. Gibt es das
        Original noch, diese Einträge löschen und das Original neu importieren.
      </p>
    {/if}
    {#if data}
      <span class="sum">{formatNumber(data.count)} Dateien · zusammen <strong>{formatBytes(data.bytes)}</strong></span>
    {/if}
  </div>

  {#if selected.size}
    <div class="selbar">
      <strong>{formatNumber(selected.size)} ausgewählt · {formatBytes(selectedBytes)}</strong>
      <span class="grow"></span>
      <button onclick={() => (selected.clear(), (lastIndex = null))}>Aufheben</button>
      {#if onconvert}
        <button onclick={() => onconvert([...selected], () => (selected.clear(), (lastIndex = null)))}
          title="HEIC → JPEG, nicht abspielbare Videos → MP4"><Icon name="convert" size={18} /> Umwandeln</button>
      {/if}
      <button class="danger" onclick={trash}><Icon name="delete" size={18} /> In den Papierkorb</button>
    </div>
  {/if}

  <ul class="list">
    {#each items as item, index (item[0])}
      <li class:on={selected.has(item[0])}>
        {#if canEdit}
          <button class="check" onclick={(e) => toggle(index, e)} title="Auswählen (Shift + Klick wählt einen Bereich)"
            aria-pressed={selected.has(item[0])}>
            {#if selected.has(item[0])}<Icon name="checkCircle" size={22} />{:else}<span class="ring"></span>{/if}
          </button>
        {/if}
        <button class="open" onclick={() => onopen(items, item[0])} title="Öffnen">
          <img src={thumbUrl(item, true)} alt="" loading="lazy" />
          {#if item[4]}<span class="play"><Icon name="play" size={16} /></span>{/if}
        </button>
        <div class="meta">
          <span class="name" title={item[7]}>{item[7]}</span>
          <small>{details(item)}</small>
          <span class="bar"><span style:width="{Math.max(1, (item[6] / largest) * 100)}%"></span></span>
        </div>
        <strong class="size">{formatBytes(item[6])}</strong>
      </li>
    {:else}
      {#if data}<li class="empty">Keine Dateien in dieser Auswahl.</li>{/if}
    {/each}
  </ul>
  {#if data && data.count > items.length}
    <p class="more">Gezeigt werden die {formatNumber(items.length)} größten von {formatNumber(data.count)} Dateien.</p>
  {/if}
</div>

<style>
  .storage {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px 32px;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px 16px;
    margin-bottom: 12px;
  }
  .segmented {
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: 20px;
    background: var(--chip);
  }
  .segmented button {
    min-height: 32px;
    padding: 0 14px;
    border: 0;
    border-radius: 16px;
    background: transparent;
    color: var(--muted);
  }
  .segmented button.active {
    background: var(--surface);
    color: var(--accent);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.15);
  }
  label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
  }
  .hint {
    flex-basis: 100%;
    order: 1;
    margin: 0;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .sum {
    color: var(--muted);
    font-size: 0.9rem;
  }
  .sum strong {
    color: var(--text);
  }
  .selbar {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin: 0 -16px 8px;
    padding: 8px 16px;
    background: color-mix(in srgb, var(--accent) 14%, var(--surface));
  }
  .grow {
    flex: 1;
  }
  .list {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 8px;
    border-radius: 8px;
  }
  li:hover {
    background: var(--chip);
  }
  li.on {
    background: color-mix(in srgb, var(--accent) 16%, transparent);
  }
  .check {
    display: grid;
    place-items: center;
    width: 36px;
    min-height: 36px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--accent);
  }
  .ring {
    width: 20px;
    height: 20px;
    border: 2px solid var(--muted);
    border-radius: 50%;
  }
  .open {
    position: relative;
    flex: none;
    width: 72px;
    height: 72px;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 6px;
    overflow: hidden;
    background: var(--placeholder);
  }
  .open img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .play {
    position: absolute;
    right: 4px;
    bottom: 4px;
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: rgb(0 0 0 / 0.5);
    color: #fff;
  }
  .meta {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 3px;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  small {
    color: var(--muted);
  }
  .bar {
    height: 4px;
    border-radius: 2px;
    background: var(--chip);
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .size {
    flex: none;
    min-width: 72px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .empty,
  .more {
    padding: 24px 8px;
    color: var(--muted);
    text-align: center;
  }
  @media (max-width: 479px) {
    .open {
      width: 56px;
      height: 56px;
    }
    .storage {
      padding: 8px 8px 24px;
    }
    .selbar {
      margin: 0 -8px 8px;
    }
  }
</style>
