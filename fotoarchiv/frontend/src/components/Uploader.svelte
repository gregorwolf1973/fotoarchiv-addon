<script>
  import { SUPPORTED, upload } from '../lib/api.js';
  import Icon from './Icon.svelte';

  let { enabled = true, onchanged } = $props();

  const PARALLEL = 2;
  const LABELS = {
    waiting: 'wartet',
    uploading: 'lädt hoch',
    imported: 'importiert',
    duplicate: 'Duplikat',
    damaged: 'beschädigt',
    skipped: 'übersprungen',
    error: 'Fehler',
  };

  let dragging = $state(false);
  let queue = $state([]);
  let active = 0;
  let depth = 0;

  const done = $derived(queue.filter((e) => !['waiting', 'uploading'].includes(e.status)).length);
  const summary = $derived.by(() => {
    const count = (s) => queue.filter((e) => e.status === s).length;
    return {
      imported: count('imported'),
      similar: queue.filter((e) => e.similar).length,
      duplicate: count('duplicate'),
      failed: count('error') + count('skipped') + count('damaged'),
    };
  });

  /** Dateien oder (per Drag & Drop) ganze Ordner hinzufügen. */
  export function add(files) {
    for (const file of files) {
      const supported = SUPPORTED.test(file.name);
      queue.push({
        file,
        name: file.name,
        status: supported ? 'waiting' : 'skipped',
        message: supported ? '' : 'Dateityp wird nicht unterstützt',
        progress: 0,
      });
    }
    pump();
  }

  function pump() {
    while (active < PARALLEL) {
      const entry = queue.find((e) => e.status === 'waiting');
      if (!entry) break;
      active++;
      entry.status = 'uploading';
      upload(entry.file, (p) => (entry.progress = p)).then((result) => {
        entry.status = result.status;
        entry.similar = Boolean(result.similar);
        entry.message =
          result.status === 'duplicate' ? `schon vorhanden: ${result.existing}`
          : result.similar ? `sehr ähnlich zu: ${result.similar}`
          : result.message;
        entry.file = null;
        active--;
        pump();
        if (!queue.some((e) => ['waiting', 'uploading'].includes(e.status))) onchanged();
      });
    }
  }

  function clear() {
    if (queue.some((e) => ['waiting', 'uploading'].includes(e.status))) return;
    queue = [];
  }

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
      <p>Zum Hochladen loslassen</p>
      <small>Fotos, Videos oder ganze Ordner – Duplikate werden erkannt</small>
    </div>
  </div>
{/if}

{#if queue.length}
  <div class="toast" role="status">
    <header>
      <strong>Hochladen · {done} / {queue.length}</strong>
      {#if done === queue.length}
        <button class="icon small" onclick={clear} title="Schließen"><Icon name="close" size={18} /></button>
      {/if}
    </header>
    {#if done === queue.length}
      <p class="summary">
        {summary.imported} importiert{#if summary.similar} ({summary.similar} sehr ähnlich zu vorhandenen){/if}{#if summary.duplicate}, {summary.duplicate} Duplikate{/if}{#if summary.failed}, {summary.failed} nicht importiert{/if}
      </p>
    {/if}
    <ul>
      {#each queue as entry}
        <li class={entry.status} class:similar={entry.similar}>
          <span class="name" title={entry.name}>{entry.name}</span>
          {#if entry.status === 'uploading'}
            <span class="bar"><span style:width="{Math.round(entry.progress * 100)}%"></span></span>
          {:else}
            <span class="state" title={entry.message}>{entry.similar ? 'ähnlich' : (LABELS[entry.status] ?? entry.status)}</span>
          {/if}
        </li>
      {/each}
    </ul>
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
    min-height: 44px;
    padding: 0 8px 0 16px;
    border-bottom: 1px solid var(--border);
  }
  .summary {
    margin: 0;
    padding: 10px 16px 0;
    font-size: 0.9rem;
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
    align-items: center;
    gap: 10px;
    padding: 3px 0;
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
  .skipped .state {
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
