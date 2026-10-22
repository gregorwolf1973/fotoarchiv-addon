<script>
  import { formatNumber } from '../lib/format.js';
  import Icon from './Icon.svelte';

  // filters: { tags: [{id, name}], persons: [{id, name}], start, end, q, ai, auto: [{id: name, name}] }
  // ai: Bildinhalt in normaler Sprache, auto: Schlagwort-Vorschläge der Bilderkennung
  // vision: Stand der Bilderkennung aus api/state (null = unbekannt)
  let { labels, filters, vision = null, onchange } = $props();

  const NONE = { tags: [], persons: [], start: '', end: '', q: '', ai: '', auto: [] };
  const smart = $derived(!!vision?.search);

  let text = $state('');
  let open = $state(false);
  let active = $state(-1); // markierte Zeile; -1 = keine
  let showDates = $state(false);
  let input = $state();

  const hasFilters = $derived(
    filters.tags.length || filters.persons.length || filters.start || filters.end || filters.q || filters.ai ||
      filters.auto?.length,
  );
  // Fortschritt der ersten Analyse: so lange findet die Bildsuche noch nicht alles
  const progress = $derived.by(() => {
    if (!vision?.enabled) return '';
    if (vision.status === 'downloading' && vision.download_total)
      return `Bildsuche wird eingerichtet: Modelle ${Math.round((vision.download_done / vision.download_total) * 100)} % geladen`;
    if (!vision.search) return vision.status === 'error' ? `Bildsuche gestört: ${vision.message}` : 'Bildsuche wird eingerichtet …';
    if (vision.done < vision.total) return `Bildinhalt: ${formatNumber(vision.done)} von ${formatNumber(vision.total)} analysiert`;
    return '';
  });

  const browsing = $derived(!text.trim()); // leeres Feld: alle Schlagworte zur Auswahl

  const suggestions = $derived.by(() => {
    const needle = text.trim().toLocaleLowerCase();
    const byCount = (a, b) => (b.count ?? 0) - (a.count ?? 0) || a.name.localeCompare(b.name, 'de');
    const auto = (labels.auto ?? []).map((l) => ({ ...l, id: l.name }));
    if (!needle) {
      const unused = (list, kind) =>
        list
          .filter((l) => !filters[kind].some((f) => f.id === l.id))
          .sort(byCount)
          .map((l) => ({ kind, id: l.id, name: l.name, count: l.count }));
      return [...unused(labels.tags, 'tags'), ...unused(auto, 'auto')];
    }
    const pick = (list, kind) =>
      list
        .filter((l) => l.name.toLocaleLowerCase().includes(needle))
        .filter((l) => !filters[kind].some((f) => f.id === l.id))
        .slice(0, 6)
        .map((l) => ({ kind, id: l.id, name: l.name, count: l.count }));
    const found = [...pick(labels.persons, 'persons'), ...pick(labels.tags, 'tags'), ...pick(auto, 'auto')];
    const q = { kind: 'q', name: text.trim() };
    const ai = smart ? [{ kind: 'ai', name: text.trim() }] : [];
    // Passt der Text zu keinem Namen, ist er meist eine Beschreibung: dann zuerst die Bildsuche
    return found.length ? [q, ...found, ...ai] : [...ai, q];
  });
  const firstAuto = $derived(browsing ? suggestions.findIndex((s) => s.kind === 'auto') : -1);

  function choose(suggestion) {
    if (suggestion.kind === 'q' || suggestion.kind === 'ai') onchange({ ...filters, [suggestion.kind]: suggestion.name });
    else onchange({ ...filters, [suggestion.kind]: [...filters[suggestion.kind], { id: suggestion.id, name: suggestion.name }] });
    text = '';
    open = false;
    active = -1;
  }

  function keydown(e) {
    if (e.key === 'ArrowDown' && suggestions.length) {
      active = (active + 1) % suggestions.length;
      open = true;
    } else if (e.key === 'ArrowUp' && suggestions.length) {
      active = active <= 0 ? suggestions.length - 1 : active - 1;
    } else if (e.key === 'Enter' && browsing) {
      // Leeres Feld: Enter nimmt nur ein Schlagwort, das man mit den Pfeiltasten gewählt hat
      if (active >= 0 && suggestions[active]) choose(suggestions[active]);
    } else if (e.key === 'Enter' && suggestions.length) {
      // Genau ein passendes Label: direkt als Filter nehmen, sonst die gewählte Zeile
      const exact = suggestions.find(
        (s) => s.kind !== 'q' && s.kind !== 'ai' && s.name.toLocaleLowerCase() === text.trim().toLocaleLowerCase(),
      );
      choose(active === 0 && exact ? exact : suggestions[active]);
    } else if (e.key === 'Escape') {
      open = false;
      input.blur();
    } else if (e.key === 'Backspace' && !text) {
      removeLast();
    } else {
      return;
    }
    e.preventDefault();
  }

  function removeLast() {
    if (filters.ai) onchange({ ...filters, ai: '' });
    else if (filters.q) onchange({ ...filters, q: '' });
    else if (filters.auto?.length) onchange({ ...filters, auto: filters.auto.slice(0, -1) });
    else if (filters.tags.length) onchange({ ...filters, tags: filters.tags.slice(0, -1) });
    else if (filters.persons.length) onchange({ ...filters, persons: filters.persons.slice(0, -1) });
  }

  const ICONS = { q: 'search', ai: 'sparkle', persons: 'person', tags: 'tag', auto: 'sparkle' };

  const without = (kind, id) => onchange({ ...filters, [kind]: filters[kind].filter((f) => f.id !== id) });

  const dateLabel = $derived.by(() => {
    const fmt = (d) => d.split('-').reverse().join('.');
    if (filters.start && filters.end) return filters.start === filters.end ? fmt(filters.start) : `${fmt(filters.start)} – ${fmt(filters.end)}`;
    if (filters.start) return `ab ${fmt(filters.start)}`;
    if (filters.end) return `bis ${fmt(filters.end)}`;
    return '';
  });

  function setYear(year) {
    onchange({ ...filters, start: `${year}-01-01`, end: `${year}-12-31` });
  }
</script>

<div class="search" class:focused={open}>
  <Icon name="search" size={20} />
  <div class="chips">
    {#each filters.persons as p (p.id)}
      <span class="chip"><Icon name="person" size={14} />{p.name}<button onclick={() => without('persons', p.id)} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/each}
    {#each filters.tags as t (t.id)}
      <span class="chip"><Icon name="tag" size={14} />{t.name}<button onclick={() => without('tags', t.id)} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/each}
    {#each filters.auto ?? [] as t (t.id)}
      <span class="chip" title="Von der Bilderkennung vorgeschlagen, noch nicht übernommen"><Icon name="sparkle" size={14} />{t.name}<button onclick={() => without('auto', t.id)} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/each}
    {#if filters.ai}
      <span class="chip" title="Bildinhalt"><Icon name="sparkle" size={14} />„{filters.ai}“<button onclick={() => onchange({ ...filters, ai: '' })} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/if}
    {#if dateLabel}
      <span class="chip"><Icon name="calendar" size={14} />{dateLabel}<button onclick={() => onchange({ ...filters, start: '', end: '' })} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/if}
    {#if filters.q}
      <span class="chip"><Icon name="search" size={14} />„{filters.q}“<button onclick={() => onchange({ ...filters, q: '' })} title="Filter entfernen"><Icon name="close" size={14} /></button></span>
    {/if}
    <input
      bind:this={input}
      bind:value={text}
      type="text"
      placeholder={hasFilters ? '' : smart ? 'Suchen: Personen, Schlagworte, Bildinhalt …' : 'Suchen: Personen, Schlagworte, Dateiname …'}
      onkeydown={keydown}
      oninput={() => ((open = true), (active = text.trim() ? 0 : -1))}
      onfocus={() => ((open = true), (active = text.trim() ? 0 : -1))}
      onblur={() => setTimeout(() => (open = false), 150)}
      enterkeyhint="search"
      aria-label="Suchen"
    />
  </div>
  <button class="icon small" class:on={showDates} onclick={() => (showDates = !showDates)} title="Zeitraum">
    <Icon name="calendar" size={18} />
  </button>
  {#if hasFilters}
    <button class="icon small" onclick={() => onchange(NONE)} title="Alle Filter entfernen">
      <Icon name="close" size={18} />
    </button>
  {/if}

  {#if open && suggestions.length}
    <ul class="suggestions" class:browse={browsing} role="listbox">
      {#if browsing && firstAuto !== 0}<li class="heading">Schlagworte</li>{/if}
      {#each suggestions as s, i}
        {#if i === firstAuto}<li class="heading" title="Noch nicht in den Fotos gespeichert – übernehmen oder ablehnen">Erkannt (Vorschläge)</li>{/if}
        <li role="option" aria-selected={i === active}>
          <button class:active={i === active} onmousedown={(e) => (e.preventDefault(), choose(s))}>
            <Icon name={ICONS[s.kind]} size={18} />
            <span class="name">
              {s.kind === 'q' ? `Name, Schlagwort oder Kamera enthält „${s.name}“` : s.kind === 'ai' ? `Fotos von „${s.name}“` : s.name}
              {#if s.kind === 'ai'}<span class="kind">Bildinhalt</span>{:else if s.kind === 'auto' && !browsing}<span class="kind">erkannt</span>{/if}
            </span>
            {#if s.count}<span class="count">{s.count}</span>{/if}
          </button>
        </li>
      {/each}
      {#if progress}<li class="status">{progress}</li>{/if}
    </ul>
  {:else if open && progress && !text.trim()}
    <ul class="suggestions"><li class="status">{progress}</li></ul>
  {/if}

  {#if showDates}
    <div class="dates">
      <label class="field">Von<input type="date" value={filters.start} onchange={(e) => onchange({ ...filters, start: e.currentTarget.value })} /></label>
      <label class="field">Bis<input type="date" value={filters.end} onchange={(e) => onchange({ ...filters, end: e.currentTarget.value })} /></label>
      <label class="field">
        Ganzes Jahr
        <input type="number" min="1800" max="2100" placeholder="z. B. 2019" onchange={(e) => e.currentTarget.value && setYear(e.currentTarget.value)} />
      </label>
      <button class="icon small close" onclick={() => (showDates = false)} title="Schließen"><Icon name="close" size={18} /></button>
    </div>
  {/if}
</div>

<style>
  .search {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 40px;
    padding: 2px 6px 2px 12px;
    border-radius: 20px;
    background: var(--chip);
    color: var(--muted);
  }
  .search.focused {
    background: var(--surface);
    box-shadow: 0 0 0 2px var(--accent);
  }
  .chips {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .chip {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 2px 1px 8px;
    border-radius: 14px;
    background: var(--accent);
    color: var(--on-accent);
    font-size: 0.85rem;
    line-height: 24px;
    white-space: nowrap;
  }
  .chip button {
    min-height: 0;
    width: 22px;
    height: 22px;
    padding: 0;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: inherit;
  }
  input[type='text'] {
    flex: 1;
    min-width: 80px;
    min-height: 34px;
    padding: 0;
    border: 0;
    background: transparent;
    outline: none;
  }
  .on {
    color: var(--accent);
  }
  .suggestions {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    z-index: 30;
    margin: 0;
    padding: 6px 0;
    list-style: none;
    border-radius: 12px;
    background: var(--surface);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.25);
  }
  .suggestions.browse {
    max-height: min(50vh, 420px);
    overflow-y: auto;
  }
  .heading {
    padding: 4px 16px 6px;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .suggestions button {
    width: 100%;
    min-height: 40px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--text);
    font-weight: 400;
    text-align: left;
  }
  .suggestions button.active,
  .suggestions button:hover {
    background: var(--chip);
  }
  .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    color: var(--muted);
    font-size: 0.8rem;
  }
  .kind {
    margin-left: 8px;
    padding: 0 6px;
    border-radius: 8px;
    background: var(--chip);
    color: var(--muted);
    font-size: 0.75rem;
  }
  .status {
    padding: 8px 16px 4px;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.8rem;
  }
  .dates {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 30;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 0 12px;
    padding: 4px 48px 16px 16px;
    border-radius: 12px;
    background: var(--surface);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.25);
  }
  .dates input[type='number'] {
    width: 110px;
    box-sizing: border-box;
    min-height: 38px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    font: inherit;
  }
  .dates .close {
    position: absolute;
    top: 6px;
    right: 6px;
  }
</style>
