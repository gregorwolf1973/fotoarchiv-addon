<script>
  import Icon from './Icon.svelte';

  // Einen Namen eingeben oder ändern; onsave liefert ein Promise, bei Fehlern bleibt der Dialog offen
  let { title, value = '', label = 'Name', saveLabel = 'Speichern', onsave, oncancel } = $props();

  // svelte-ignore state_referenced_locally
  let name = $state(value);
  let saving = $state(false);

  async function submit(e) {
    e.preventDefault();
    if (!name.trim() || saving) return;
    saving = true;
    try {
      await onsave(name.trim());
    } catch {
      /* Meldung kommt von der App */
    } finally {
      saving = false;
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="name-title">
  <form onsubmit={submit}>
    <header>
      <h2 id="name-title">{title}</h2>
      <button type="button" class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
    </header>
    <!-- svelte-ignore a11y_autofocus -->
    <input type="text" bind:value={name} maxlength="100" aria-label={label} autofocus />
    <footer>
      <button type="button" onclick={oncancel}>Abbrechen</button>
      <button class="primary" type="submit" disabled={!name.trim() || saving}>{saveLabel}</button>
    </footer>
  </form>
  </div>
</div>

<style>
  input {
    width: 100%;
    box-sizing: border-box;
    margin-top: 8px;
  }
</style>
