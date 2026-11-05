<script>
  // „So kommen Fotos ins Archiv“: im Fenster Importieren und hinter dem ⓘ neben „Hochladen“.
  // admin: Abgleich der Bibliothek nur für Administratoren erklären. importDir: Import-Ordner (über die Internetadresse
  // nicht bekannt, dann die Vorgabe). onclose gesetzt: als eigenes Fenster zeigen.
  import { t } from '../lib/i18n.js';
  import Icon from './Icon.svelte';
  let { admin = false, importDir = null, onclose = null } = $props();
  const ordner = $derived(/^\/(share|media)\/(.*)$/.exec(importDir || '/share/fotoarchiv-import'));
  const windowsPfad = $derived(ordner ? `\\\\homeassistant\\${ordner[1]}\\${ordner[2].replaceAll('/', '\\')}` : null);
  const smbPfad = $derived(ordner ? `smb://homeassistant/${ordner[1]}/${ordner[2]}` : null);
</script>

{#snippet liste()}
  <ol>
    <li>
      <strong>{t('Hochladen')}</strong> {t('(Knopf oben rechts): Fotos und Videos am Rechner auswählen oder ins Fenster ziehen. Das geht auch am Handy:')}
      <code>{location.host}</code>
      {t('im Browser des Handys öffnen, „Hochladen“ tippen und die Fotos aus der Galerie wählen. Was schon im Archiv ist, wird gar nicht erst gesendet.')}
    </li>
    <li>
      <strong>{t('Handy per USB:')}</strong>
      {t('Das Handy an den Rechner stecken, nicht an Home Assistant. Bei Android in der USB-Meldung des Handys „Dateiübertragung“ wählen, beim iPhone „Vertrauen“ tippen; ein reines Ladekabel reicht nicht. Das Handy erscheint dann in der Dateiverwaltung als Gerät. Mit dem Knopf')}
      <em>{t('Ordner hochladen')}</em>
      {t('(neben „Hochladen“) den Ordner')} <code>DCIM/Camera</code>
      {t('des Handys wählen oder ihn in den Import-Ordner kopieren (siehe unten). Handys sind keine Laufwerke, darum bindet Home Assistant sie nicht ein – einen USB-Stick oder eine Speicherkarte dagegen schon.')}
    </li>
    <li>
      <strong>{t('Import-Ordner')}</strong>
      {t('– für viele Dateien auf einmal, im Heimnetz: Fotos und Videos über das Netzwerk in den Import-Ordner kopieren')}{#if windowsPfad}, {t('unter Windows')} <code>{windowsPfad}</code>, {t('unter Linux und am Mac')}
      <code>{smbPfad}</code>{/if}. {t('Anmelden mit dem Samba-Konto von Home Assistant. Danach im Fenster')} <em>{t('Importieren')}</em>
      {t('„Import starten“ drücken – das Fenster gibt es in Home Assistant unter')} <em>Fotoarchiv</em> {t('im Seitenmenü. Das Archiv sortiert die Dateien nach Aufnahmedatum ein und nimmt sie aus dem Import-Ordner; Fotos, die es schon gibt, legt es dort in den Unterordner')} <code>_duplikate</code>.
    </li>
    {#if admin}
      <li>
        <strong>{t('Direkt in die Bibliothek:')}</strong>
        {t('Wer Dateien selbst in die Jahres- und Monatsordner der Bibliothek kopiert, nimmt sie mit „Bibliothek abgleichen“ auf, ohne dass etwas verschoben wird.')}
      </li>
    {/if}
  </ol>
{/snippet}

<svelte:window onkeydown={(e) => onclose && e.key === 'Escape' && onclose()} />

{#if onclose}
  <div class="backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
    <div class="panel" role="dialog" aria-modal="true" aria-labelledby="hilfe-titel">
      <header>
        <h2 id="hilfe-titel">{t('So kommen Fotos ins Archiv')}</h2>
        <button class="icon" onclick={onclose} title={t('Schließen')}><Icon name="close" /></button>
      </header>
      {@render liste()}
    </div>
  </div>
{:else}
  <details class="hilfe">
    <summary><Icon name="info" size={18} /> {t('So kommen Fotos ins Archiv')}</summary>
    {@render liste()}
  </details>
{/if}

<style>
  .hilfe {
    margin: 0 0 4px;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .hilfe summary {
    cursor: pointer;
    font-weight: 600;
  }
  .hilfe summary :global(svg) {
    vertical-align: -3px;
    margin-right: 4px;
  }
  ol {
    margin: 10px 0 2px;
    padding-left: 20px;
    line-height: 1.45;
  }
  li + li {
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
</style>
