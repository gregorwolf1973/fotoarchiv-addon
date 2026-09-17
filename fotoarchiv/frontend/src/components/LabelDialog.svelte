<script>
  import ChipInput from './ChipInput.svelte';
  import Icon from './Icon.svelte';

  let { kind, count, suggestions, onsave, oncancel } = $props();

  const title = $derived(kind === 'tags' ? 'Schlagworte ändern' : 'Personen ändern');
  const icon = $derived(kind === 'tags' ? 'tag' : 'person');
  let add = $state([]);
  let remove = $state([]);
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="label-title">
    <header>
      <h2 id="label-title">{title}</h2>
      <button class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
    </header>
    <p>Gilt für <strong>{count}</strong> ausgewählte Dateien. Andere vorhandene Einträge bleiben erhalten.</p>
    <div class="field">
      <span>Hinzufügen</span>
      <ChipInput values={add} {suggestions} {icon} placeholder="Name eingeben, Enter" onchange={(v) => (add = v)} />
    </div>
    <div class="field">
      <span>Entfernen</span>
      <ChipInput values={remove} {suggestions} {icon} placeholder="Name eingeben, Enter" onchange={(v) => (remove = v)} />
    </div>
    <footer>
      <button onclick={oncancel}>Abbrechen</button>
      <button class="primary" disabled={!add.length && !remove.length} onclick={() => onsave(add, remove)}>
        Übernehmen
      </button>
    </footer>
  </div>
</div>

<style>
  .field {
    display: grid;
    gap: 8px;
    margin-top: 16px;
  }
  .field > span {
    font-size: 0.85rem;
    color: var(--muted);
  }
</style>
