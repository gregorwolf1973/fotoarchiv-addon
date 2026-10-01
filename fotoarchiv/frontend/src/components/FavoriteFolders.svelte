<script>
  import { thumbUrl } from '../lib/api.js';
  import { isPhotoDrag, readPhotoIds } from '../lib/dragphotos.js';
  import { formatNumber } from '../lib/format.js';
  import Icon from './Icon.svelte';

  // Favoritenordner als Seitenleiste neben der Galerie (side) oder als eigene Übersicht (page).
  // Jeder Ordner nimmt Fotos per Drag & Drop an; anlegen und umbenennen direkt in der Liste.
  // oncreate/onrename liefern ein Promise, das bei Fehlern ablehnt – das Eingabefeld bleibt dann offen.
  let { folders, active = null, canEdit, mode = 'side', onopen, ondropids, oncreate, onrename, onhide } = $props();

  let editing = $state(null); // Ordner-ID beim Umbenennen, 'new' beim Anlegen
  let draft = $state('');
  let saving = $state(false);
  let over = $state(null); // Ordner unter dem Mauszeiger beim Ziehen

  function startEdit(folder) {
    editing = folder ? folder.id : 'new';
    draft = folder ? folder.name : '';
  }

  async function save() {
    if (saving || editing === null) return;
    const name = draft.trim();
    const folder = folders.find((f) => f.id === editing);
    if (!name || name === folder?.name) {
      editing = null;
      return;
    }
    saving = true;
    try {
      await (editing === 'new' ? oncreate(name) : onrename(folder, name));
      editing = null;
    } catch {
      /* Fehlermeldung zeigt die App; Name zum Korrigieren stehen lassen */
    } finally {
      saving = false;
    }
  }

  function keydown(e) {
    if (e.key === 'Enter') save();
    else if (e.key === 'Escape') editing = null;
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  const focus = (node) => {
    node.focus();
    node.select();
  };

  function dragover(e, folder) {
    if (!canEdit || !isPhotoDrag(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'link';
    over = folder.id;
  }
  function drop(e, folder) {
    if (!canEdit || !isPhotoDrag(e)) return;
    e.preventDefault();
    over = null;
    const ids = readPhotoIds(e);
    if (ids.length) ondropids(folder, ids);
  }
  const cover = (folder) => thumbUrl([folder.cover[0], 0, 0, 0, 0, folder.cover[1]], true);
</script>

<aside class="folders {mode}">
  {#if mode === 'side'}
    <header>
      <Icon name="star" size={18} />
      <strong>Favoriten</strong>
      <span class="grow"></span>
      {#if canEdit}
        <button class="icon small" onclick={() => startEdit(null)} title="Neuer Ordner"><Icon name="folderPlus" size={20} /></button>
      {/if}
      <button class="icon small" onclick={onhide} title="Leiste ausblenden"><Icon name="left" size={20} /></button>
    </header>
  {/if}

  <ul>
    {#each folders as folder (folder.id)}
      <li
        class:active={folder.id === active}
        class:over={folder.id === over}
        ondragover={(e) => dragover(e, folder)}
        ondragenter={(e) => dragover(e, folder)}
        ondragleave={(e) => !e.currentTarget.contains(e.relatedTarget) && over === folder.id && (over = null)}
        ondrop={(e) => drop(e, folder)}
      >
        {#if editing === folder.id}
          <div class="row">
            <span class="cover"><Icon name="folderStar" size={mode === 'page' ? 40 : 22} /></span>
            <input type="text" bind:value={draft} maxlength="100" disabled={saving} onkeydown={keydown} onblur={save} use:focus aria-label="Ordnername" />
          </div>
        {:else}
          <button class="row" onclick={() => onopen(folder)} ondblclick={() => canEdit && startEdit(folder)} title={folder.name}>
            <span class="cover">
              {#if folder.cover}<img src={cover(folder)} alt="" loading="lazy" draggable="false" />{:else}<Icon name="folderStar" size={mode === 'page' ? 40 : 22} />{/if}
            </span>
            <span class="text">
              <span class="name">{folder.name}</span>
              <span class="count">{folder.count === 1 ? '1 Foto' : `${formatNumber(folder.count)} Fotos`}</span>
            </span>
          </button>
          {#if canEdit}
            <button class="icon small rename" onclick={() => startEdit(folder)} title="Umbenennen"><Icon name="pencil" size={16} /></button>
          {/if}
        {/if}
      </li>
    {/each}
    {#if editing === 'new'}
      <li>
        <div class="row">
          <span class="cover"><Icon name="folderStar" size={mode === 'page' ? 40 : 22} /></span>
          <input type="text" bind:value={draft} maxlength="100" disabled={saving} placeholder="Name des Ordners" onkeydown={keydown} onblur={save} use:focus aria-label="Name des neuen Ordners" />
        </div>
      </li>
    {:else if mode === 'page' && canEdit}
      <li class="add">
        <button class="row" onclick={() => startEdit(null)}>
          <span class="cover"><Icon name="folderPlus" size={40} /></span>
          <span class="text"><span class="name">Neuer Ordner</span></span>
        </button>
      </li>
    {/if}
  </ul>

  {#if !folders.length && editing !== 'new'}
    <p class="hint">
      {#if canEdit}
        Noch keine Ordner. {mode === 'side' ? 'Mit dem Ordner-Knopf oben einen anlegen,' : 'Einen anlegen,'} dann Fotos hineinziehen
        oder auswählen und auf <Icon name="star" size={14} /> tippen.
      {:else}
        Noch keine Favoritenordner.
      {/if}
    </p>
  {:else if mode === 'side' && canEdit}
    <p class="hint">Fotos aus der Galerie auf einen Ordner ziehen. Doppelklick benennt um.</p>
  {/if}
</aside>

<style>
  .folders {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .side {
    flex: none;
    width: 230px;
    border-right: 1px solid var(--border);
    background: var(--surface);
    overflow-y: auto;
  }
  .side header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 6px 6px 14px;
    color: var(--accent);
  }
  .side header strong {
    color: var(--text);
    font-weight: 500;
  }
  .grow {
    flex: 1;
  }
  ul {
    margin: 0;
    padding: 4px 6px;
    list-style: none;
  }
  li {
    position: relative;
    display: flex;
    align-items: center;
    border-radius: 8px;
    outline: 2px solid transparent;
    transition: background 0.1s;
  }
  li.active {
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }
  li.over {
    background: color-mix(in srgb, var(--accent) 25%, transparent);
    outline-color: var(--accent);
  }
  .row {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 44px;
    padding: 4px 8px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--text);
    text-align: left;
  }
  button.row:hover:not(:disabled) {
    background: var(--chip);
  }
  .cover {
    flex: none;
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    overflow: hidden;
    border-radius: 6px;
    background: var(--chip);
    color: var(--accent);
  }
  .cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .text {
    display: grid;
    min-width: 0;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    font-size: 0.75rem;
    color: var(--muted);
  }
  input {
    flex: 1;
    min-width: 0;
  }
  .rename {
    position: absolute;
    right: 4px;
    display: none;
  }
  li:hover .rename {
    display: inline-flex;
  }
  .hint {
    margin: 8px 16px;
    font-size: 0.8rem;
    line-height: 1.4;
    color: var(--muted);
  }

  /* Übersicht: Kacheln mit großem Titelbild */
  .page {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }
  .page ul {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: 12px;
    padding: 0;
  }
  .page li {
    flex-direction: column;
    align-items: stretch;
  }
  .page .row {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    padding: 8px;
  }
  .page .cover {
    width: 100%;
    height: auto;
    aspect-ratio: 1;
    border-radius: 10px;
  }
  .page .add .cover {
    color: var(--muted);
  }
  .page .rename {
    top: 14px;
    right: 14px;
    background: var(--surface);
  }
  .page .hint {
    margin: 16px 0;
    text-align: center;
  }
  @media (hover: none) {
    .rename {
      display: inline-flex;
    }
  }
  @media (max-width: 479px) {
    .page {
      padding: 8px;
    }
    .page ul {
      grid-template-columns: repeat(2, 1fr);
      gap: 6px;
    }
  }
</style>
