<script>
  import { SvelteSet } from 'svelte/reactivity';
  import { api, cropUrl } from '../lib/api.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // group: { id, count } aus /api/people; persons: bekannte Personen für die Namensvorschläge
  let { group, persons, onclose, onchanged } = $props();

  const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeZone: 'UTC' });
  const listId = `persons-${Math.random().toString(36).slice(2)}`;

  let faces = $state([]);
  let name = $state('');
  let busy = $state(false);
  const excluded = new SvelteSet();

  $effect(() => {
    api.groupFaces(group.id).then((list) => (faces = list), notifyError);
  });

  async function save(e) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    busy = true;
    try {
      // Erst die abgewählten Gesichter herauslösen, dann den Rest benennen
      for (const id of excluded) await api.removeFace(id);
      await api.nameGroup(group.id, name.trim());
      onchanged();
      onclose();
    } catch (err) {
      notifyError(err);
    } finally {
      busy = false;
    }
  }

  async function hide() {
    busy = true;
    try {
      await api.hideGroup(group.id);
      onchanged();
      onclose();
    } catch (err) {
      notifyError(err);
    } finally {
      busy = false;
    }
  }

  const toggle = (id) => (excluded.has(id) ? excluded.delete(id) : excluded.add(id));
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="group-title">
    <form onsubmit={save}>
      <header>
        <h2 id="group-title">Wer ist das?</h2>
        <button type="button" class="icon" onclick={onclose} title="Schließen"><Icon name="close" /></button>
      </header>
      <p>
        {faces.length} ähnliche Gesichter. Tippe Gesichter an, die <strong>nicht</strong> zu dieser Person gehören.
        Der Name wird in alle übrigen Fotos geschrieben.
      </p>
      <div class="faces">
        {#each faces as face (face.id)}
          <button type="button" class="face" class:excluded={excluded.has(face.id)} onclick={() => toggle(face.id)}
            title={dateFormat.format(face.taken_ts * 1000)}>
            <img src={cropUrl(face.id)} alt="" loading="lazy" />
            {#if excluded.has(face.id)}<span class="mark"><Icon name="close" size={28} /></span>{/if}
          </button>
        {/each}
      </div>
      <label class="field">
        Name
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" bind:value={name} list={listId} placeholder="z. B. Anna Müller" autofocus required />
        <datalist id={listId}>{#each persons as person}<option value={person.name}></option>{/each}</datalist>
        <small>Gibt es die Person schon, werden die Gesichter ihr hinzugefügt.</small>
      </label>
      <footer>
        <button type="button" onclick={hide} disabled={busy} title="Unbekannte Person nicht mehr vorschlagen">
          <Icon name="hide" size={18} /> Ausblenden
        </button>
        <span class="grow"></span>
        <button type="button" onclick={onclose}>Abbrechen</button>
        <button type="submit" class="primary" disabled={busy || !name.trim() || excluded.size === faces.length}>
          {busy ? 'Wird gespeichert …' : 'Speichern'}
        </button>
      </footer>
    </form>
  </div>
</div>

<style>
  .wide {
    width: min(760px, 100%);
  }
  .faces {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
    gap: 6px;
    max-height: 45vh;
    overflow-y: auto;
  }
  .face {
    position: relative;
    aspect-ratio: 1;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 50%;
    overflow: hidden;
    background: var(--placeholder);
  }
  .face img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .face.excluded img {
    opacity: 0.35;
    filter: grayscale(1);
  }
  .mark {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--danger);
  }
  small {
    color: var(--muted);
  }
  .grow {
    flex: 1;
  }
</style>
