<script>
  import { api, thumbUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // Drehen prüfen: Jedes Foto erscheint so, wie es nach der Drehung aussähe. Stimmt das, nichts tun;
  // stimmt es nicht, antippen. "Übernehmen" erledigt dann alle auf einmal.
  let { revision, onopen, ontask } = $props();

  const PAGE = 120;
  let items = $state.raw(null);
  let wrong = $state(new Set()); // angetippt: Drehung stimmt nicht
  let done = $state(new Set()); // schon abgeschickt, bis zum nächsten Laden ausblenden
  let limit = $state(PAGE);
  let busy = $state(false);

  async function load() {
    try {
      items = (await api.rotationReview()).items;
    } catch (e) {
      notifyError(e);
    }
  }

  $effect(() => {
    revision;
    load();
  });

  const open = $derived((items ?? []).filter((i) => !done.has(i.id)));
  const shown = $derived(open.slice(0, limit));
  const automatic = $derived(shown.filter((i) => i.status === 'auto'));
  const suggested = $derived(shown.filter((i) => i.status === 'suggested'));

  // Viewer-Eintrag wie im Index: [id, ts, w, h, video, rev]
  const asItem = (i) => [i.id, i.ts, i.w || 1, i.h || 1, 0, i.rev];

  function toggle(id) {
    const next = new Set(wrong);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    wrong = next;
  }

  async function apply() {
    const accept = shown.filter((i) => !wrong.has(i.id)).map((i) => i.id);
    const reject = shown.filter((i) => wrong.has(i.id)).map((i) => i.id);
    busy = true;
    try {
      // Beide Listen als eigene Aufgaben: sie laufen nacheinander und überstehen einen Neustart
      if (accept.length) ontask(await api.decideRotations(accept, true));
      if (reject.length) ontask(await api.decideRotations(reject, false));
      done = new Set([...done, ...accept, ...reject]);
      wrong = new Set();
      limit = PAGE;
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }

  const direction = (degrees) => (degrees === 90 ? 'nach rechts' : degrees === 270 ? 'nach links' : 'um 180°');
  function caption(item, isWrong) {
    if (item.status === 'auto') return isWrong ? 'wird zurückgedreht' : `${direction(item.degrees)} gedreht`;
    return isWrong ? 'bleibt, wie es war' : `${direction(item.degrees)} drehen`;
  }
</script>

{#snippet card(item)}
  {@const isWrong = wrong.has(item.id)}
  <figure class:wrong={isWrong}>
    <button
      class="thumb"
      onclick={() => toggle(item.id)}
      title={isWrong ? 'Doch richtig – antippen zum Zurücknehmen' : 'Stimmt nicht – antippen'}
      aria-pressed={isWrong}
    >
      <!-- Vorschläge zeigt die Seite schon gedreht; automatisch gedrehte sind es wirklich -->
      <img
        src={thumbUrl(asItem(item), true)}
        alt=""
        loading="lazy"
        style:transform={item.status === 'suggested' && !isWrong ? `rotate(${item.degrees}deg)` : null}
      />
      {#if isWrong}<span class="mark"><Icon name="close" size={28} /></span>{/if}
    </button>
    <figcaption>
      <span>{caption(item, isWrong)}</span>
      <button class="icon small" onclick={() => onopen(open.map(asItem), item.id)} title="Groß ansehen"><Icon name="search" size={16} /></button>
    </figcaption>
  </figure>
{/snippet}

<div class="review">
  {#if items === null}
    <p class="muted">Wird geladen …</p>
  {:else if !open.length}
    <div class="empty">
      <Icon name="checkCircle" size={64} />
      <h2>Nichts zu prüfen</h2>
      <p>Die Bilderkennung hat keine falsch gedrehten Fotos gefunden – oder alle sind schon erledigt.</p>
    </div>
  {:else}
    <div class="head">
      <p class="hint">
        So sähen die Fotos richtig gedreht aus. <strong>Antippen, was nicht stimmt</strong> – dann „Übernehmen“.
        Angetippte bleiben bzw. werden wie vorher.
      </p>
      <button class="primary" disabled={busy} onclick={apply}>
        <Icon name="check" size={18} />
        {formatNumber(shown.length)} übernehmen{#if wrong.size} ({formatNumber(wrong.size)} abgelehnt){/if}
      </button>
    </div>

    {#if automatic.length}
      <h3>Automatisch gedreht <span class="count">{formatNumber(automatic.length)}</span></h3>
      <p class="hint">Mit Gesicht eindeutig erkannt und schon gedreht. Angetippte werden zurückgedreht.</p>
      <div class="grid">
        {#each automatic as item (item.id)}{@render card(item)}{/each}
      </div>
    {/if}

    {#if suggested.length}
      <h3>Vielleicht falsch gedreht <span class="count">{formatNumber(suggested.length)}</span></h3>
      <p class="hint">Noch nicht gedreht – die Vorschau zeigt den Vorschlag. Etwa jeder vierte Vorschlag liegt daneben.</p>
      <div class="grid">
        {#each suggested as item (item.id)}{@render card(item)}{/each}
      </div>
    {/if}

    {#if open.length > limit}
      <button class="more" onclick={() => (limit += PAGE)}>Weitere {formatNumber(Math.min(PAGE, open.length - limit))} anzeigen</button>
    {/if}
  {/if}
</div>

<style>
  .review {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 12px 16px 32px;
    box-sizing: border-box;
  }
  .head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .head .hint {
    flex: 1;
    min-width: 240px;
  }
  .hint {
    margin: 4px 0 12px;
    color: var(--muted);
    font-size: 0.9rem;
  }
  h3 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 20px 0 0;
    font-size: 1rem;
    font-weight: 500;
  }
  .count {
    padding: 0 8px;
    border-radius: 10px;
    background: var(--chip);
    color: var(--muted);
    font-size: 0.8rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
  }
  figure {
    display: grid;
    gap: 4px;
    min-width: 0;
    margin: 0;
  }
  .thumb {
    position: relative;
    display: block;
    aspect-ratio: 1;
    width: 100%;
    height: auto;
    padding: 0;
    border: 2px solid transparent;
    border-radius: 8px;
    overflow: hidden;
    background: var(--placeholder);
  }
  .thumb img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain; /* quadratische Fläche: auch um 90° gedreht passt das Foto hinein */
    transition: transform 0.2s ease;
  }
  .wrong .thumb {
    border-color: var(--danger);
  }
  .wrong .thumb img {
    opacity: 0.5;
  }
  .mark {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--danger);
  }
  figcaption {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    min-width: 0;
    font-size: 0.8rem;
    color: var(--muted);
  }
  .wrong figcaption {
    color: var(--danger);
  }
  .more {
    display: flex;
    margin: 16px auto 0;
  }
  .muted {
    color: var(--muted);
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
    .review {
      padding: 8px 8px 24px;
    }
    .grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }
  }
</style>
