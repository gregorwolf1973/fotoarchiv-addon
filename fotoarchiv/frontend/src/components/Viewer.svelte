<script>
  import { api, originalUrl, previewUrl, thumbUrl } from '../lib/api.js';
  import { DATE_SOURCES, formatBytes, formatDuration, formatTaken } from '../lib/format.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import ChipInput from './ChipInput.svelte';
  import DateDialog from './DateDialog.svelte';
  import Icon from './Icon.svelte';

  let { items, index, trash = false, labels, onclose, onnavigate, onchanged, ondelete, onrestore, onpurge } = $props();

  const INFO_KEY = 'fotoarchiv.info';
  let showInfo = $state(readInfoSetting());
  let detail = $state(null);
  let error = $state('');
  let busy = $state(false);
  let editDate = $state(false);
  let loadedKey = $state(null); // Großansicht geladen: Platzhalter ausblenden

  const item = $derived(items[index]);
  const itemId = $derived(item?.[0]);
  const key = $derived(`${item[0]}-${item[5]}`); // neue Revision (z. B. gedreht) lädt neu
  const isVideo = $derived(item?.[4] === 1);
  const canEdit = $derived(!trash && detail?.editable);

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
    const id = itemId;
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

  /** Änderung speichern; der Server schreibt in die Datei und liefert die neuen Daten. */
  async function save(action, success) {
    if (busy) return false;
    busy = true;
    try {
      detail = await action();
      if (success) notify(success);
      onchanged();
      return true;
    } catch (e) {
      notifyError(e);
      detail = await api.asset(itemId).catch(() => detail); // Stand der Datei zurückholen
      return false;
    } finally {
      busy = false;
    }
  }

  const rotate = (degrees) => save(() => api.rotate(itemId, degrees));
  const setLabels = (kind, values) => save(() => api.update(itemId, { [kind]: values }));
  function setDate(value) {
    editDate = false;
    save(() => api.update(itemId, { taken_at: value }), 'Datum gespeichert');
  }
  async function removeLocation() {
    const { lat, lon } = detail;
    const id = itemId;
    if (await save(() => api.update(id, { location: null }))) {
      notify('Ort entfernt', {
        actionLabel: 'Rückgängig',
        action: () => api.update(id, { location: { lat, lon } }).then(onchanged, notifyError),
      });
    }
  }

  const go = (step) => {
    const next = index + step;
    if (next >= 0 && next < items.length) onnavigate(next);
  };

  function keydown(e) {
    if (editDate || e.target.closest?.('input, textarea, .modal')) return;
    if (e.key === 'Escape') onclose();
    else if (e.key === 'ArrowRight') go(1);
    else if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'i') toggleInfo();
    else if (e.key === 'Delete' && !trash) ondelete(itemId);
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
  const expires = (d) => new Date(d.expires_at).toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' });
</script>

<svelte:window onkeydown={keydown} />

<div class="viewer" role="dialog" aria-modal="true" aria-label="Einzelansicht">
  <div class="stage" onpointerdown={pointerdown} onpointerup={pointerup} role="presentation">
    {#key key}
      {#if isVideo}
        <!-- svelte-ignore a11y_media_has_caption -->
        <video src={originalUrl(item)} poster={previewUrl(item)} controls autoplay playsinline></video>
      {:else}
        {#if loadedKey !== key}<img class="placeholder" src={thumbUrl(item)} alt="" />{/if}
        <img class="photo" src={previewUrl(item)} alt={detail?.name ?? ''} onload={() => (loadedKey = key)} />
      {/if}
    {/key}

    <div class="toolbar">
      <button class="round" onclick={onclose} title="Schließen (Esc)"><Icon name="close" /></button>
      <span class="spacer"></span>
      {#if busy}<span class="spinner" title="Wird gespeichert"></span>{/if}
      {#if trash}
        <button class="round" onclick={() => onrestore(itemId)} title="Wiederherstellen"><Icon name="restore" /></button>
        <button class="round" onclick={() => onpurge(itemId)} title="Endgültig löschen"><Icon name="deleteForever" /></button>
      {:else}
        {#if detail?.rotatable}
          <button class="round" disabled={busy} onclick={() => rotate(270)} title="Nach links drehen"><Icon name="rotate" /></button>
          <button class="round" disabled={busy} onclick={() => rotate(90)} title="Nach rechts drehen"><Icon name="rotate" flip /></button>
        {/if}
        <a class="round" href={originalUrl(item, true)} title="Original herunterladen"><Icon name="download" /></a>
        <button class="round" disabled={busy} onclick={() => ondelete(itemId)} title="In den Papierkorb (Entf)"><Icon name="delete" /></button>
      {/if}
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
        {#if trash}
          <p class="notice"><Icon name="delete" size={16} /> Im Papierkorb – wird am {expires(detail)} endgültig gelöscht.</p>
        {:else if !detail.editable}
          <p class="notice"><Icon name="alert" size={16} /> Dieses Dateiformat kann keine Metadaten speichern und ist daher nicht bearbeitbar.</p>
        {/if}
        <dl>
          <dt>Aufnahme</dt>
          <dd class="row">
            <div>
              {formatTaken(detail.taken_at)}
              {#if detail.tz_offset}<span class="muted">(UTC{detail.tz_offset})</span>{/if}
              {#if DATE_SOURCES[detail.date_source]}
                <div class="hint"><Icon name="alert" size={14} />{DATE_SOURCES[detail.date_source]}</div>
              {/if}
            </div>
            {#if canEdit}
              <button class="icon small" disabled={busy} onclick={() => (editDate = true)} title="Datum ändern"><Icon name="pencil" size={18} /></button>
            {/if}
          </dd>

          <dt>Ort</dt>
          <dd class="row">
            {#if detail.lat !== null}
              <a href={mapLink(detail)} target="_blank" rel="noopener">{detail.lat.toFixed(5)}, {detail.lon.toFixed(5)}</a>
              {#if canEdit}
                <button class="icon small" disabled={busy} onclick={removeLocation} title="Ort entfernen"><Icon name="close" size={18} /></button>
              {/if}
            {:else}
              <span class="muted">Kein Aufnahmeort</span>
            {/if}
          </dd>

          <dt>Personen</dt>
          <dd>
            {#if canEdit || detail.persons.length}
              <ChipInput
                values={detail.persons}
                suggestions={labels.persons.map((p) => p.name)}
                icon="person"
                placeholder="Person hinzufügen"
                disabled={!canEdit || busy}
                onchange={(v) => setLabels('persons', v)}
              />
            {:else}
              <span class="muted">Keine</span>
            {/if}
          </dd>

          <dt>Schlagworte</dt>
          <dd>
            {#if canEdit || detail.tags.length}
              <ChipInput
                values={detail.tags}
                suggestions={labels.tags.map((t) => t.name)}
                icon="tag"
                placeholder="Schlagwort hinzufügen"
                disabled={!canEdit || busy}
                onchange={(v) => setLabels('tags', v)}
              />
            {:else}
              <span class="muted">Keine</span>
            {/if}
          </dd>

          {#if detail.camera}
            <dt>Kamera</dt>
            <dd>{detail.camera}</dd>
          {/if}

          <dt>Datei</dt>
          <dd>
            <div class="path">{detail.orig_path ?? detail.path}</div>
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

{#if editDate && detail}
  <DateDialog value={detail.taken_at} onsave={setDate} oncancel={() => (editDate = false)} />
{/if}

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
    align-items: center;
    gap: 4px;
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
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: #fff;
    cursor: pointer;
  }
  .round:hover:not(:disabled),
  .round.on {
    background: rgb(255 255 255 / 0.18);
  }
  .spinner {
    width: 18px;
    height: 18px;
    margin: 0 10px;
    border: 2px solid #fff;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
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
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: #fff;
    opacity: 0.6;
    cursor: pointer;
  }
  .nav:hover:not(:disabled) {
    opacity: 1;
    background: transparent;
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
    width: 360px;
    flex: none;
    overflow-y: auto;
    padding: 20px;
    box-sizing: border-box;
    background: var(--surface);
    color: var(--text);
  }
  .info h3 {
    margin: 4px 0 16px;
    font-size: 1.1rem;
    font-weight: 500;
  }
  .notice {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    margin: 0 0 8px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--warning-bg);
    font-size: 0.875rem;
    line-height: 1.4;
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
    margin: 6px 0 0;
    line-height: 1.45;
    overflow-wrap: anywhere;
  }
  dd.row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  .hint {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 2px;
    font-size: 0.85rem;
    color: var(--warning);
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
      max-height: 50vh;
    }
    .nav {
      width: 44px;
    }
    .round {
      width: 40px;
      height: 40px;
    }
  }
</style>
