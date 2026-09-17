<script>
  import { api } from '../lib/api.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // Rahmen über dem angezeigten Bild. frame: { left, top, width, height } der Bildfläche in der Bühne
  let { assetId, revision, frame, persons, editable = true, onchanged } = $props();

  const listId = `face-names-${Math.random().toString(36).slice(2)}`;

  let faces = $state([]);
  let editing = $state(null); // Gesicht, dessen Namen gerade eingegeben wird
  let name = $state('');
  let busy = $state(false);

  async function load(id) {
    try {
      faces = await api.assetFaces(id);
    } catch (e) {
      notifyError(e);
    }
  }

  $effect(() => {
    revision;
    editing = null;
    load(assetId);
  });

  function edit(face) {
    editing = face;
    name = face.name ?? '';
  }

  async function run(action) {
    busy = true;
    try {
      await action();
      editing = null;
      await load(assetId);
      onchanged();
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }

  const save = (e) => {
    e.preventDefault();
    if (name.trim()) run(() => api.assignFace(editing.id, name.trim()));
  };
</script>

<div class="boxes" style:left="{frame.left}px" style:top="{frame.top}px" style:width="{frame.width}px" style:height="{frame.height}px">
  {#each faces as face (face.id)}
    <button
      class="box"
      class:named={face.name}
      class:active={editing?.id === face.id}
      style:left="{face.x * 100}%"
      style:top="{face.y * 100}%"
      style:width="{face.w * 100}%"
      style:height="{face.h * 100}%"
      onclick={(e) => (e.stopPropagation(), editable && edit(face))}
      onpointerdown={(e) => e.stopPropagation()}
      title={face.name ?? (editable ? 'Unbekannt – antippen zum Benennen' : 'Unbekannt')}
    >
      <span class="label">{face.name ?? '?'}{#if face.name && !face.confirmed}<small>&nbsp;auto</small>{/if}</span>
    </button>
  {/each}

  {#if editing}
    <form
      class="editor"
      style:left="{Math.min(Math.max(editing.x + editing.w / 2, 0.15), 0.85) * 100}%"
      style:top="{Math.min((editing.y + editing.h) * 100 + 4, 80)}%"
      onsubmit={save}
      onpointerdown={(e) => e.stopPropagation()}
    >
      <!-- svelte-ignore a11y_autofocus -->
      <input type="text" bind:value={name} list={listId} placeholder="Name" autofocus />
      <datalist id={listId}>{#each persons as person}<option value={person.name}></option>{/each}</datalist>
      <div class="actions">
        <button type="submit" class="primary" disabled={busy || !name.trim()}>Speichern</button>
        {#if editing.group_id}
          <button type="button" disabled={busy} onclick={() => run(() => api.removeFace(editing.id))}
            title={editing.name ? `Nicht ${editing.name}` : 'Aus der Gruppe ähnlicher Gesichter lösen'}>
            {editing.name ? `Nicht ${editing.name}` : 'Nicht zuordnen'}
          </button>
        {/if}
        <button type="button" class="icon small" onclick={() => (editing = null)} title="Abbrechen"><Icon name="close" size={18} /></button>
      </div>
    </form>
  {/if}
</div>

<style>
  .boxes {
    position: absolute;
    z-index: 1;
    pointer-events: none;
  }
  .box {
    position: absolute;
    min-height: 0;
    padding: 0;
    border: 2px solid rgb(255 255 255 / 0.9);
    border-radius: 6px;
    background: transparent;
    box-shadow: 0 0 0 1px rgb(0 0 0 / 0.5);
    pointer-events: auto;
    cursor: pointer;
  }
  .box:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.1);
  }
  .box.named {
    border-color: #81d4fa;
  }
  .box.active {
    border-color: var(--accent);
    border-width: 3px;
  }
  .label {
    position: absolute;
    left: 50%;
    top: calc(100% + 4px);
    transform: translateX(-50%);
    padding: 1px 8px;
    border-radius: 10px;
    background: rgb(0 0 0 / 0.65);
    color: #fff;
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .label small {
    opacity: 0.7;
  }
  .editor {
    position: absolute;
    transform: translateX(-50%);
    display: grid;
    gap: 8px;
    width: 240px;
    padding: 10px;
    border-radius: 10px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 6px 24px rgb(0 0 0 / 0.4);
    pointer-events: auto;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .actions .icon {
    margin-left: auto;
  }
</style>
