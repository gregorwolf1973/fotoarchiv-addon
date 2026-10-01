<script>
  import Icon from './Icon.svelte';

  // Ausgewählte Fotos in einen Favoritenordner legen – auch für Touchscreens, wo Ziehen nicht geht.
  // onsave(folder) mit einem vorhandenen Ordner oder onsave(null, name) für einen neuen.
  let { count, folders, onsave, oncancel } = $props();

  let name = $state('');
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="favorite-title">
    <header>
      <h2 id="favorite-title">Zu Favoriten hinzufügen</h2>
      <button class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
    </header>
    <p>{count === 1 ? 'Das Foto wird' : `${count} Fotos werden`} im Ordner verlinkt; die Dateien bleiben, wo sie sind.</p>
    {#if folders.length}
      <ul>
        {#each folders as folder (folder.id)}
          <li>
            <button onclick={() => onsave(folder)}>
              <Icon name="folderStar" size={20} />
              <span class="name">{folder.name}</span>
              <span class="count">{folder.count}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
    <form
      class="new"
      onsubmit={(e) => {
        e.preventDefault();
        if (name.trim()) onsave(null, name.trim());
      }}
    >
      <input type="text" bind:value={name} maxlength="100" placeholder="Neuer Ordner" aria-label="Name des neuen Ordners" />
      <button class="primary" type="submit" disabled={!name.trim()}><Icon name="folderPlus" size={20} /> Anlegen</button>
    </form>
  </div>
</div>

<style>
  ul {
    display: grid;
    gap: 2px;
    max-height: 50vh;
    margin: 12px 0 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }
  li button {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    border: 0;
    background: transparent;
    color: var(--text);
    text-align: left;
  }
  li button:hover:not(:disabled) {
    background: var(--chip);
  }
  li :global(svg) {
    color: var(--accent);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    font-size: 0.8rem;
    color: var(--muted);
  }
  .new {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }
  .new input {
    flex: 1;
    min-width: 0;
  }
</style>
