<script>
  import { api, SUPPORTED, upload } from '../lib/api.js';
  import Icon from './Icon.svelte';
  import { t, tServer } from '../lib/i18n.js';

  let { enabled = true, onchanged } = $props();

  const PARALLEL = 2;
  const CHECK_BATCH = 1000;
  const LABELS = {
    checking: t('prüft'),
    waiting: t('wartet'),
    uploading: t('lädt hoch'),
    imported: t('importiert'),
    duplicate: t('schon da'),
    damaged: t('beschädigt'),
    skipped: t('übersprungen'),
    cancelled: t('abgebrochen'),
    error: t('Fehler'),
  };
  const OPEN = ['checking', 'waiting', 'uploading'];
  const FAILED = ['error', 'damaged', 'skipped'];

  let dragging = $state(false);
  let queue = $state([]);
  // Am Handy nur eine schmale Leiste, damit man während des Hochladens weiterblättern kann
  let collapsed = $state(window.innerWidth < 640);
  let startedAt = $state(0);
  let now = $state(Date.now());
  let active = 0;
  let depth = 0;

  const running = $derived(queue.some((e) => OPEN.includes(e.status)));
  const retryable = $derived(queue.some((e) => e.status === 'error' && e.file));
  const done = $derived(queue.filter((e) => !OPEN.includes(e.status)).length);
  const summary = $derived.by(() => {
    const count = (s) => queue.filter((e) => e.status === s).length;
    return {
      imported: count('imported'),
      similar: queue.filter((e) => e.similar).length,
      duplicate: count('duplicate'),
      cancelled: count('cancelled'),
      failed: count('error') + count('skipped') + count('damaged'),
    };
  });
  // Nur was wirklich übertragen wird, zählt für Fortschritt und Restzeit
  const bytes = $derived.by(() => {
    let total = 0;
    let sent = 0;
    for (const e of queue) {
      if (!e.transfer) continue;
      total += e.size;
      sent += e.status === 'uploading' ? e.size * e.progress : e.status === 'waiting' ? 0 : e.size;
    }
    return { total, sent };
  });
  const percent = $derived(bytes.total ? Math.floor((bytes.sent / bytes.total) * 100) : 0);
  const remaining = $derived.by(() => {
    const elapsed = (now - startedAt) / 1000;
    if (!running || !startedAt || elapsed < 5 || !bytes.sent) return '';
    const seconds = ((bytes.total - bytes.sent) / bytes.sent) * elapsed;
    if (seconds < 60) return t('noch unter 1 Min.');
    const minutes = Math.round(seconds / 60);
    return minutes < 60 ? t('noch ca. {minutes} Min.', { minutes }) : t('noch ca. {hours} Std. {minutes} Min.', { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
  });

  /** Dateien oder (per Drag & Drop) ganze Ordner hinzufügen. */
  export function add(files) {
    const fresh = [];
    for (const file of files) {
      const supported = SUPPORTED.test(file.name);
      queue.push({
        file,
        name: file.name,
        size: file.size,
        status: supported ? 'checking' : 'skipped',
        message: supported ? '' : t('Dateityp wird nicht unterstützt'),
        progress: 0,
        transfer: false, // wird wirklich übertragen (nicht vorab als vorhanden erkannt)
        controller: null,
      });
      if (supported) fresh.push(queue[queue.length - 1]);
    }
    check(fresh);
  }

  /** Vorab fragen, was das Archiv schon hat – das muss das Handy nicht stundenlang hochladen. */
  async function check(entries) {
    for (let i = 0; i < entries.length; i += CHECK_BATCH) {
      const part = entries.slice(i, i + CHECK_BATCH);
      let known = [];
      try {
        known = (await api.knownFiles(part.map((e) => ({ name: e.name, size: e.size })))).known;
      } catch {
        /* Prüfung nicht möglich: dann eben hochladen, der Server erkennt Duplikate trotzdem */
      }
      part.forEach((entry, j) => {
        if (entry.status !== 'checking') return; // inzwischen abgebrochen
        if (known[j]) {
          entry.status = 'duplicate';
          entry.message = t('schon im Archiv – nicht erneut hochgeladen');
          entry.file = null;
        } else {
          entry.status = 'waiting';
          entry.transfer = true;
        }
      });
      pump();
    }
    finishIfDone();
  }

  function pump() {
    while (active < PARALLEL) {
      const entry = queue.find((e) => e.status === 'waiting');
      if (!entry) break;
      active++;
      if (!startedAt) startedAt = Date.now();
      entry.status = 'uploading';
      entry.controller = new AbortController();
      upload(entry.file, (p) => (entry.progress = p), entry.controller.signal).then((result) => {
        entry.status = result.status;
        entry.similar = Boolean(result.similar);
        entry.message =
          result.status === 'duplicate' ? t('schon vorhanden: {name}', { name: result.existing })
          : result.similar ? t('sehr ähnlich zu: {name}', { name: result.similar })
          : tServer(result.message);
        // Bei einem Fehler die Datei behalten: "Erneut versuchen" schickt sie noch einmal
        if (result.status !== 'error') entry.file = null;
        entry.controller = null;
        active--;
        pump();
        finishIfDone();
      });
    }
  }

  function finishIfDone() {
    if (queue.length && !queue.some((e) => OPEN.includes(e.status))) {
      startedAt = 0;
      onchanged();
    }
  }

  function cancel() {
    for (const entry of queue) {
      if (entry.status === 'waiting' || entry.status === 'checking') {
        entry.status = 'cancelled';
        entry.file = null;
      } else if (entry.status === 'uploading') {
        entry.controller?.abort();
      }
    }
  }

  function retry() {
    for (const entry of queue) {
      if (entry.status === 'error' && entry.file) {
        entry.status = 'waiting';
        entry.message = '';
        entry.progress = 0;
      }
    }
    pump();
  }

  function clear() {
    if (running) return;
    queue = [];
  }

  // Während des Hochladens: Restzeit auffrischen, Bildschirm anlassen, vor dem Schließen warnen
  $effect(() => {
    if (!running) return;
    const timer = setInterval(() => (now = Date.now()), 1000);
    let lock = null;
    const keepAwake = async () => {
      try {
        if (document.visibilityState === 'visible' && 'wakeLock' in navigator) {
          lock = await navigator.wakeLock.request('screen');
        }
      } catch {
        /* nicht erlaubt oder nicht unterstützt: dann eben ohne */
      }
    };
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    keepAwake();
    document.addEventListener('visibilitychange', keepAwake);
    window.addEventListener('beforeunload', warn);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', keepAwake);
      window.removeEventListener('beforeunload', warn);
      lock?.release().catch(() => {});
    };
  });

  async function collect(dataTransfer) {
    // webkitGetAsEntry muss synchron im Drop-Ereignis aufgerufen werden
    const entries = [...dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
    if (!entries.length) return [...dataTransfer.files];
    const files = [];
    async function walk(entry) {
      if (entry.isFile) {
        files.push(await new Promise((resolve, reject) => entry.file(resolve, reject)));
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        let batch;
        do {
          batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
          for (const child of batch) await walk(child);
        } while (batch.length);
      }
    }
    for (const entry of entries) await walk(entry);
    return files;
  }

  const hasFiles = (e) => enabled && e.dataTransfer?.types?.includes('Files');
</script>

<svelte:window
  ondragenter={(e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth++;
    dragging = true;
  }}
  ondragover={(e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }}
  ondragleave={(e) => {
    if (!hasFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (!depth) dragging = false;
  }}
  ondrop={async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    dragging = false;
    add(await collect(e.dataTransfer));
  }}
/>

{#if dragging}
  <div class="dropzone">
    <div>
      <Icon name="upload" size={56} />
      <p>{t('Zum Hochladen loslassen')}</p>
      <small>{t('Fotos, Videos oder ganze Ordner – Duplikate werden erkannt')}</small>
    </div>
  </div>
{/if}

{#if queue.length}
  <div class="toast" class:collapsed role="status">
    <header>
      <button class="head" onclick={() => (collapsed = !collapsed)} title={collapsed ? t('Liste zeigen') : t('Liste ausblenden')}>
        <strong>{t('Hochladen · {done} / {total}', { done, total: queue.length })}</strong>
        <span class="meta">
          {#if running}
            {percent} %{#if remaining} · {remaining}{/if}
          {:else}
            {t('fertig')}
          {/if}
        </span>
      </button>
      {#if running}
        <button class="text" onclick={cancel}>{t('Abbrechen')}</button>
      {:else}
        {#if retryable}
          <button class="text" onclick={retry} title={t('Fehlgeschlagene Dateien noch einmal hochladen')}>{t('Erneut versuchen')}</button>
        {/if}
        <button class="icon small" onclick={clear} title={t('Schließen')}><Icon name="close" size={18} /></button>
      {/if}
    </header>
    {#if running}
      <div class="total"><span style:width="{percent}%"></span></div>
    {:else}
      <p class="summary">
        {t('{n} importiert', { n: summary.imported })}{#if summary.similar} ({t('{n} sehr ähnlich zu vorhandenen', { n: summary.similar })}){/if}{#if summary.duplicate}, {t('{n} schon vorhanden', { n: summary.duplicate })}{/if}{#if summary.cancelled}, {t('{n} abgebrochen', { n: summary.cancelled })}{/if}{#if summary.failed}, {t('{n} nicht importiert', { n: summary.failed })}{/if}
      </p>
    {/if}
    {#if !collapsed}
      <ul>
        {#each queue as entry}
          <li class={entry.status} class:similar={entry.similar}>
            <span class="name" title={entry.name}>{entry.name}</span>
            {#if entry.status === 'uploading'}
              <span class="bar"><span style:width="{Math.round(entry.progress * 100)}%"></span></span>
            {:else}
              <span class="state" title={entry.message}>{entry.similar ? t('ähnlich') : (LABELS[entry.status] ?? entry.status)}</span>
            {/if}
            {#if entry.message && FAILED.includes(entry.status)}
              <!-- Am Handy gibt es keinen Tooltip: den Grund direkt zeigen -->
              <small class="reason">{entry.message}</small>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .dropzone {
    position: fixed;
    inset: 0;
    z-index: 60;
    display: grid;
    place-items: center;
    padding: 24px;
    background: rgb(0 0 0 / 0.55);
    pointer-events: none;
  }
  .dropzone > div {
    display: grid;
    justify-items: center;
    gap: 4px;
    padding: 48px 64px;
    border: 3px dashed var(--accent);
    border-radius: 16px;
    background: var(--surface);
    color: var(--text);
    text-align: center;
  }
  .dropzone p {
    margin: 8px 0 0;
    font-size: 1.25rem;
    font-weight: 500;
  }
  .dropzone small {
    color: var(--muted);
  }
  .toast {
    position: fixed;
    right: 80px;
    bottom: 16px;
    z-index: 45;
    width: min(360px, calc(100vw - 32px));
    max-height: 50vh;
    display: flex;
    flex-direction: column;
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.3);
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    min-height: 44px;
    padding: 0 8px 0 0;
    border-bottom: 1px solid var(--border);
  }
  .collapsed header {
    border-bottom: 0;
  }
  .head {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0;
    padding: 6px 0 6px 16px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .meta {
    font-size: 0.8rem;
    color: var(--muted);
  }
  button.text {
    flex: none;
    min-height: 32px;
    padding: 0 12px;
    font-size: 0.85rem;
  }
  .total {
    height: 4px;
    background: var(--chip);
  }
  .total span {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 0.4s;
  }
  .summary {
    margin: 0;
    padding: 8px 16px 10px;
    font-size: 0.9rem;
  }
  .collapsed .summary {
    padding-top: 0;
  }
  ul {
    margin: 0;
    padding: 8px 16px 12px;
    list-style: none;
    overflow-y: auto;
    font-size: 0.875rem;
  }
  li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 10px;
    padding: 3px 0;
  }
  .reason {
    flex-basis: 100%;
    color: var(--muted);
    font-size: 0.8rem;
    overflow-wrap: anywhere;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .state {
    flex: none;
    color: var(--muted);
  }
  .imported .state {
    color: var(--success);
  }
  .similar .state,
  .duplicate .state {
    color: var(--warning);
  }
  .error .state,
  .skipped .state,
  .cancelled .state {
    color: var(--danger);
  }
  .bar {
    flex: none;
    width: 80px;
    height: 6px;
    border-radius: 3px;
    background: var(--chip);
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  @media (max-width: 639px) {
    .toast {
      right: 16px;
    }
  }
</style>
