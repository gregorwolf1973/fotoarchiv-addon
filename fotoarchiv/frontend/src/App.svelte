<script>
  import { onMount } from 'svelte';
  import { api } from './lib/api.js';
  import { formatBytes, formatNumber } from './lib/format.js';
  import Gallery from './components/Gallery.svelte';
  import Icon from './components/Icon.svelte';
  import ImportPanel from './components/ImportPanel.svelte';
  import Uploader from './components/Uploader.svelte';
  import Viewer from './components/Viewer.svelte';

  let info = $state(null);
  let items = $state.raw([]); // groß und unveränderlich: kein tiefer Proxy
  let loaded = $state(false);
  let failure = $state('');
  let openIndex = $state(-1);
  let showImport = $state(false);
  let uploader = $state();
  let fileInput = $state();
  let revision = null;

  const missingTools = $derived(
    info ? Object.entries({ libvips: info.tools.vips, exiftool: info.tools.exiftool, ffmpeg: info.tools.ffmpeg })
      .filter(([, ok]) => !ok).map(([name]) => name) : [],
  );

  async function refresh() {
    try {
      info = await api.state();
      if (info.revision !== revision) {
        const index = await api.index();
        revision = index.revision;
        items = index.items;
        if (openIndex >= items.length) openIndex = -1;
      }
      failure = '';
    } catch (e) {
      failure = e.message;
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    let timer;
    const tick = async () => {
      await refresh();
      timer = setTimeout(tick, info?.importing ? 2000 : 20000);
    };
    tick();
    return () => clearTimeout(timer);
  });

  function pickFiles(e) {
    uploader.add([...e.currentTarget.files]);
    e.currentTarget.value = '';
  }
</script>

<div class="app">
  <header class="topbar">
    <div class="brand">
      <Icon name="images" size={26} />
      <h1>Fotoarchiv</h1>
      {#if info}
        <span class="stats">
          {formatNumber(info.counts.images)} Fotos · {formatNumber(info.counts.videos)} Videos · {formatBytes(info.counts.bytes)}
        </span>
      {/if}
    </div>
    <div class="actions">
      {#if info?.importing}<span class="busy" title="Import läuft"></span>{/if}
      <button onclick={() => fileInput.click()} title="Dateien hochladen">
        <Icon name="upload" size={20} /><span class="label">Hochladen</span>
      </button>
      <button onclick={() => (showImport = true)} title="Aus Ordner importieren">
        <Icon name="import" size={20} /><span class="label">Importieren</span>
      </button>
      <input bind:this={fileInput} type="file" multiple accept="image/*,video/*,.heic,.heif" hidden onchange={pickFiles} />
    </div>
  </header>

  {#if failure}
    <div class="banner error"><Icon name="alert" size={18} /> Server nicht erreichbar: {failure}</div>
  {/if}
  {#if missingTools.length}
    <div class="banner"><Icon name="alert" size={18} /> Fehlende Programme im Add-on: {missingTools.join(', ')}</div>
  {/if}

  {#if items.length}
    <Gallery {items} onopen={(i) => (openIndex = i)} />
  {:else if loaded && info}
    <div class="empty">
      <Icon name="images" size={64} />
      <h2>Noch keine Fotos</h2>
      <p>Dateien einfach hierher ziehen, über <strong>Hochladen</strong> auswählen oder in den Import-Ordner legen:</p>
      <code>{info.import_dir}</code>
      <button class="primary" onclick={() => (showImport = true)}><Icon name="import" size={20} /> Import öffnen</button>
    </div>
  {/if}
</div>

{#if openIndex >= 0 && items[openIndex]}
  <Viewer {items} index={openIndex} onclose={() => (openIndex = -1)} onnavigate={(i) => (openIndex = i)} />
{/if}

{#if showImport && info}
  <ImportPanel {info} onclose={() => (showImport = false)} onchanged={refresh} />
{/if}

<Uploader bind:this={uploader} onchanged={refresh} />

<style>
  .app {
    height: 100vh;
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }
  .topbar {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    height: 56px;
    padding: 0 12px 0 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    color: var(--accent);
  }
  h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 500;
    color: var(--text);
  }
  .stats {
    color: var(--muted);
    font-size: 0.875rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .busy {
    width: 18px;
    height: 18px;
    border: 2px solid var(--accent);
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--warning-bg);
    color: var(--text);
    font-size: 0.9rem;
  }
  .banner.error {
    background: var(--danger-bg);
  }
  .empty {
    flex: 1;
    display: grid;
    align-content: center;
    justify-items: center;
    gap: 12px;
    padding: 24px;
    text-align: center;
    color: var(--muted);
  }
  .empty h2 {
    margin: 0;
    color: var(--text);
    font-weight: 500;
  }
  .empty p {
    margin: 0;
    max-width: 420px;
    line-height: 1.5;
  }
  .empty code {
    padding: 4px 8px;
    border-radius: 4px;
    background: var(--chip);
    color: var(--text);
  }
  @media (max-width: 639px) {
    .stats,
    .label {
      display: none;
    }
    .topbar {
      padding: 0 8px 0 12px;
    }
  }
</style>
