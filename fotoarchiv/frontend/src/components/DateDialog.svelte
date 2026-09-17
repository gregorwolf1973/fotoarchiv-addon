<script>
  import Icon from './Icon.svelte';

  // value: "YYYY-MM-DDTHH:MM:SS" (Ortszeit ohne Zone)
  let { value, count = 1, onsave, oncancel } = $props();

  // Startwert bewusst nur einmal übernehmen
  // svelte-ignore state_referenced_locally
  let input = $state(value?.slice(0, 19) ?? '');
  const valid = $derived(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(input));

  function save() {
    if (valid) onsave(input.length === 16 ? `${input}:00` : input);
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="date-title">
    <form onsubmit={(e) => (e.preventDefault(), save())}>
      <header>
        <h2 id="date-title">Aufnahmedatum</h2>
        <button type="button" class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
      </header>
      {#if count > 1}
        <p>Alle <strong>{count}</strong> ausgewählten Dateien bekommen genau dieses Datum und diese Uhrzeit.</p>
      {:else}
        <p>Das Datum wird in die Datei geschrieben. Die Datei wird danach in den passenden Monatsordner verschoben.</p>
      {/if}
      <label class="field">
        Datum und Uhrzeit
        <!-- svelte-ignore a11y_autofocus -->
        <input type="datetime-local" step="1" bind:value={input} required autofocus />
      </label>
      <footer>
        <button type="button" onclick={oncancel}>Abbrechen</button>
        <button type="submit" class="primary" disabled={!valid}>Speichern</button>
      </footer>
    </form>
  </div>
</div>
