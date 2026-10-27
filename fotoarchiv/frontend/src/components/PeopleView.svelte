<script>
  import { api, cropUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import FaceStatus from './FaceStatus.svelte';
  import FotoLupe from './FotoLupe.svelte';
  import GroupDialog from './GroupDialog.svelte';
  import Icon from './Icon.svelte';
  import PersonDialog from './PersonDialog.svelte';

  let { revision, canEdit = true, onshowphotos, ontask, onchanged } = $props();

  let people = $state({ persons: [], groups: [] });
  let suggestions = $state([]);
  let loaded = $state(false);
  let group = $state(null);
  let person = $state(null);
  let query = $state('');
  let comparing = $state(false);
  let answering = $state(new Set());
  let lupe = $state(null); // { entry, faces, index }: ganze Fotos eines Vorschlags, vergrößerbar

  const matches = (name) => !query.trim() || name.toLocaleLowerCase('de').includes(query.trim().toLocaleLowerCase('de'));
  let persons = $derived(people.persons.filter((p) => matches(p.name)));
  let shownSuggestions = $derived(suggestions.filter((s) => matches(s.name)));

  async function load() {
    try {
      [people, suggestions] = await Promise.all([api.people(), canEdit ? api.faceSuggestions() : Promise.resolve([])]);
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

  /** "Ist das X?" – Ja ordnet die ganze Gruppe der Person zu, Nein merkt sich die Ablehnung. */
  async function answer(entry, yes) {
    answering = new Set([...answering, entry.group_id]);
    try {
      if (yes) {
        await api.nameGroup(entry.group_id, entry.name);
      } else {
        await api.refuseGroup(entry.group_id, entry.person_id);
      }
      suggestions = suggestions.filter((s) => s.group_id !== entry.group_id);
      if (yes) changed();
    } catch (e) {
      notifyError(e);
    } finally {
      answering = new Set([...answering].filter((id) => id !== entry.group_id));
    }
  }

  /** Ganze Fotos der vorgeschlagenen Gruppe zeigen, beginnend mit dem Vorschaugesicht. */
  async function openLupe(entry) {
    try {
      const list = await api.groupFaces(entry.group_id);
      const faces = list.length ? list : [entry.face];
      lupe = { entry, faces, index: Math.max(0, faces.findIndex((f) => f.id === entry.face_id)) };
    } catch (e) {
      notifyError(e);
    }
  }

  async function answerInLupe(yes) {
    const { entry } = lupe;
    lupe = null;
    await answer(entry, yes);
  }

  const personFace = (personId) => people.persons.find((p) => p.id === personId)?.face_id;

  async function compare() {
    comparing = true;
    try {
      const result = await api.compareFaces();
      notify(
        result.merged || result.learned
          ? `${formatNumber(result.merged)} ähnliche Gruppen zusammengeführt${result.learned ? ', bekannte Personen zugeordnet' : ''}.`
          : 'Keine weiteren Übereinstimmungen gefunden.',
      );
      changed();
    } catch (e) {
      notifyError(e);
    } finally {
      comparing = false;
    }
  }
</script>

<div class="people">
  {#if canEdit}<FaceStatus {revision} />{/if}

  <div class="toolbar">
    <input type="search" class="find" placeholder="Name suchen …" aria-label="Personen nach Namen suchen" bind:value={query} />
    {#if canEdit}
      <button onclick={compare} disabled={comparing} title="Alle unbekannten Gesichter erneut miteinander und mit den benannten Personen vergleichen">
        <Icon name="face" size={18} /> {comparing ? 'Vergleiche …' : 'Gesichter vergleichen'}
      </button>
    {/if}
  </div>

  {#if canEdit && shownSuggestions.length}
  <section>
    <h2>Vorschläge <span class="count">{formatNumber(shownSuggestions.length)}</span></h2>
    <p class="hint">Diese Gesichter ähneln einer bekannten Person. Antippen zeigt alle Gesichter der Gruppe, die Lupe die ganzen Fotos zum Vergrößern.</p>
    <div class="grid">
      {#each shownSuggestions as entry (entry.group_id)}
        <div class="card suggestion">
          <span class="pic">
            <button class="face" onclick={() => (group = { id: entry.group_id, count: entry.count, face_id: entry.face_id })}>
              <img class="avatar" src={cropUrl(entry.face_id)} alt="" loading="lazy" />
            </button>
            <button class="icon zoom" onclick={() => openLupe(entry)} title="Ganze Fotos vergrößert ansehen"><Icon name="zoom" size={18} /></button>
          </span>
          <span class="name">Ist das {entry.name}?</span>
          <span class="meta">{Math.round(entry.similarity * 100)} % ähnlich · {formatNumber(entry.count)} {entry.count === 1 ? 'Gesicht' : 'Gesichter'}</span>
          <span class="answers">
            <button class="primary" disabled={answering.has(entry.group_id)} onclick={() => answer(entry, true)}>Ja</button>
            <button disabled={answering.has(entry.group_id)} onclick={() => answer(entry, false)}>Nein</button>
          </span>
        </div>
      {/each}
    </div>
  </section>
  {/if}

  <section>
    <h2>Personen <span class="count">{formatNumber(persons.length)}</span></h2>
    {#if persons.length}
      <div class="grid">
        {#each persons as entry (entry.id)}
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
    {:else if loaded && query.trim()}
      <p class="empty">Keine Person mit „{query.trim()}“.</p>
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

{#if lupe}
  <FotoLupe faces={lupe.faces} index={lupe.index} onclose={() => (lupe = null)}>
    {#snippet heading()}
      {#if personFace(lupe.entry.person_id)}
        <img class="ref" src={cropUrl(personFace(lupe.entry.person_id))} alt="" title="{lupe.entry.name} auf einem bestätigten Foto" />
      {/if}
      <strong>Ist das {lupe.entry.name}?</strong>
    {/snippet}
    {#snippet actions()}
      <button class="primary" disabled={answering.has(lupe.entry.group_id)} onclick={() => answerInLupe(true)}>Ja, das ist {lupe.entry.name}</button>
      <button disabled={answering.has(lupe.entry.group_id)} onclick={() => answerInLupe(false)}>Nein</button>
    {/snippet}
  </FotoLupe>
{/if}
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
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-top: 16px;
  }
  .toolbar .find {
    flex: 1 1 220px;
    max-width: 360px;
  }
  .toolbar button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .suggestion .face {
    padding: 0;
    border: 0;
    background: transparent;
  }
  .pic {
    position: relative;
  }
  .zoom {
    position: absolute;
    top: 0;
    right: -4px;
    width: 32px;
    height: 32px;
    min-height: 0;
    padding: 0;
    border-radius: 50%;
    background: var(--surface);
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
  }
  .ref {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid #fff;
  }
  .suggestion .name {
    white-space: normal;
    text-align: center;
  }
  .answers {
    display: flex;
    gap: 6px;
    margin-top: 4px;
  }
  .answers button {
    min-width: 56px;
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
