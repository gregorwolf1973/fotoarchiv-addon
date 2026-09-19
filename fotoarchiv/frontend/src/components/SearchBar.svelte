<script>
  import Icon from './Icon.svelte';

  // filters: { tags: [{id, name}], persons: [{id, name}], start, end, q }
  let { labels, filters, onchange } = $props();

  let text = $state('');
  let open = $state(false);
  let active = $state(-1); // markierte Zeile; -1 = keine
  let showDates = $state(false);
  let input = $state();

  const hasFilters = $derived(
    filters.tags.length || filters.persons.length || filters.start || filters.end || filters.q,
  );

  const browsing = $derived(!text.trim()); // leeres Feld: alle Schlagworte zur Auswahl

  const suggestions = $derived.by(() => {
    const needle = text.trim().toLocaleLowerCase();
    if (!needle) {
      return labels.tags
        .filter((t) => !filters.tags.some((f) => f.id === t.id))
        .sort((a, b) => (b.count ?? 0) - (a.count ?? 0) || a.name.localeCompare(b.name, 'de'))
        .map((t) => ({ kind: 'tags', id: t.id, name: t.name, count: t.count }));
    }
    const pick = (list, kind) =>
      list
        .filter((l) => l.name.toLocaleLowerCase().includes(needle))
        .filter((l) => !filters[kind].some((f) => f.id === l.id))
        .slice(0, 6)
        .map((l) => ({ kind, id: l.id, name: l.name, count: l.count }));
    return [
      { kind: 'q', name: text.trim() },
      ...pick(labels.persons, 'persons'),
      ...pick(labels.tags, 'tags'),
    ];
  });

  function choose(suggestion) {
    if (suggestion.kind === 'q') onchange({ ...filters, q: suggestion.name });
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
      const exact = suggestions.find((s) => s.kind !== 'q' && s.name.toLocaleLowerCase() === text.trim().toLocaleLowerCase());
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
    if (filters.q) onchange({ ...filters, q: '' });
    else if (filters.tags.length) onchange({ ...filters, tags: filters.tags.slice(0, -1) });
    else if (filters.persons.length) onchange({ ...filters, persons: filters.persons.slice(0, -1) });
  }

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
      placeholder={hasFilters ? '' : 'Suchen: Personen, Schlagworte, Dateiname …'}
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
    <button class="icon small" onclick={() => onchange({ tags: [], persons: [], start: '', end: '', q: '' })} title="Alle Filter entfernen">
      <Icon name="close" size={18} />
    </button>
  {/if}

  {#if open && suggestions.length}
    <ul class="suggestions" class:browse={browsing} role="listbox">
      {#if browsing}<li class="heading">Schlagworte</li>{/if}
      {#each suggestions as s, i}
        <li role="option" aria-selected={i === active}>
          <button class:active={i === active} onmousedown={(e) => (e.preventDefault(), choose(s))}>
            <Icon name={s.kind === 'q' ? 'search' : s.kind === 'persons' ? 'person' : 'tag'} size={18} />
            <span class="name">{s.kind === 'q' ? `Suche nach „${s.name}“` : s.name}</span>
            {#if s.count}<span class="count">{s.count}</span>{/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if showDates}
    <div class="dates">
      <label class="field">Von<input type="date" value={filters.start} onchange={(e) => onchange({ ...filters, start: e.currentTarget.value })} /></label>
      <label class="field">Bis<input type="date" value={filters.end} onchange={(e) => onchange({ ...filters, end: e.currentTarget.value })} /></label>
      <label class="field">
        Ganzes Jahr
        <input type="number" min="1900" max="2100" placeholder="z. B. 2019" onchange={(e) => e.currentTarget.value && setYear(e.currentTarget.value)} />
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
