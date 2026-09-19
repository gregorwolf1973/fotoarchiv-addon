<script>
  import { formatNumber } from '../lib/format.js';
  import Icon from './Icon.svelte';

  // Zeitraum für die Karte: period = { on, start, span } (Startjahr, Länge in Jahren)
  let { period, minYear, maxYear, count, onchange } = $props();

  const SPANS = [1, 2, 3, 5, 10];

  const label = $derived(period.span === 1 ? `${period.start}` : `${period.start} – ${period.start + period.span - 1}`);

  const set = (changes) => onchange({ ...period, ...changes });
  const move = (step) => set({ start: Math.min(maxYear, Math.max(minYear, period.start + step)) });
</script>

<div class="timeline" class:on={period.on}>
  <button class="toggle" class:active={period.on} onclick={() => set({ on: !period.on })}
    title={period.on ? 'Alle Jahre zeigen' : 'Nur Fotos aus einem Zeitraum zeigen'}>
    <Icon name="calendar" size={18} />
    <span>{period.on ? label : 'Zeitraum'}</span>
  </button>
  {#if period.on}
    <button class="icon small" disabled={period.start <= minYear} onclick={() => move(-1)} title="Ein Jahr früher">
      <Icon name="left" size={20} />
    </button>
    <input
      type="range"
      min={minYear}
      max={maxYear}
      step="1"
      value={period.start}
      oninput={(e) => set({ start: Number(e.currentTarget.value) })}
      aria-label="Startjahr"
    />
    <button class="icon small" disabled={period.start >= maxYear} onclick={() => move(1)} title="Ein Jahr später">
      <Icon name="right" size={20} />
    </button>
    <select value={period.span} onchange={(e) => set({ span: Number(e.currentTarget.value) })} aria-label="Länge des Zeitraums">
      {#each SPANS as span}<option value={span}>{span === 1 ? '1 Jahr' : `${span} Jahre`}</option>{/each}
    </select>
    <span class="count">{formatNumber(count)} {count === 1 ? 'Foto' : 'Fotos'}</span>
  {/if}
</div>

<style>
  .timeline {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
    padding: 6px 10px;
    border-radius: 22px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 2px 12px rgb(0 0 0 / 0.3);
    pointer-events: auto;
  }
  .timeline.on {
    width: min(640px, calc(100vw - 32px));
    box-sizing: border-box;
    border-radius: 14px;
  }
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 32px;
    padding: 0 12px;
    border-radius: 16px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .toggle.active {
    background: var(--accent);
    color: var(--on-accent);
    border-color: transparent;
  }
  input[type='range'] {
    flex: 1;
    min-width: 120px;
    accent-color: var(--accent);
  }
  select {
    min-height: 32px;
    padding: 0 6px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    font: inherit;
    font-size: 0.85rem;
  }
  .count {
    font-size: 0.85rem;
    color: var(--muted);
    white-space: nowrap;
  }
</style>
