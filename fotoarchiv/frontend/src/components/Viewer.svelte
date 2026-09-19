<script>
  import { api, originalUrl, previewUrl, thumbUrl } from '../lib/api.js';
  import { DATE_SOURCES, formatBytes, formatDuration, formatTaken } from '../lib/format.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import { clampView, RESET, zoomAt } from '../lib/zoom.js';
  import ChipInput from './ChipInput.svelte';
  import Confirm from './Confirm.svelte';
  import DateDialog from './DateDialog.svelte';
  import FaceBoxes from './FaceBoxes.svelte';
  import LocationDialog from './LocationDialog.svelte';
  import Icon from './Icon.svelte';

  let { items, index, trash = false, canEdit: allowed = true, canDelete = true, canPurge = true, labels, onclose, onnavigate, onchanged, ondelete, onrestore, onpurge } = $props();

  const INFO_KEY = 'fotoarchiv.info';
  let showInfo = $state(readInfoSetting());
  let detail = $state(null);
  let error = $state('');
  let busy = $state(false);
  let editDate = $state(false);
  let editLocation = $state(false);
  let loadedKey = $state(null); // Großansicht geladen: Platzhalter ausblenden
  let showFaces = $state(false);
  let stageWidth = $state(0);
  let stageHeight = $state(0);
  let natural = $state({ width: 0, height: 0 });
  let videoError = $state('');
  let stage = $state();
  let view = $state(RESET); // Zoom: { scale, x, y }
  let hiresFor = $state(null); // Original nachladen, sobald gezoomt wird (einmal je Bild)
  let hiresReady = $state(null);
  // Personen, Schlagworte und Ort erst mit "Speichern" in die Datei schreiben.
  // draft enthält nur geänderte Felder; location: null = Ort entfernen
  let draft = $state({});
  let personText = $state('');
  let tagText = $state('');
  let personInput = $state();
  let tagInput = $state();
  let leaving = $state(null); // Aktion, die auf "Änderungen verwerfen?" wartet

  // Ein .mp4 sagt nichts über den Codec darin. Kann der Browser ihn nicht dekodieren,
  // bleibt sonst nur das Vorschaubild stehen, ohne jeden Hinweis.
  const VIDEO_ERRORS = {
    1: 'Die Wiedergabe wurde abgebrochen.',
    2: 'Das Video konnte nicht vollständig geladen werden (Netzwerkfehler).',
    3: 'Der Browser kann dieses Video nicht dekodieren. Meist steckt H.265/HEVC darin, das nur wenige Browser abspielen. Abhilfe: in der Galerie auswählen und „Umwandeln“.',
    4: 'Dieses Videoformat unterstützt der Browser nicht. Die Datei selbst ist in Ordnung – nur der Codec darin passt nicht. Abhilfe: in der Galerie auswählen und „Umwandeln“.',
  };
  function videoFailed(e) {
    videoError = VIDEO_ERRORS[e.currentTarget.error?.code] ?? 'Das Video lässt sich nicht abspielen.';
  }

  // Fläche, die das Bild bei object-fit: contain tatsächlich einnimmt
  const frame = $derived.by(() => {
    if (!natural.width || !stageWidth) return null;
    const scale = Math.min(stageWidth / natural.width, stageHeight / natural.height);
    const width = natural.width * scale;
    const height = natural.height * scale;
    return { left: (stageWidth - width) / 2, top: (stageHeight - height) / 2, width, height };
  });

  const item = $derived(items[index]);
  const itemId = $derived(item?.[0]);
  const key = $derived(`${item[0]}-${item[5]}`); // neue Revision (z. B. gedreht) lädt neu
  const isVideo = $derived(item?.[4] === 1);
  const canEdit = $derived(allowed && !trash && detail?.editable);

  // ── Entwurf ────────────────────────────────────────────────────
  const sameList = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
  const savedLocation = $derived(detail && detail.lat !== null ? { lat: detail.lat, lon: detail.lon } : null);
  const persons = $derived(draft.persons ?? detail?.persons ?? []);
  const tags = $derived(draft.tags ?? detail?.tags ?? []);
  const location = $derived('location' in draft ? draft.location : savedLocation);
  const changes = $derived.by(() => {
    if (!detail) return {};
    const result = {};
    if (!sameList(persons, detail.persons)) result.persons = persons;
    if (!sameList(tags, detail.tags)) result.tags = tags;
    if (location?.lat !== savedLocation?.lat || location?.lon !== savedLocation?.lon) result.location = location;
    return result;
  });
  const dirty = $derived(Object.keys(changes).length > 0 || !!personText.trim() || !!tagText.trim());

  function discard() {
    draft = {};
    personText = '';
    tagText = '';
  }

  async function saveDraft() {
    // Namen, die noch ohne Enter im Feld stehen, gehören dazu
    personInput?.commit();
    tagInput?.commit();
    const body = changes;
    if (!Object.keys(body).length) return discard();
    if (await save(() => api.update(itemId, body), 'Gespeichert')) discard();
  }

  /** Blättern oder Schließen: bei ungespeicherten Änderungen erst nachfragen. */
  function leave(action) {
    if (dirty) leaving = action;
    else action();
  }

  // ── Zoom ───────────────────────────────────────────────────────
  // Browser zeigen HEIC/TIFF nicht an; sehr große Originale lohnen das Nachladen nicht
  const HIRES_TYPES = /^image\/(jpeg|png|webp|gif|avif)$/;
  const HIRES_MAX = 60 * 1024 * 1024;
  const zoomed = $derived(view.scale > 1.01);
  const canZoom = $derived(!isVideo && frame !== null && loadedKey === key);
  const stageSize = $derived({ width: stageWidth, height: stageHeight });
  const transform = $derived(zoomed ? `translate(${view.x}px, ${view.y}px) scale(${view.scale})` : null);
  const hiresAllowed = $derived(!isVideo && HIRES_TYPES.test(detail?.mime ?? '') && (detail?.size ?? Infinity) <= HIRES_MAX);

  $effect(() => {
    key; // anderes Bild oder neue Revision: ungezoomt beginnen
    view = RESET;
  });
  $effect(() => {
    if (zoomed && hiresAllowed) hiresFor = key;
  });

  function zoomTo(scale, x, y) {
    if (canZoom) view = zoomAt(view, scale, x, y, frame, stageSize);
  }
  const toggleZoom = (x, y) => (zoomed ? (view = RESET) : zoomTo(2.5, x, y));

  function local(e) {
    const rect = stage.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  // Mausrad und Touchpad-Geste; muss preventDefault können, darum nicht passiv
  $effect(() => {
    if (!stage) return;
    function onwheel(e) {
      if (!canZoom || e.target.closest('.toolbar, .nav')) return;
      e.preventDefault();
      const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY; // Firefox liefert Zeilen
      const [x, y] = local(e);
      zoomTo(view.scale * Math.exp(-delta * 0.002), x, y);
    }
    stage.addEventListener('wheel', onwheel, { passive: false });
    return () => stage.removeEventListener('wheel', onwheel);
  });

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
    videoError = '';
    discard();
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
  const setLabels = (kind, values) => (draft[kind] = values);
  function setDate(value) {
    editDate = false;
    save(() => api.update(itemId, { taken_at: value }), 'Datum gespeichert');
  }
  function setLocation(position) {
    editLocation = false;
    draft.location = position;
  }
  const removeLocation = () => (draft.location = null);

  const go = (step) => {
    const next = index + step;
    if (next >= 0 && next < items.length) leave(() => onnavigate(next));
  };
  const close = () => leave(onclose);

  function keydown(e) {
    if (editDate || editLocation || leaving || e.target.closest?.('input, textarea, .modal')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowRight') go(1);
    else if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'i') toggleInfo();
    else if (e.key === 'f' && !isVideo && !trash) showFaces = !showFaces;
    else if (e.key === 'Delete' && !trash && canDelete) ondelete(itemId);
    else if ((e.key === '+' || e.key === '=') && canZoom) zoomTo(view.scale * 1.5, stageWidth / 2, stageHeight / 2);
    else if (e.key === '-' && canZoom) zoomTo(view.scale / 1.5, stageWidth / 2, stageHeight / 2);
    else if (e.key === '0' && zoomed) view = RESET;
    else return;
    e.preventDefault();
  }

  // Gesten: Wischen blättert (ungezoomt), zwei Finger zoomen, ein Finger bzw. die Maus verschiebt
  // das gezoomte Bild, Doppeltippen zoomt hinein und wieder heraus
  const pointers = new Map(); // pointerId -> [x, y]
  let gesture = null; // { type: swipe | pan | pinch | click, sx, sy, … }
  let lastTap = null;
  const spread = () => {
    const [a, b] = [...pointers.values()];
    return [Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  };

  function pointerdown(e) {
    if (e.target.closest('button, a, input, textarea, form')) return;
    const [x, y] = local(e);
    pointers.set(e.pointerId, [x, y]);
    if (pointers.size === 2 && canZoom) {
      gesture = { type: 'pinch', dist: spread()[0], scale: view.scale };
    } else if (pointers.size === 1) {
      const type = zoomed ? 'pan' : e.pointerType === 'mouse' ? 'click' : 'swipe';
      gesture = { type, sx: x, sy: y, x, y, touch: e.pointerType !== 'mouse' };
      if (type === 'pan') {
        try {
          stage.setPointerCapture(e.pointerId); // Verschieben auch, wenn der Zeiger die Bühne verlässt
        } catch {
          /* Zeiger schon wieder weg */
        }
      }
    }
  }

  function pointermove(e) {
    if (!pointers.has(e.pointerId)) return;
    const [x, y] = local(e);
    pointers.set(e.pointerId, [x, y]);
    if (gesture?.type === 'pinch' && pointers.size === 2) {
      const [dist, cx, cy] = spread();
      zoomTo((gesture.scale * dist) / gesture.dist, cx, cy);
    } else if (gesture?.type === 'pan') {
      view = clampView({ scale: view.scale, x: view.x + x - gesture.x, y: view.y + y - gesture.y }, frame, stageSize);
      gesture.x = x;
      gesture.y = y;
    }
  }

  function pointerup(e) {
    if (!pointers.has(e.pointerId)) return;
    const [x, y] = local(e);
    pointers.delete(e.pointerId);
    const done = gesture;
    if (pointers.size) {
      // Nach dem Zusammenziehen bleibt oft ein Finger liegen: mit ihm weiter verschieben
      const [rest] = pointers.values();
      gesture = zoomed ? { type: 'pan', sx: rest[0], sy: rest[1], x: rest[0], y: rest[1], touch: true, moved: true } : null;
      return;
    }
    gesture = null;
    if (!done || done.type === 'pinch' || e.type === 'pointercancel') return;
    const dx = x - done.sx;
    const dy = y - done.sy;
    if (done.type === 'swipe' && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
      go(dx < 0 ? 1 : -1);
      return;
    }
    // Doppeltippen am Touchscreen; mit der Maus übernimmt das dblclick
    if (done.touch && !done.moved && Math.hypot(dx, dy) < 10) {
      const now = performance.now();
      if (lastTap && now - lastTap.time < 300 && Math.hypot(x - lastTap.x, y - lastTap.y) < 30) {
        toggleZoom(x, y);
        lastTap = null;
      } else {
        lastTap = { time: now, x, y };
      }
    }
  }

  function dblclick(e) {
    if (!canZoom || e.target.closest('button, a, input, form')) return;
    const [x, y] = local(e);
    toggleZoom(x, y);
  }

  const mapLink = (d) => `https://www.openstreetmap.org/?mlat=${d.lat}&mlon=${d.lon}#map=15/${d.lat}/${d.lon}`;
  const expires = (d) => new Date(d.expires_at).toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' });
</script>

<svelte:window onkeydown={keydown} />

<div class="viewer" role="dialog" aria-modal="true" aria-label="Einzelansicht">
  <div
    class="stage"
    class:zoomable={!isVideo}
    class:zoomed
    bind:this={stage}
    bind:clientWidth={stageWidth}
    bind:clientHeight={stageHeight}
    onpointerdown={pointerdown}
    onpointermove={pointermove}
    onpointerup={pointerup}
    onpointercancel={pointerup}
    ondblclick={dblclick}
    role="presentation"
  >
    {#key key}
      {#if isVideo}
        <!-- Kein autoplay: Browser blocken Autostart mit Ton ohnehin, und bei Familienvideos
             will man den Ton hören statt stumm zu starten. -->
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          src={originalUrl(item)}
          poster={previewUrl(item)}
          controls
          playsinline
          preload="metadata"
          onerror={videoFailed}
        ></video>
      {:else}
        {#if loadedKey !== key}<img class="placeholder" src={thumbUrl(item)} alt="" />{/if}
        <img
          class="photo"
          src={previewUrl(item)}
          alt={detail?.name ?? ''}
          style:transform
          draggable="false"
          onload={(e) => {
            loadedKey = key;
            natural = { width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight };
          }}
        />
        {#if hiresFor === key}
          <!-- Beim Hineinzoomen das Original darüberlegen, sobald es geladen ist -->
          <img class="photo hires" class:ready={hiresReady === key} src={originalUrl(item)} alt="" style:transform
            draggable="false" onload={() => (hiresReady = key)} />
        {/if}
      {/if}
    {/key}
    {#if showFaces && !isVideo && !zoomed && frame && loadedKey === key}
      <FaceBoxes
        assetId={itemId}
        revision={item[5]}
        {frame}
        persons={labels.persons}
        editable={allowed}
        onchanged={async () => {
          detail = await api.asset(itemId).catch(() => detail);
          onchanged();
        }}
      />
    {/if}

    {#if videoError}
      <div class="video-error">
        <Icon name="alert" size={22} />
        <p>{videoError}</p>
        <a class="download" href={originalUrl(item, true)}><Icon name="download" size={18} /> Original herunterladen</a>
      </div>
    {/if}

    <div class="toolbar">
      <button class="round" onclick={close} title="Schließen (Esc)"><Icon name="close" /></button>
      <span class="spacer"></span>
      {#if busy}<span class="spinner" title="Wird gespeichert"></span>{/if}
      {#if trash}
        {#if canDelete}<button class="round" onclick={() => onrestore(itemId)} title="Wiederherstellen"><Icon name="restore" /></button>{/if}
        {#if canPurge}<button class="round" onclick={() => onpurge(itemId)} title="Endgültig löschen"><Icon name="deleteForever" /></button>{/if}
      {:else}
        {#if detail?.rotatable && allowed}
          <button class="round" disabled={busy} onclick={() => rotate(270)} title="Nach links drehen"><Icon name="rotate" /></button>
          <button class="round" disabled={busy} onclick={() => rotate(90)} title="Nach rechts drehen"><Icon name="rotate" flip /></button>
        {/if}
        {#if !isVideo}
          <button class="round" class:on={showFaces} onclick={() => (showFaces = !showFaces)} title="Gesichter zeigen (f)"><Icon name="face" /></button>
        {/if}
        <a class="round" href={originalUrl(item, true)} title="Original herunterladen"><Icon name="download" /></a>
        {#if canDelete}<button class="round" disabled={busy} onclick={() => ondelete(itemId)} title="In den Papierkorb (Entf)"><Icon name="delete" /></button>{/if}
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
        {:else if !detail.editable && allowed}
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
            {#if location}
              <a href={mapLink(location)} target="_blank" rel="noopener">{location.lat.toFixed(5)}, {location.lon.toFixed(5)}</a>
            {:else}
              <span class="muted">Kein Aufnahmeort</span>
            {/if}
            {#if canEdit}
              <span class="buttons">
                <button class="icon small" disabled={busy} onclick={() => (editLocation = true)} title={location ? 'Ort ändern' : 'Ort setzen'}>
                  <Icon name="pencil" size={18} />
                </button>
                {#if location}
                  <button class="icon small" disabled={busy} onclick={removeLocation} title="Ort entfernen"><Icon name="close" size={18} /></button>
                {/if}
              </span>
            {/if}
          </dd>

          <dt>Personen</dt>
          <dd>
            {#if canEdit || persons.length}
              <ChipInput
                bind:this={personInput}
                bind:text={personText}
                values={persons}
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
            {#if canEdit || tags.length}
              <ChipInput
                bind:this={tagInput}
                bind:text={tagText}
                values={tags}
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
        {#if canEdit && dirty}
          <div class="draft-bar">
            <span class="muted">Nicht gespeichert</span>
            <button disabled={busy} onclick={discard}>Verwerfen</button>
            <button class="primary" disabled={busy} onclick={saveDraft}>Speichern</button>
          </div>
        {/if}
      {/if}
    </aside>
  {/if}
</div>

{#if editLocation && detail}
  <LocationDialog lat={location?.lat ?? null} lon={location?.lon ?? null} saveLabel="Übernehmen" onsave={setLocation}
    oncancel={() => (editLocation = false)} />
{/if}

{#if leaving}
  <Confirm
    title="Änderungen verwerfen?"
    text="Personen, Schlagworte oder Ort sind geändert, aber noch nicht gespeichert."
    confirmLabel="Verwerfen"
    danger
    onconfirm={() => {
      const action = leaving;
      leaving = null;
      discard();
      action();
    }}
    oncancel={() => (leaving = null)}
  />
{/if}

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
    overflow: hidden;
  }
  /* Bei Fotos übernimmt die Seite alle Gesten selbst (Zoom, Verschieben, Wischen) */
  .stage.zoomable {
    touch-action: none;
  }
  .stage.zoomed {
    cursor: grab;
  }
  .stage.zoomed:active {
    cursor: grabbing;
  }
  .photo {
    transform-origin: 0 0;
    will-change: transform;
  }
  .hires {
    opacity: 0;
    transition: opacity 0.2s;
  }
  .hires.ready {
    opacity: 1;
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
  .video-error {
    position: absolute;
    left: 50%;
    bottom: 96px;
    transform: translateX(-50%);
    display: grid;
    justify-items: center;
    gap: 8px;
    width: min(420px, calc(100% - 32px));
    padding: 16px;
    border-radius: 10px;
    background: rgb(0 0 0 / 0.82);
    color: #fff;
    text-align: center;
    z-index: 2;
  }
  .video-error p {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.45;
  }
  .video-error .download {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #fff;
    font-size: 0.9rem;
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
  .buttons {
    display: flex;
    flex: none;
  }
  dd.row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  .draft-bar {
    position: sticky;
    bottom: -20px; /* bündig mit dem Innenabstand von .info */
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 20px -20px -20px;
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: var(--surface);
  }
  .draft-bar span {
    flex: 1;
    font-size: 0.85rem;
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
      /* feste Höhe: sonst ändert sich mit jedem Bild die Höhe der Bühne, und die Pfeile wandern mit */
      height: 45vh;
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
