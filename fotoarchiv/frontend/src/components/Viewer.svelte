<script>
  import { api, originalUrl, previewUrl, thumbUrl } from '../lib/api.js';
  import { DATE_SOURCES, formatBytes, formatDuration, formatTaken } from '../lib/format.js';
  import Icon from './Icon.svelte';

  let { items, index, onclose, onnavigate } = $props();

  const INFO_KEY = 'fotoarchiv.info';
  let showInfo = $state(readInfoSetting());
  let detail = $state(null);
  let error = $state('');
  let loadedId = $state(null); // Großansicht geladen: Platzhalter ausblenden

  const item = $derived(items[index]);
  const isVideo = $derived(item?.[4] === 1);

  function readInfoSetting() {
    try {
      return localStorage.getItem(INFO_KEY) !== '0' && window.innerWidth >= 900;
    } catch {
      return false;
    }
  }
  function toggleInfo() {
    showInfo = !showInfo;
    try {
      localStorage.setItem(INFO_KEY, showInfo ? '1' : '0');
    } catch {
      /* ohne Speicher geht es auch */
    }
  }

  $effect(() => {
    const id = item?.[0];
    detail = null;
    error = '';
    if (id === undefined) return;
    let cancelled = false;
    api.asset(id).then(
      (d) => !cancelled && (detail = d),
      (e) => !cancelled && (error = e.message),
    );
    // Nachbarn vorladen, damit das Blättern flüssig ist
    for (const n of [items[index + 1], items[index - 1]]) {
      if (n && !n[4]) new Image().src = previewUrl(n);
    }
    return () => (cancelled = true);
  });

  const go = (step) => {
    const next = index + step;
    if (next >= 0 && next < items.length) onnavigate(next);
  };

  function keydown(e) {
    if (e.target.closest?.('input, textarea')) return;
    if (e.key === 'Escape') onclose();
    else if (e.key === 'ArrowRight') go(1);
    else if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'i') toggleInfo();
    else return;
    e.preventDefault();
  }

  // Wischen auf Touch-Geräten
  let startX = null;
  const pointerdown = (e) => e.pointerType !== 'mouse' && (startX = e.clientX);
  function pointerup(e) {
    if (startX === null) return;
    const dx = e.clientX - startX;
    startX = null;
    if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1);
  }

  const mapLink = (d) => `https://www.openstreetmap.org/?mlat=${d.lat}&mlon=${d.lon}#map=15/${d.lat}/${d.lon}`;
</script>

<svelte:window onkeydown={keydown} />

<div class="viewer" role="dialog" aria-modal="true" aria-label="Einzelansicht">
  <div class="stage" onpointerdown={pointerdown} onpointerup={pointerup} role="presentation">
    {#key item[0]}
      {#if isVideo}
        <!-- svelte-ignore a11y_media_has_caption -->
        <video src={originalUrl(item)} poster={previewUrl(item)} controls autoplay playsinline></video>
      {:else}
        {#if loadedId !== item[0]}<img class="placeholder" src={thumbUrl(item)} alt="" />{/if}
        <img class="photo" src={previewUrl(item)} alt={detail?.name ?? ''} onload={() => (loadedId = item[0])} />
      {/if}
    {/key}

    <div class="toolbar">
      <button class="round" onclick={onclose} title="Schließen (Esc)"><Icon name="close" /></button>
      <span class="spacer"></span>
      <a class="round" href={originalUrl(item, true)} title="Original herunterladen"><Icon name="download" /></a>
      <button class="round" class:on={showInfo} onclick={toggleInfo} title="Informationen (i)"><Icon name="info" /></button>
    </div>
    {#if index > 0}
      <button class="nav prev" onclick={() => go(-1)} title="Neuer (←)"><Icon name="left" size={36} /></button>
    {/if}
    {#if index < items.length - 1}
      <button class="nav next" onclick={() => go(1)} title="Älter (→)"><Icon name="right" size={36} /></button>
    {/if}
  </div>

  {#if showInfo}
    <aside class="info">
      <h3>Informationen</h3>
      {#if error}
        <p class="error">{error}</p>
      {:else if !detail}
        <p class="muted">Wird geladen …</p>
      {:else}
        <dl>
          <dt>Aufnahme</dt>
          <dd>
            {formatTaken(detail.taken_at)}
            {#if detail.tz_offset}<span class="muted">(UTC{detail.tz_offset})</span>{/if}
            {#if DATE_SOURCES[detail.date_source]}
              <div class="hint"><Icon name="alert" size={14} />{DATE_SOURCES[detail.date_source]}</div>
            {/if}
          </dd>

          <dt>Ort</dt>
          <dd>
            {#if detail.lat !== null}
              <a href={mapLink(detail)} target="_blank" rel="noopener">{detail.lat.toFixed(5)}, {detail.lon.toFixed(5)}</a>
            {:else}
              <span class="muted">Kein Aufnahmeort</span>
            {/if}
          </dd>

          {#if detail.persons.length}
            <dt>Personen</dt>
            <dd class="chips">{#each detail.persons as person}<span class="chip">{person}</span>{/each}</dd>
          {/if}

          {#if detail.tags.length}
            <dt>Schlagworte</dt>
            <dd class="chips">{#each detail.tags as tag}<span class="chip">{tag}</span>{/each}</dd>
          {/if}

          {#if detail.camera}
            <dt>Kamera</dt>
            <dd>{detail.camera}</dd>
          {/if}

          <dt>Datei</dt>
          <dd>
            <div class="path">{detail.path}</div>
            <div class="muted">
              {[detail.width && `${detail.width} × ${detail.height}`, formatBytes(detail.size), formatDuration(detail.duration)]
                .filter(Boolean)
                .join(' · ')}
            </div>
          </dd>
        </dl>
      {/if}
    </aside>
  {/if}
</div>

<style>
  .viewer {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    background: #000;
    color: #fff;
  }
  .stage {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    touch-action: pan-y;
  }
  .stage img,
  .stage video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .placeholder {
    filter: blur(8px);
  }
  .toolbar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    gap: 8px;
    padding: 12px;
    background: linear-gradient(rgb(0 0 0 / 0.55), transparent);
    z-index: 2;
  }
  .spacer {
    flex: 1;
  }
  .round {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: #fff;
    cursor: pointer;
  }
  .round:hover,
  .round.on {
    background: rgb(255 255 255 / 0.18);
  }
  .nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    z-index: 2;
    display: grid;
    place-items: center;
    width: 56px;
    height: 96px;
    border: 0;
    background: transparent;
    color: #fff;
    opacity: 0.6;
    cursor: pointer;
  }
  .nav:hover {
    opacity: 1;
  }
  .prev {
    left: 0;
  }
  .next {
    right: 0;
  }
  .stage:has(video) .nav {
    top: 40%;
  }
  .info {
    width: 340px;
    flex: none;
    overflow-y: auto;
    padding: 20px;
    box-sizing: border-box;
    background: var(--surface);
    color: var(--text);
  }
  .info h3 {
    margin: 4px 0 20px;
    font-size: 1.1rem;
    font-weight: 500;
  }
  dl {
    margin: 0;
  }
  dt {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-top: 18px;
  }
  dd {
    margin: 4px 0 0;
    line-height: 1.45;
    overflow-wrap: anywhere;
  }
  .hint {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 2px;
    font-size: 0.85rem;
    color: var(--warning);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    padding: 2px 10px;
    border-radius: 12px;
    background: var(--chip);
    font-size: 0.875rem;
  }
  .path {
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .muted {
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
  a {
    color: var(--accent);
  }
  @media (max-width: 899px) {
    .viewer {
      flex-direction: column;
    }
    .info {
      width: auto;
      max-height: 45vh;
    }
    .nav {
      width: 44px;
    }
  }
</style>
