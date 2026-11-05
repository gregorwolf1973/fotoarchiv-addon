<script>
  import { api } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { locale, t, tServer } from '../lib/i18n.js';
  import Confirm from './Confirm.svelte';
  import Icon from './Icon.svelte';
  import ImportHilfe from './ImportHilfe.svelte';

  // ontask(task): Hintergrundaufgabe an die App zur Verfolgung übergeben
  // onshowrecent(): Fenster schließen und die zuletzt eingelesenen Fotos zeigen
  let { info, onclose, onchanged, ontask, onshowrecent } = $props();

  let job = $state(null);
  let error = $state('');
  let confirmRemove = $state(false);
  let deep = $state(false); // Abgleich mit gründlicher Prüfung jeder Datei
  const count = (key) => formatNumber(job?.counts[key] ?? 0);
  const plural = (key, one, many) => ((job?.counts[key] ?? 0) === 1 ? one : many);

  const sambaPath = $derived.by(() => {
    const m = /^\/(share|media)\/(.*)$/.exec(info.import_dir);
    return m ? `\\\\homeassistant\\${m[1]}\\${m[2].replaceAll('/', '\\')}` : null;
  });
  const percent = $derived(job?.total ? Math.round((job.done / job.total) * 100) : 0);
  const finished = $derived(job?.finished_at ? new Date(job.finished_at).toLocaleString(locale) : null);

  async function refresh() {
    const wasRunning = job?.running;
    try {
      job = await api.importStatus();
      error = '';
    } catch (e) {
      error = e.message;
    }
    if (wasRunning && !job?.running) onchanged();
  }

  $effect(() => {
    refresh();
    const timer = setInterval(refresh, 1000);
    return () => clearInterval(timer);
  });

  async function start(mode) {
    try {
      await api.startImport(mode, mode === 'library' && deep);
      await refresh();
    } catch (e) {
      error = e.message;
    }
  }

  async function cancel() {
    try {
      await api.cancelImport();
      await refresh();
    } catch (e) {
      error = e.message;
    }
  }

  async function removeMissing() {
    confirmRemove = false;
    try {
      ontask(await api.removeMissing());
      onclose();
    } catch (e) {
      error = e.message;
    }
  }

  function copySambaPath() {
    navigator.clipboard?.writeText(sambaPath);
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && !confirmRemove && onclose()} />

<div class="backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="import-title">
    <header>
      <h2 id="import-title">{t('Importieren')}</h2>
      <button class="icon" onclick={onclose} title={t('Schließen')}><Icon name="close" /></button>
    </header>

    <ImportHilfe admin importDir={info.import_dir} />
    <section>
      <h3>{t('Aus dem Import-Ordner')}</h3>
      <p>
        {t('Fotos und Videos in diesen Ordner legen (Unterordner sind erlaubt) und dann den Import starten. Die Dateien werden nach Aufnahmedatum in die Bibliothek verschoben.')}
      </p>
      <div class="path">
        <code>{info.import_dir}</code>
        {#if sambaPath}
          <span class="muted">Samba:</span>
          <code>{sambaPath}</code>
          <button class="icon small" onclick={copySambaPath} title={t('Samba-Pfad kopieren')}><Icon name="copy" size={16} /></button>
        {/if}
      </div>
      <button class="primary" disabled={job?.running} onclick={() => start('import')}>
        <Icon name="import" size={20} /> {t('Import starten')}
      </button>
    </section>

    <section>
      <h3>{t('Bibliothek abgleichen')}</h3>
      <p>
        {t('Vergleicht das Archiv mit den Dateien in')} <code>{info.library}</code>{t(': Neue Dateien werden ohne Verschieben aufgenommen, von Hand verschobene oder umbenannte Dateien werden ihrem Eintrag wieder zugeordnet, und Einträge, deren Datei gelöscht wurde, werden aufgelistet.')}
      </p>
      <label class="check">
        <input type="checkbox" bind:checked={deep} disabled={job?.running} />
        <span>
          <strong>{t('Dateien gründlich prüfen')}</strong> {t('– liest jede Datei vollständig und vergleicht sie mit der gespeicherten Prüfsumme. Findet abgeschnittene Fotos und Videos und Dateien, die auf dem Datenträger kaputtgegangen sind. Dauert auf dem Raspberry Pi mehrere Stunden, lässt sich abbrechen.')}
        </span>
      </label>
      <button disabled={job?.running} onclick={() => start('library')}>
        {deep ? t('Abgleichen und prüfen') : t('Bibliothek abgleichen')}
      </button>
    </section>

    {#if error}<p class="error">{error}</p>{/if}

    {#if job?.running}
      <section class="progress">
        <div class="bar"><div style:width="{percent}%"></div></div>
        <div class="line">
          <span>{t('{done} von {total} Dateien', { done: formatNumber(job.done), total: formatNumber(job.total) })}</span>
          <span>{percent} %</span>
        </div>
        {#if job.current}<div class="current muted">{job.current}</div>{/if}
        {#if job.deep}<button class="cancel" onclick={cancel}>{t('Prüfung abbrechen')}</button>{/if}
      </section>
    {/if}

    {#if job && (job.running || job.finished_at)}
      <section class="report">
        <h3>{job.running ? t('Bisher') : t('Letzter Lauf · {finished}', { finished })}{job.auto ? ' · ' + t('automatisch') : ''}</h3>
        <div class="counts">
          <span class="count ok">{t('{n} neu', { n: count('imported') })}</span>
          {#if job.counts.relinked}<span class="count ok">{t('{n} wieder zugeordnet', { n: count('relinked') })}</span>{/if}
          <span class="count warn">{t('{n} Duplikate', { n: count('duplicate') })}</span>
          {#if job.counts.damaged}<span class="count bad">{t('{n} beschädigt', { n: count('damaged') })}</span>{/if}
          {#if job.deep}<span class="count ok">{t('{n} geprüft', { n: count('checked') })}</span>{/if}
          {#if job.counts.changed}<span class="count warn">{t('{n} verändert', { n: count('changed') })}</span>{/if}
          {#if job.counts.similar}<span class="count warn">{t('{n} sehr ähnlich', { n: count('similar') })}</span>{/if}
          <span class="count">{t('{n} übersprungen', { n: count('skipped') })}</span>
          <span class="count bad">{t('{n} Fehler', { n: count('error') })}</span>
          {#if job.mode === 'library' && !job.running}<span class="count" class:bad={job.counts.missing}>{count('missing')} {plural('missing', t('Datei fehlt'), t('Dateien fehlen'))}</span>{/if}
        </div>
        {#if job.mode === 'import' && !job.running && job.counts.imported}
          <button onclick={onshowrecent}><Icon name="recent" size={18} /> {t('Eingelesene ansehen')}</button>
        {/if}
        {#if job.mode === 'library' && !job.running && job.counts.missing}
          <div class="missing">
            <p>
              {t('Für')} <strong>{count('missing')}</strong> {plural('missing', t('Eintrag'), t('Einträge'))} {t('liegt keine Datei mehr in der Bibliothek – vermutlich außerhalb des Fotoarchivs gelöscht. Taucht die Datei später wieder auf, wird sie beim nächsten Abgleich oder Import automatisch wieder zugeordnet.')}
            </p>
            <button class="danger" onclick={() => (confirmRemove = true)}>
              <Icon name="deleteForever" size={18} /> {t('Fehlende Einträge entfernen')}
            </button>
          </div>
          <details>
            <summary>{t('Fehlende Dateien')}</summary>
            <ul>
              {#each job.missing as entry}<li>{entry.name}</li>{/each}
            </ul>
          </details>
        {/if}
        {#if job.relinked?.length}
          <details>
            <summary>{t('Wieder zugeordnet')}</summary>
            <ul>
              {#each job.relinked as entry}
                <li><span>{entry.name}</span> <span class="muted">{t('← vorher {name}', { name: entry.existing })}</span></li>
              {/each}
            </ul>
          </details>
        {/if}
        {#if job.duplicates.length}
          <details>
            <summary>{t('Duplikate')}</summary>
            {#if job.auto}
              <p class="muted">{t('Liegen schon im Archiv oder im Papierkorb – die Kopien im Import-Ordner wurden gelöscht.')}</p>
            {:else if job.mode === 'import'}
              <p class="muted">{t('Verschoben nach')} <code>_duplikate</code> {t('im Import-Ordner. Dort prüfen und löschen.')}</p>
            {/if}
            <ul>
              {#each job.duplicates as entry}
                <li><span>{entry.name}</span> <span class="muted">= {entry.existing} ({tServer(entry.message)})</span></li>
              {/each}
            </ul>
          </details>
        {/if}
        {#if job.cancelled}
          <p class="muted">{t('Die Prüfung wurde abgebrochen. Bis dahin gefundene Befunde sind gespeichert.')}</p>
        {/if}
        {#if job.damaged?.length}
          <details open>
            <summary>{t('Beschädigt')}</summary>
            {#if job.mode === 'library'}
              <p class="muted">
                {t('Im Archiv, aber nicht vollständig lesbar. Alle Befunde stehen unter')} <strong>{t('Speicherplatz → Beschädigt')}</strong>. {t('Gibt es das Original noch, den Eintrag löschen und das Original neu importieren.')}
              </p>
            {:else}
              <p class="muted">
                {t('Nicht ins Archiv übernommen, meist weil das Kopieren abgebrochen ist. Verschoben nach')} <code>_defekt</code>
                {t('im Import-Ordner – die Datei noch einmal vom Original kopieren.')}
              </p>
            {/if}
            <ul>
              {#each job.damaged as entry}<li><span>{entry.name}</span> <span class="error">{tServer(entry.message)}</span></li>{/each}
            </ul>
          </details>
        {/if}
        {#if job.similar?.length}
          <details>
            <summary>{t('Sehr ähnlich zu vorhandenen Fotos')}</summary>
            <p class="muted">{t('Importiert, aber vermutlich schon in anderer Fassung vorhanden. Prüfen unter')} <strong>{t('Doppelte Fotos')}</strong>.</p>
            <ul>
              {#each job.similar as entry}
                <li><span>{entry.name}</span> <span class="muted">≈ {entry.existing}</span></li>
              {/each}
            </ul>
          </details>
        {/if}
        {#if job.changed?.length}
          <details>
            <summary>{t('Außerhalb verändert')}</summary>
            <p class="muted">
              {t('Der Inhalt passt nicht mehr zur gespeicherten Prüfsumme. Das ist in Ordnung, wenn du die Datei mit einem anderen Programm bearbeitet hast – sonst ein Hinweis auf einen Fehler des Datenträgers. Wird nur einmal gemeldet.')}
            </p>
            <ul>
              {#each job.changed as entry}<li><span>{entry.name}</span></li>{/each}
            </ul>
          </details>
        {/if}
        {#if job.errors.length}
          <details open>
            <summary>{t('Fehler')}</summary>
            <ul>
              {#each job.errors as entry}<li><span>{entry.name}</span> <span class="error">{tServer(entry.message)}</span></li>{/each}
            </ul>
          </details>
        {/if}
        {#if job.skipped.length}
          <details>
            <summary>{t('Übersprungen')}</summary>
            <ul>
              {#each job.skipped as entry}<li><span>{entry.name}</span> <span class="muted">{tServer(entry.message)}</span></li>{/each}
            </ul>
          </details>
        {/if}
      </section>
    {/if}
  </div>
</div>

{#if confirmRemove}
  <Confirm
    title={t('Fehlende Einträge entfernen?')}
    text={t('Die Einträge werden aus dem Archiv entfernt, samt Schlagworten und Personen. Dateien werden dabei nicht angefasst – es werden nur Einträge gelöscht, deren Datei beim Entfernen weiterhin fehlt.')}
    confirmLabel={t('Einträge entfernen')}
    danger
    onconfirm={removeMissing}
    oncancel={() => (confirmRemove = false)}
  />
{/if}

<style>
  .check {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 4px 0 12px;
    font-size: 0.9rem;
    line-height: 1.45;
  }
  .check input {
    margin-top: 3px;
  }
  .cancel {
    margin-top: 8px;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    display: grid;
    place-items: center;
    padding: 16px;
    background: rgb(0 0 0 / 0.5);
  }
  .panel {
    width: min(640px, 100%);
    max-height: calc(100vh - 32px);
    overflow-y: auto;
    box-sizing: border-box;
    padding: 8px 24px 24px;
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 12px 40px rgb(0 0 0 / 0.3);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h2 {
    font-size: 1.3rem;
    font-weight: 500;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 1rem;
    font-weight: 500;
  }
  section {
    padding: 16px 0;
    border-top: 1px solid var(--border);
  }
  p {
    margin: 0 0 12px;
    line-height: 1.5;
    color: var(--text-secondary);
  }
  .path {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    margin-bottom: 14px;
  }
  code {
    font-size: 0.85rem;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--chip);
    overflow-wrap: anywhere;
  }
  .progress .bar {
    height: 8px;
    border-radius: 4px;
    background: var(--chip);
    overflow: hidden;
  }
  .progress .bar div {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
  .line {
    display: flex;
    justify-content: space-between;
    margin-top: 8px;
    font-variant-numeric: tabular-nums;
  }
  .current {
    margin-top: 4px;
    font-size: 0.85rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .counts {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0;
  }
  .count {
    padding: 4px 12px;
    border-radius: 14px;
    background: var(--chip);
    font-size: 0.9rem;
  }
  .count.ok {
    color: var(--success);
  }
  .count.warn {
    color: var(--warning);
  }
  .count.bad {
    color: var(--danger);
  }
  .missing {
    margin: 12px 0;
    padding: 12px;
    border-radius: 8px;
    background: var(--danger-bg);
  }
  .missing p {
    margin-bottom: 10px;
    color: var(--text);
  }
  details {
    margin-top: 10px;
  }
  summary {
    cursor: pointer;
    font-weight: 500;
  }
  ul {
    margin: 8px 0 0;
    padding-left: 18px;
    font-size: 0.875rem;
    line-height: 1.6;
    max-height: 220px;
    overflow-y: auto;
    overflow-wrap: anywhere;
  }
  .muted {
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
</style>
