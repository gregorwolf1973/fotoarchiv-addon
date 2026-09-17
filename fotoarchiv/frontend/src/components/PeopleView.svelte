<script>
  import { api, cropUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import FaceStatus from './FaceStatus.svelte';
  import GroupDialog from './GroupDialog.svelte';
  import Icon from './Icon.svelte';
  import PersonDialog from './PersonDialog.svelte';

  let { revision, canEdit = true, onshowphotos, ontask, onchanged } = $props();

  let people = $state({ persons: [], groups: [] });
  let loaded = $state(false);
  let group = $state(null);
  let person = $state(null);

  async function load() {
    try {
      people = await api.people();
    } catch (e) {
      notifyError(e);
    } finally {
      loaded = true;
    }
  }

  $effect(() => {
    revision;
    load();
  });

  const initials = (name) =>
    name
      .split(/\s+/)
      .map((part) => part[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();

  function changed() {
    load();
    onchanged();
  }
</script>

<div class="people">
  {#if canEdit}<FaceStatus {revision} />{/if}

  <section>
    <h2>Personen <span class="count">{formatNumber(people.persons.length)}</span></h2>
    {#if people.persons.length}
      <div class="grid">
        {#each people.persons as entry (entry.id)}
          <button class="card" onclick={() => (person = entry)}>
            {#if entry.face_id}
              <img class="avatar" src={cropUrl(entry.face_id)} alt="" loading="lazy" />
            {:else}
              <span class="avatar initials">{initials(entry.name)}</span>
            {/if}
            <span class="name">{entry.name}</span>
            <span class="meta">{formatNumber(entry.count)} {entry.count === 1 ? 'Foto' : 'Fotos'}</span>
          </button>
        {/each}
      </div>
    {:else if loaded}
      <p class="empty">Noch keine Personen. Benenne unten eine Gruppe unbekannter Gesichter.</p>
    {/if}
  </section>

  {#if canEdit}
  <section>
    <h2>Unbekannte Gesichter <span class="count">{formatNumber(people.groups.length)}</span></h2>
    {#if people.groups.length}
      <p class="hint">Ähnliche Gesichter sind zu Gruppen zusammengefasst. Antippen, um der Gruppe einen Namen zu geben.</p>
      <div class="grid">
        {#each people.groups as entry (entry.id)}
          <button class="card" onclick={() => (group = entry)}>
            <img class="avatar" src={cropUrl(entry.face_id)} alt="" loading="lazy" />
            <span class="name unknown"><Icon name="plus" size={16} /> Namen geben</span>
            <span class="meta">{formatNumber(entry.count)} Gesichter</span>
          </button>
        {/each}
      </div>
    {:else if loaded}
      <p class="empty">Keine unbekannten Gesichtergruppen.</p>
    {/if}
  </section>
  {/if}
</div>

{#if group}
  <GroupDialog {group} persons={people.persons} onclose={() => (group = null)} onchanged={changed} />
{/if}
{#if person}
  <PersonDialog
    {person}
    persons={people.persons}
    {canEdit}
    onclose={() => (person = null)}
    onchanged={changed}
    {ontask}
    onshowphotos={(p) => {
      person = null;
      onshowphotos(p);
    }}
  />
{/if}

<style>
  .people {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px;
    box-sizing: border-box;
  }
  section {
    margin-top: 24px;
  }
  h2 {
    margin: 0 0 12px;
    font-size: 1.1rem;
    font-weight: 500;
  }
  .count {
    margin-left: 6px;
    padding: 0 8px;
    border-radius: 10px;
    background: var(--chip);
    color: var(--muted);
    font-size: 0.8rem;
    vertical-align: middle;
  }
  .hint,
  .empty {
    margin: -4px 0 12px;
    color: var(--muted);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
    gap: 12px;
  }
  .card {
    display: grid;
    justify-items: center;
    gap: 4px;
    min-height: 0;
    padding: 12px 8px;
    border: 0;
    border-radius: 12px;
    background: transparent;
    font-weight: 400;
  }
  .card:hover:not(:disabled) {
    background: var(--chip);
  }
  .avatar {
    width: 100px;
    height: 100px;
    margin-bottom: 4px;
    border-radius: 50%;
    object-fit: cover;
    background: var(--placeholder);
  }
  .initials {
    display: grid;
    place-items: center;
    color: var(--muted);
    font-size: 2rem;
    font-weight: 500;
  }
  .name {
    display: flex;
    align-items: center;
    gap: 4px;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }
  .name.unknown {
    color: var(--accent);
  }
  .meta {
    color: var(--muted);
    font-size: 0.8rem;
  }
  @media (max-width: 479px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
      gap: 4px;
    }
    .avatar {
      width: 76px;
      height: 76px;
    }
  }
</style>
