<script>
  import { api, thumbUrl } from '../lib/api.js';
  import { formatBytes, formatNumber } from '../lib/format.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import Confirm from './Confirm.svelte';
  import Icon from './Icon.svelte';

  let { revision, onopen, ontask, onchanged } = $props();

  const PAGE = 40;
  const SOURCES = { exif: 'Datum aus Kamera', filename: 'Datum aus Dateiname', mtime: 'Datum geschätzt' };

  let data = $state.raw(null);
  let tab = $state('duplicates'); // duplicates | series
  let keepByGroup = $state({}); // Gruppe -> behaltene Fotos (abweichend von der Empfehlung)
  let done = $state(new Set()); // erledigte Gruppen bis zum nächsten Laden ausblenden
  let transfer = $state(true);
  let limit = $state(PAGE);
  let confirmAll = $state(false);
  let busy = $state(false);

  async function load() {
    try {
      data = await api.duplicates();
    } catch (e) {
      notifyError(e);
    }
  }

  $effect(() => {
    revision;
    load();
  });

  const groups = $derived((data?.[tab] ?? []).filter((g) => !done.has(g.key)));
  const counts = $derived({
    duplicates: (data?.duplicates ?? []).filter((g) => !done.has(g.key)).length,
    series: (data?.series ?? []).filter((g) => !done.has(g.key)).length,
  });
  const extra = $derived(groups.reduce((sum, g) => sum + g.items.length - 1, 0));

  const kept = (group) => keepByGroup[group.key] ?? [group.keep];

  function toggleKeep(group, id) {
    const current = kept(group);
    keepByGroup[group.key] = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
  }

  // Viewer-Eintrag wie im Index: [id, ts, w, h, video, rev]
  const asItem = (i) => [i.id, i.taken_ts, i.width || 1, i.height || 1, 0, i.rev];

  const date = (ts) =>
    new Date(ts * 1000).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' });

  function plan(group) {
    const keep = kept(group);
    const remove = group.items.map((i) => i.id).filter((id) => !keep.includes(id));
    return { keep: [...keep].sort((a, b) => (a === group.keep ? -1 : b === group.keep ? 1 : 0)), remove };
  }

  async function resolve(list) {
    const payload = list.map(plan).filter((p) => p.keep.length && p.remove.length);
    if (!payload.length) return;
    busy = true;
    try {
      const task = await api.resolveDuplicates(payload, transfer);
      done = new Set([...done, ...list.map((g) => g.key)]);
      ontask(task);
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }

  async function ignore(group) {
    try {
      await api.ignoreDuplicates(group.items.map((i) => i.id));
      done = new Set([...done, group.key]);
      notify('Als „keine Duplikate“ gemerkt');
      onchanged();
    } catch (e) {
      notifyError(e);
    }
  }

  function setTab(next) {
    tab = next;
    limit = PAGE;
  }
</script>

<div class="dups">
  {#if data && !data.enabled}
    <div class="empty">
      <Icon name="duplicate" size={64} />
      <h2>Doppelten-Erkennung ist ausgeschaltet</h2>
      <p>Einschalten in Home Assistant unter Einstellungen → Add-ons → Fotoarchiv → Konfiguration.</p>
    </div>
  {:else if data}
    <div class="head">
      <nav class="tabs">
        <button class:active={tab === 'duplicates'} onclick={() => setTab('duplicates')}>
          Doppelt <span class="count">{formatNumber(counts.duplicates)}</span>
        </button>
        <button class:active={tab === 'series'} onclick={() => setTab('series')}>
          Serien <span class="count">{formatNumber(counts.series)}</span>
        </button>
      </nav>
      <span class="grow"></span>
      {#if data.hashed < data.images}
        <span class="progress muted"><span class="spinner"></span>{formatNumber(data.hashed)} von {formatNumber(data.images)} Fotos analysiert</span>
      {/if}
    </div>

    <p class="hint">
      {#if tab === 'duplicates'}
        Gleiches Motiv – z. B. verkleinerte Kopie, anderes Format oder erneut gespeichert. Vorgeschlagen wird die beste
        Fassung (Auflösung, Datum, Metadaten).
      {:else}
        Sehr ähnliche Fotos, die innerhalb von 30 Sekunden aufgenommen wurden. Vorgeschlagen wird die größte Datei – meist
        die schärfste. Bitte selbst prüfen.
      {/if}
      Antippen des Schalters ändert, was behalten wird.
    </p>

    {#if groups.length}
      <div class="toolbar">
        <label class="check">
          <input type="checkbox" bind:checked={transfer} />
          Schlagworte, Personen, Ort und Datum aufs behaltene Foto übertragen
        </label>
        <span class="grow"></span>
        {#if tab === 'duplicates'}
          <button class="primary" disabled={busy} onclick={() => (confirmAll = true)}>
            <Icon name="checkCircle" size={18} /> Alle Vorschläge übernehmen
          </button>
        {/if}
      </div>

      {#each groups.slice(0, limit) as group (group.key)}
        {@const keep = kept(group)}
        <section class="group">
          <header>
            <strong>{date(group.items[0].taken_ts)}</strong>
            <span class="muted">
              {group.items.length} Fotos{#if group.kind === 'series' && group.span} · innerhalb von {group.span} s{/if}
            </span>
            <span class="grow"></span>
            <button onclick={() => ignore(group)} title="Diese Fotos nicht mehr als Duplikate vorschlagen">
              <Icon name="hide" size={18} /><span class="label">Keine Duplikate</span>
            </button>
            <button
              class="primary"
              disabled={busy || !keep.length || keep.length === group.items.length}
              onclick={() => resolve([group])}
              title={keep.length ? '' : 'Mindestens ein Foto behalten'}
            >
              <Icon name="delete" size={18} />
              {group.items.length - keep.length} löschen
            </button>
          </header>
          <div class="items">
            {#each group.items as item (item.id)}
              {@const on = keep.includes(item.id)}
              <figure class:remove={!on}>
                <button class="thumb" onclick={() => onopen(group.items.map(asItem), item.id)} title="Groß ansehen">
                  <img src={thumbUrl(asItem(item))} alt={item.name} loading="lazy" />
                </button>
                <button class="keep" class:on onclick={() => toggleKeep(group, item.id)}>
                  <Icon name={on ? 'checkCircle' : 'delete'} size={18} />
                  {on ? 'Behalten' : 'Löschen'}
                  {#if item.id === group.keep}<span class="tip" title="Empfehlung">★</span>{/if}
                </button>
                <figcaption>
                  <span class="name" title={item.path}>{item.name}</span>
                  <span>{item.width && item.height ? `${item.width} × ${item.height}` : '–'} · {formatBytes(item.size)} · {item.format}</span>
                  <span class="muted">{SOURCES[item.date_source] ?? item.date_source}{#if item.camera} · {item.camera}{/if}</span>
                  <span class="labels muted">
                    {#if item.tags}<span title="Schlagworte"><Icon name="tag" size={14} />{item.tags}</span>{/if}
                    {#if item.persons}<span title="Personen"><Icon name="person" size={14} />{item.persons}</span>{/if}
                    {#if item.has_location}<span title="Aufnahmeort"><Icon name="marker" size={14} /></span>{/if}
                  </span>
                </figcaption>
              </figure>
            {/each}
          </div>
        </section>
      {/each}
      {#if groups.length > limit}
        <button class="more" onclick={() => (limit += PAGE)}>Weitere {formatNumber(Math.min(PAGE, groups.length - limit))} Gruppen anzeigen</button>
      {/if}
    {:else}
      <div class="empty">
        <Icon name="checkCircle" size={64} />
        <h2>{tab === 'duplicates' ? 'Keine doppelten Fotos gefunden' : 'Keine Serien gefunden'}</h2>
        {#if data.hashed < data.images}<p>Die Analyse läuft noch – später erneut vorbeischauen.</p>{/if}
      </div>
    {/if}
  {/if}
</div>

{#if confirmAll}
  <Confirm
    title="Alle Vorschläge übernehmen?"
    text={`${formatNumber(extra)} ${extra === 1 ? 'Foto kommt' : 'Fotos kommen'} aus ${formatNumber(groups.length)} Gruppen in den Papierkorb.${transfer ? ' Metadaten werden vorher aufs behaltene Foto übertragen.' : ''}`}
    confirmLabel="In den Papierkorb"
    danger
    oncancel={() => (confirmAll = false)}
    onconfirm={() => {
      confirmAll = false;
      resolve(groups);
    }}
  />
{/if}

<style>
  .dups {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 12px 16px 32px;
    box-sizing: border-box;
  }
  .head,
  .toolbar,
  .group header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .grow {
    flex: 1;
  }
  .tabs {
    display: flex;
    gap: 4px;
  }
  .tabs button {
    border-radius: 18px;
    background: transparent;
    border-color: transparent;
  }
  .tabs button.active {
    background: var(--chip);
    color: var(--accent);
  }
  .count {
    padding: 0 8px;
    border-radius: 10px;
    background: var(--chip);
    color: var(--muted);
    font-size: 0.8rem;
  }
  .muted {
    color: var(--muted);
  }
  .progress {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
  }
  .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .hint {
    margin: 8px 0 12px;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .toolbar {
    margin-bottom: 12px;
  }
  .check {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
  }
  .group {
    margin-bottom: 16px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
  }
  .group header {
    margin-bottom: 10px;
  }
  .items {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
  }
  figure {
    display: grid;
    gap: 6px;
    min-width: 0;
    margin: 0;
  }
  .thumb {
    display: block;
    height: 180px;
    padding: 0;
    border: 0;
    border-radius: 8px;
    overflow: hidden;
    background: var(--placeholder);
  }
  .thumb img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .remove .thumb img {
    opacity: 0.45;
  }
  .keep {
    justify-content: center;
    color: var(--danger);
  }
  .keep.on {
    color: var(--success);
  }
  .tip {
    color: var(--warning);
  }
  figcaption {
    display: grid;
    gap: 2px;
    min-width: 0;
    font-size: 0.8rem;
  }
  figcaption span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name {
    font-weight: 500;
  }
  .labels {
    display: flex;
    gap: 8px;
    min-height: 14px;
  }
  .labels span {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .more {
    display: flex;
    margin: 0 auto;
  }
  .empty {
    display: grid;
    justify-items: center;
    gap: 4px;
    margin-top: 12vh;
    color: var(--muted);
    text-align: center;
  }
  .empty h2 {
    margin: 8px 0 0;
    color: var(--text);
    font-weight: 500;
  }
  @media (max-width: 639px) {
    .dups {
      padding: 8px 8px 24px;
    }
    .items {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .thumb {
      height: 120px;
    }
    .group header .label {
      display: none;
    }
  }
</style>
