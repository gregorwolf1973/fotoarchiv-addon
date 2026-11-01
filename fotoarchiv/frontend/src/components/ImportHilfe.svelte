<script>
  // „So kommen Fotos ins Archiv“: im Fenster Importieren und hinter dem ⓘ neben „Hochladen“.
  // admin: Import-Ordner und Bibliotheksabgleich nur für Administratoren erklären.
  // onclose gesetzt: als eigenes Fenster zeigen.
  import Icon from './Icon.svelte';
  let { admin = false, onclose = null } = $props();
</script>

{#snippet liste()}
  <ol>
    <li>
      <strong>Hochladen</strong> (Knopf oben rechts): Fotos und Videos am Rechner auswählen oder ins Fenster ziehen. Das
      geht auch am Handy: <code>{location.host}</code> im Browser des Handys öffnen, „Hochladen“ tippen und die Fotos aus
      der Galerie wählen. Was schon im Archiv ist, wird gar nicht erst gesendet.
    </li>
    <li>
      <strong>Handy per USB:</strong> Das Handy an den Rechner stecken, nicht an Home Assistant. Bei Android in der
      USB-Meldung des Handys „Dateiübertragung“ wählen, beim iPhone „Vertrauen“ tippen; ein reines Ladekabel reicht nicht.
      Das Handy erscheint dann in der Dateiverwaltung als Gerät. Mit dem Knopf <em>Ordner hochladen</em> (neben
      „Hochladen“) den Ordner <code>DCIM/Camera</code> des Handys wählen{admin ? ' oder ihn in den Import-Ordner kopieren' : ''}.
      Handys sind keine Laufwerke, darum bindet Home Assistant sie nicht ein – einen USB-Stick oder eine Speicherkarte
      dagegen schon.
    </li>
    {#if admin}
      <li>
        <strong>Import-Ordner</strong> (im Fenster <em>Importieren</em>): für viele Dateien auf einmal. Die Dateien über
        das Netzwerk (Samba) in den Import-Ordner kopieren und „Import starten“ drücken. Das Archiv sortiert sie nach
        Aufnahmedatum ein und nimmt sie aus dem Import-Ordner; Fotos, die es schon gibt, legt es dort in den Unterordner
        <code>_duplikate</code>.
      </li>
      <li>
        <strong>Direkt in die Bibliothek:</strong> Wer Dateien selbst in die Jahres- und Monatsordner der Bibliothek
        kopiert, nimmt sie mit „Bibliothek abgleichen“ auf, ohne dass etwas verschoben wird.
      </li>
    {/if}
  </ol>
{/snippet}

<svelte:window onkeydown={(e) => onclose && e.key === 'Escape' && onclose()} />

{#if onclose}
  <div class="backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
    <div class="panel" role="dialog" aria-modal="true" aria-labelledby="hilfe-titel">
      <header>
        <h2 id="hilfe-titel">So kommen Fotos ins Archiv</h2>
        <button class="icon" onclick={onclose} title="Schließen"><Icon name="close" /></button>
      </header>
      {@render liste()}
    </div>
  </div>
{:else}
  <details class="hilfe">
    <summary><Icon name="info" size={18} /> So kommen Fotos ins Archiv</summary>
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
