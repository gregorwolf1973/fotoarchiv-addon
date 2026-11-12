<script>
  import { api } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { LANGUAGES, language, setLanguage, t, tServer } from '../lib/i18n.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import Confirm from './Confirm.svelte';
  import Icon from './Icon.svelte';

  // vision: Stand aus api/state (wird laufend aktualisiert); ontask(task): Aufgabe an die App übergeben
  // revision: Änderungszähler – die Zahlen laufen mit, während eine Aufgabe schreibt
  let { vision, revision, onclose, ontask, onchanged } = $props();

  let overview = $state(null);
  let error = $state('');
  let confirm = $state(null); // 'recheck' | 'writeback'
  let busy = $state(false);

  let lastLoad = 0;
  async function load() {
    lastLoad = Date.now();
    try {
      overview = await api.settingsOverview();
      error = '';
    } catch (e) {
      error = e.message;
    }
  }
  // Zählen geht auf dem Pi alle Ordner durch: höchstens alle 5 Sekunden
  $effect(() => {
    revision;
    const timer = setTimeout(load, Math.max(0, 5000 - (Date.now() - lastLoad)));
    return () => clearTimeout(timer);
  });

  const v = $derived(vision ?? overview?.vision);
  const details = $derived(overview?.vision);
  const write = $derived(overview?.writeback);
  const pending = $derived(write?.files ?? 0);
  const n = (value) => formatNumber(value ?? 0);
  const photos = (value) => (value === 1 ? t('1 Foto') : t('{n} Fotos', { n: n(value) }));

  const statusText = $derived.by(() => {
    if (!v) return '';
    if (!v.enabled) return t('Ausgeschaltet (Add-on-Option image_recognition).');
    if (v.status === 'downloading')
      return t('Modelle werden heruntergeladen: {percent} %', {
        percent: v.download_total ? Math.round((v.download_done / v.download_total) * 100) : 0,
      });
    if (v.status === 'loading' || v.status === 'starting') return t('Wird vorbereitet …');
    if (v.status === 'error') return t('Gestört: {message}', { message: tServer(v.message) });
    if (v.done < v.total)
      return t('Läuft: {done} von {total} Dateien analysiert ({percent} %).', {
        done: n(v.done),
        total: n(v.total),
        percent: Math.floor((v.done / v.total) * 100),
      });
    return t('Alle {total} Dateien analysiert.', { total: n(v.total) });
  });

  async function recheck() {
    confirm = null;
    busy = true;
    try {
      const { count } = await api.recheckOrientation();
      notify(t('{photos} werden noch einmal auf die Ausrichtung geprüft', { photos: photos(count) }));
      onchanged();
      await load();
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }

  async function writeBack() {
    confirm = null;
    busy = true;
    try {
      ontask(await api.writeBack(language));
      await load();
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && !confirm && onclose()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal panel" role="dialog" aria-modal="true" aria-labelledby="settings-title">
    <header>
      <h2 id="settings-title"><Icon name="cog" size={22} /> {t('Einstellungen')}</h2>
      <button class="icon" onclick={onclose} title={t('Schließen')}><Icon name="close" /></button>
    </header>

    {#if error}<p class="error">{error}</p>{/if}

    <section>
      <h3>{t('Sprache')}</h3>
      <select value={language} onchange={(e) => setLanguage(e.currentTarget.value)} aria-label={t('Sprache')}>
        {#each LANGUAGES as l}<option value={l.code}>{l.label}</option>{/each}
      </select>
    </section>

    <section>
      <h3><Icon name="sparkle" size={18} /> {t('Bilderkennung')}</h3>
      <p class="status" class:running={v?.done < v?.total}>{statusText}</p>
      <p class="hint">
        {t('Sie läuft von selbst im Hintergrund: einmal über alle Fotos und Videos, die neuesten zuerst, danach jedes neue Foto kurz nach dem Import oder Hochladen. Solange die Gesichtserkennung arbeitet, wartet sie. Die Ausrichtung prüft sie je Foto nur einmal, beim ersten Durchgang. Bestätigt ein Gesicht die neue Lage, dreht sie das Foto dabei sofort, sonst kommt es nach „Drehen prüfen“.')}
      </p>
      {#if details}
        <ul class="facts">
          <li>{t('Automatisch gedreht:')} <strong>{n((details.rotations.auto ?? 0) + (details.rotations.accepted ?? 0) + (details.rotations.undone ?? 0))}</strong>
            {#if details.rotations.undone}<span class="muted">{t('(davon {n} zurückgedreht)', { n: n(details.rotations.undone) })}</span>{/if}</li>
          <li>{t('Noch zu prüfen:')} <strong>{n(details.review)}</strong></li>
          <li>{t('Offene Schlagwort-Vorschläge:')} <strong>{n(details.suggestions.tags)}</strong> {t('bei {photos}', { photos: photos(details.suggestions.photos) })}</li>
        </ul>
      {/if}
    </section>

    <section>
      <h3><Icon name="rotate" size={18} /> {t('Manuell gedrehte Fotos')}</h3>
      <p class="hint">
        {t('Was du von Hand drehst, bleibt so – die Bilderkennung prüft es nicht mehr.')}
        {#if details}{t('Das betrifft zurzeit')} <strong>{photos(details.manual)}</strong>.{/if}
        {t('Bekannt sind alle Drehungen ab jetzt; von früher nur die Mehrfach-Drehungen der letzten Tage.')}
      </p>
      <button disabled={busy || !details?.manual || !v?.enabled} onclick={() => (confirm = 'recheck')}>
        <Icon name="rotate" size={18} /> {t('Alle prüfen, auch die manuell gedrehten')}
      </button>
    </section>

    <section>
      <h3><Icon name="download" size={18} /> {t('Alle Informationen in die Bilder schreiben')}</h3>
      <p class="hint">{t('Schreibt in die Dateien, was bisher nur in der Datenbank steht:')}</p>
      {#if write}
        <ul class="facts">
          <li><strong>{n(write.suggestion_tags)}</strong> {t('erkannte Schlagworte bei {photos} – abgelehnte nicht', { photos: photos(write.suggestion_photos) })}</li>
          <li><strong>{photos(write.persons)}</strong> {t('mit Personennamen, die noch nicht geschrieben sind')}</li>
          <li><strong>{photos(write.sidecars)}</strong> {t('mit Angaben aus Begleitdateien (Google-JSON, XMP)')}</li>
        </ul>
        {#if write.unwritable}
          <p class="hint">{t('{n} Dateien können keine Metadaten speichern (z. B. AVI, GIF). Ihre Vorschläge bleiben in der Datenbank.', { n: n(write.unwritable) })}</p>
        {/if}
        <p class="hint">
          {t('Drehvorschläge und Favoritenordner gehören nicht dazu. Etwa jedes zehnte erkannte Schlagwort liegt daneben – wer mag, prüft vorher über das Suchfeld unter')} <em>{t('Erkannt')}</em>.
          {#if v?.done < v?.total}{t('Die Bilderkennung ist noch nicht durch; später einfach noch einmal drücken, es wird nur geschrieben, was fehlt.')}{/if}
        </p>
      {:else}
        <p class="muted">{t('Wird gezählt …')}</p>
      {/if}
      <button class="primary" disabled={busy || !pending} onclick={() => (confirm = 'writeback')}>
        <Icon name="download" size={18} /> {t('Alle Informationen in die Bilder schreiben')}
      </button>
    </section>
  </div>
</div>

{#if confirm === 'recheck'}
  <Confirm
    title={t('Auch manuell gedrehte Fotos prüfen?')}
    text={t('Die {photos}, die von Hand gedreht wurden, werden noch einmal auf die Ausrichtung geprüft. Eindeutige Fälle (mit Gesicht) dreht das Add-on dabei selbst, die übrigen kommen nach „Drehen prüfen“. Beides lässt sich dort rückgängig machen.', { photos: photos(details.manual) })}
    confirmLabel={t('Prüfen')}
    oncancel={() => (confirm = null)}
    onconfirm={recheck}
  />
{:else if confirm === 'writeback'}
  <Confirm
    title={t('Alle Informationen in die Bilder schreiben?')}
    text={write.files === 1
      ? t('1 Datei wird geändert. Die Angaben stehen danach in den Dateien selbst und bleiben auch ohne das Fotoarchiv erhalten. Das läuft als Hintergrundaufgabe.')
      : t('{n} Dateien werden geändert. Die Angaben stehen danach in den Dateien selbst und bleiben auch ohne das Fotoarchiv erhalten. Das läuft als Hintergrundaufgabe.', { n: n(write.files) })}
    confirmLabel={t('Schreiben')}
    oncancel={() => (confirm = null)}
    onconfirm={writeBack}
  />
{/if}

<style>
  .panel {
    width: min(620px, 100%);
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  section {
    padding: 4px 0 16px;
    border-top: 1px solid var(--border);
  }
  h3 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 14px 0 4px;
    font-size: 1rem;
    font-weight: 500;
  }
  .status {
    margin: 4px 0;
    font-weight: 500;
    color: var(--text);
  }
  .status.running {
    color: var(--accent);
  }
  .hint {
    margin: 6px 0 10px;
    font-size: 0.9rem;
  }
  .facts {
    margin: 6px 0 12px;
    padding-left: 20px;
    font-size: 0.9rem;
    line-height: 1.6;
  }
  .muted {
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
</style>
