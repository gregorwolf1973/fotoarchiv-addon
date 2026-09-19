<script>
  import Icon from './Icon.svelte';

  // Für Konten, die selbst nicht löschen dürfen: der Vorschlag geht an den Admin in Home Assistant
  let { count = 1, onsave, oncancel } = $props();

  let reason = $state('');
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="propose-title">
    <form onsubmit={(e) => (e.preventDefault(), onsave(reason.trim()))}>
      <header>
        <h2 id="propose-title">Löschen vorschlagen</h2>
        <button type="button" class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
      </header>
      <p>
        {count === 1 ? 'Dieses Foto' : `Diese ${count} Fotos`} wird dem Admin zum Löschen vorgeschlagen.
        Er entscheidet, ob {count === 1 ? 'es' : 'sie'} in den Papierkorb {count === 1 ? 'kommt' : 'kommen'}.
      </p>
      <label class="field">
        Grund (freiwillig)
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" bind:value={reason} maxlength="300" placeholder="z. B. unscharf, doppelt, falsches Foto" autofocus />
      </label>
      <footer>
        <button type="button" onclick={oncancel}>Abbrechen</button>
        <button type="submit" class="primary">Vorschlagen</button>
      </footer>
    </form>
  </div>
</div>
