<script>
  import Icon from './Icon.svelte';

  // values: Liste von Namen; Enter fügt hinzu (Komma nicht, Namen wie "Müller, Hans" sind erlaubt)
  let { values = [], suggestions = [], placeholder = '', icon = 'tag', disabled = false, onchange } = $props();

  const listId = `chips-${Math.random().toString(36).slice(2)}`;
  let text = $state('');

  const available = $derived(
    suggestions.filter((name) => !values.some((v) => v.toLocaleLowerCase() === name.toLocaleLowerCase())),
  );

  function add() {
    const name = text.replace(/\s+/g, ' ').trim();
    text = '';
    if (!name || values.some((v) => v.toLocaleLowerCase() === name.toLocaleLowerCase())) return;
    // Schreibweise eines vorhandenen Labels übernehmen
    const known = suggestions.find((s) => s.toLocaleLowerCase() === name.toLocaleLowerCase());
    onchange([...values, known ?? name]);
  }

  function keydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      add();
    } else if (e.key === 'Backspace' && !text && values.length) {
      onchange(values.slice(0, -1));
    }
  }
</script>

<div class="chips" class:disabled>
  {#each values as value (value)}
    <span class="chip">
      <Icon name={icon} size={14} />
      {value}
      {#if !disabled}
        <button type="button" onclick={() => onchange(values.filter((v) => v !== value))} title="Entfernen">
          <Icon name="close" size={14} />
        </button>
      {/if}
    </span>
  {/each}
  {#if !disabled}
    <input
      type="text"
      list={listId}
      bind:value={text}
      {placeholder}
      onkeydown={keydown}
      onchange={() => available.includes(text) && add()}
      enterkeyhint="done"
    />
    <datalist id={listId}>
      {#each available as name}<option value={name}></option>{/each}
    </datalist>
  {/if}
</div>

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 4px 2px 8px;
    border-radius: 14px;
    background: var(--chip);
    font-size: 0.875rem;
    line-height: 24px;
  }
  .disabled .chip {
    padding-right: 10px;
  }
  .chip button {
    min-height: 0;
    width: 22px;
    height: 22px;
    padding: 0;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: var(--muted);
  }
  .chip button:hover {
    color: var(--text);
  }
  input {
    flex: 1;
    min-width: 120px;
  }
</style>
