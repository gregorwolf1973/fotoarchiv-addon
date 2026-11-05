<script>
  import { t, tServer } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { formatBytes, formatNumber } from '../lib/format.js';
  import Icon from './Icon.svelte';

  let { revision } = $props();

  let status = $state(null);

  const busy = $derived(['starting', 'downloading', 'loading', 'scanning'].includes(status?.status));
  const percent = $derived.by(() => {
    if (!status) return 0;
    if (status.status === 'downloading') return status.download_total ? Math.round((status.download_done / status.download_total) * 100) : 0;
    return status.images ? Math.round((status.scanned / status.images) * 100) : 100;
  });

  async function load() {
    try {
      status = await api.faceStatus();
    } catch {
      /* Anzeige ist nur Zusatz */
    }
  }

  $effect(() => {
    revision;
    load();
  });

  // Download und Scan melden Fortschritt ohne Revisionswechsel: öfter nachfragen
  $effect(() => {
    if (!busy) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  });
</script>

{#if status}
  <div class="status" class:error={status.status === 'error'}>
    <Icon name={status.status === 'error' ? 'alert' : 'face'} size={20} />
    <div class="text">
      {#if !status.enabled}
        {t('Die Gesichtserkennung ist in den Add-on-Einstellungen ausgeschaltet')} (<code>face_recognition</code>).
      {:else if status.status === 'error'}
        {t('Gesichtserkennung gestört: {message}', { message: tServer(status.message) })}
      {:else if status.status === 'downloading'}
        {t('Erkennungsmodelle werden heruntergeladen: {done} von {total}', { done: formatBytes(status.download_done), total: formatBytes(status.download_total) })}
      {:else if status.status === 'starting' || status.status === 'loading'}
        {t('Gesichtserkennung startet …')}
      {:else if status.scanned < status.images}
        {t('{scanned} von {images} Fotos nach Gesichtern durchsucht', { scanned: formatNumber(status.scanned), images: formatNumber(status.images) })}
        <span class="muted">· {t('läuft im Hintergrund, dauert auf dem Raspberry Pi etwa 1 Sekunde pro Foto')}</span>
      {:else}
        {t('Alle {images} Fotos durchsucht · {faces} Gesichter', { images: formatNumber(status.images), faces: formatNumber(status.faces) })}
        {#if status.pending_files}<span class="muted">· {t('{n} Fotos warten aufs Beschriften', { n: formatNumber(status.pending_files) })}</span>{/if}
      {/if}
      {#if busy || (status.enabled && status.scanned < status.images && status.status !== 'error')}
        <div class="bar"><div style:width="{percent}%"></div></div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .status {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 12px 16px;
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.08);
  }
  .status.error {
    background: var(--danger-bg);
  }
  .status > :global(svg) {
    color: var(--accent);
    margin-top: 1px;
  }
  .text {
    flex: 1;
    line-height: 1.45;
  }
  .muted {
    color: var(--muted);
  }
  .bar {
    height: 6px;
    margin-top: 8px;
    border-radius: 3px;
    background: var(--chip);
    overflow: hidden;
  }
  .bar div {
    height: 100%;
    background: var(--accent);
    transition: width 0.4s;
  }
</style>
