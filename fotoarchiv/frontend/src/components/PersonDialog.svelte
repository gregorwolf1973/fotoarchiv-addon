<script>
  import { api, cropUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // person: { id, name, count, face_id }; onshowphotos(person); ontask(task) verfolgt das Umbenennen
  let { person, canEdit = true, onclose, onchanged, onshowphotos, ontask } = $props();

  const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeZone: 'UTC' });

  let faces = $state([]);
  // svelte-ignore state_referenced_locally
  let name = $state(person.name);
  let busy = $state(false);

  function load() {
    api.personFaces(person.id).then((list) => (faces = list), notifyError);
  }
  $effect(load);

  async function rename(e) {
    e.preventDefault();
    const clean = name.trim();
    if (!clean || clean === person.name || busy) return;
    busy = true;
    try {
      const { task } = await api.renamePerson(person.id, clean);
      if (task) ontask(task);
      else notify('Umbenannt');
      onchanged();
      onclose();
    } catch (err) {
      notifyError(err);
    } finally {
      busy = false;
    }
  }

  async function remove(face) {
    try {
      await api.removeFace(face.id);
      faces = faces.filter((f) => f.id !== face.id);
      notify(`Gesicht von „${person.name}“ gelöst`);
      onchanged();
    } catch (err) {
      notifyError(err);
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="person-title">
    <header>
      <h2 id="person-title">{person.name}</h2>
      <button class="icon" onclick={onclose} title="Schließen"><Icon name="close" /></button>
    </header>

    {#if canEdit}
    <form class="rename" onsubmit={rename}>
      <label class="field">
        Name
        <input type="text" bind:value={name} required />
      </label>
      <button type="submit" disabled={busy || !name.trim() || name.trim() === person.name}>Umbenennen</button>
    </form>
    <p class="hint">
      Der neue Name wird in alle {formatNumber(person.count)} Fotos geschrieben. Heißt schon eine andere Person so, werden
      beide zusammengeführt.
    </p>
    {/if}

    <div class="section">
      <h3>Erkannte Gesichter <span class="muted">{formatNumber(faces.length)}</span></h3>
      {#if faces.length}
        {#if canEdit}<p class="hint">Falsch zugeordnet? Mit ✕ lösen – der Name wird aus dem Foto entfernt und dort nicht wieder vorgeschlagen.</p>{/if}
        <div class="faces">
          {#each faces as face (face.id)}
            <div class="face" title={dateFormat.format(face.taken_ts * 1000)}>
              <img src={cropUrl(face.id)} alt="" loading="lazy" />
              {#if !face.confirmed}<span class="auto" title="automatisch erkannt">auto</span>{/if}
              {#if canEdit}<button class="remove" onclick={() => remove(face)} title="Nicht {person.name}"><Icon name="close" size={16} /></button>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <p class="muted">Keine Gesichter zugeordnet – die Person stammt nur aus den Metadaten der Fotos.</p>
      {/if}
    </div>

    <footer>
      <button onclick={onclose}>Schließen</button>
      <button class="primary" onclick={() => onshowphotos(person)}><Icon name="images" size={18} /> Fotos anzeigen</button>
    </footer>
  </div>
</div>

<style>
  .wide {
    width: min(760px, 100%);
  }
  .rename {
    display: flex;
    align-items: flex-end;
    gap: 8px;
  }
  .rename .field {
    flex: 1;
    margin-top: 0;
  }
  .hint {
    font-size: 0.85rem;
    margin: 8px 0 0;
  }
  .section {
    margin-top: 20px;
  }
  h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 500;
  }
  .muted {
    color: var(--muted);
    font-weight: 400;
  }
  .faces {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
    gap: 8px;
    max-height: 42vh;
    margin-top: 12px;
    overflow-y: auto;
  }
  .face {
    position: relative;
    aspect-ratio: 1;
  }
  .face img {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    object-fit: cover;
    display: block;
    background: var(--placeholder);
  }
  .auto {
    position: absolute;
    left: 50%;
    bottom: -2px;
    transform: translateX(-50%);
    padding: 0 6px;
    border-radius: 8px;
    background: var(--chip);
    color: var(--muted);
    font-size: 0.7rem;
  }
  .remove {
    position: absolute;
    top: 0;
    right: 0;
    min-height: 0;
    width: 26px;
    height: 26px;
    padding: 0;
    justify-content: center;
    border-radius: 50%;
    background: var(--surface);
    color: var(--danger);
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.3);
  }
</style>
