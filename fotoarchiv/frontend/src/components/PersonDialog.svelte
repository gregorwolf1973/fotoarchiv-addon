<script>
  import { api, cropUrl, thumbUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { locale, t } from '../lib/i18n.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // person: { id, name, count, face_id }; persons: alle Personen (zum Zusammenführen)
  // onshowphotos(person); ontask(task) verfolgt Umbenennen und Zusammenführen im Hintergrund
  let { person, persons = [], canEdit = true, onclose, onchanged, onshowphotos, ontask } = $props();

  const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' });

  let faces = $state([]);
  let samples = $state.raw([]); // Fotos einer Person ohne erkannte Gesichter
  // svelte-ignore state_referenced_locally
  let name = $state(person.name);
  let busy = $state(false);
  let merging = $state(false);
  let deleting = $state(false);
  let search = $state('');
  let target = $state(null);

  const others = $derived(persons.filter((p) => p.id !== person.id));
  const matches = $derived.by(() => {
    const needle = search.trim().toLocaleLowerCase();
    return others.filter((p) => !needle || p.name.toLocaleLowerCase().includes(needle)).slice(0, 50);
  });
  // Umbenennen auf den Namen einer anderen Person ist ebenfalls ein Zusammenführen
  const renameTarget = $derived(
    others.find((p) => p.name.toLocaleLowerCase() === name.trim().toLocaleLowerCase()) ?? null,
  );
  const initials = (text) =>
    text
      .split(/\s+/)
      .map((part) => part[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();
  const photos = (n) => (n === 1 ? t('{n} Foto', { n: formatNumber(n) }) : t('{n} Fotos', { n: formatNumber(n) }));

  function startMerge(candidate = null) {
    merging = true;
    search = '';
    target = candidate;
  }

  async function merge() {
    if (!target || busy) return;
    busy = true;
    try {
      const { task } = await api.mergePerson(person.id, target.id);
      if (task) ontask(task);
      else notify(t('„{name}“ mit „{target}“ zusammengeführt', { name: person.name, target: target.name }));
      onchanged();
      onclose();
    } catch (err) {
      notifyError(err);
    } finally {
      busy = false;
    }
  }

  function load() {
    api.personFaces(person.id).then((list) => {
      faces = list;
      // Nur aus Metadaten bekannt: ein paar Fotos zeigen, damit man sieht, wer gemeint ist
      if (!list.length && person.count) {
        api.index({ persons: [{ id: person.id }] }, false).then((index) => (samples = index.items.slice(0, 12)), notifyError);
      }
    }, notifyError);
  }
  $effect(load);

  async function removePerson() {
    if (busy) return;
    busy = true;
    try {
      const { task } = await api.deletePerson(person.id);
      if (task) ontask(task);
      else notify(t('„{name}“ entfernt', { name: person.name }));
      onchanged();
      onclose();
    } catch (err) {
      notifyError(err);
    } finally {
      busy = false;
    }
  }

  async function rename(e) {
    e.preventDefault();
    const clean = name.trim();
    if (!clean || clean === person.name || busy) return;
    busy = true;
    try {
      const { task } = await api.renamePerson(person.id, clean);
      if (task) ontask(task);
      else notify(t('Umbenannt'));
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
      notify(t('Gesicht von „{name}“ gelöst', { name: person.name }));
      onchanged();
    } catch (err) {
      notifyError(err);
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && (merging ? (merging = false) : onclose())} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="person-title">
    <header>
      <h2 id="person-title">{person.name}</h2>
      <button class="icon" onclick={onclose} title={t('Schließen')}><Icon name="close" /></button>
    </header>

    {#if canEdit && merging}
      <div class="merge">
        {#if target}
          <h3>{t('Zusammenführen')}</h3>
          <div class="preview">
            <div class="pair">
              <span class="who">
                {#if person.face_id}<img src={cropUrl(person.face_id)} alt="" />{:else}<span class="initials">{initials(person.name)}</span>{/if}
                <strong>{person.name}</strong><small>{photos(person.count)}</small>
              </span>
              <Icon name="right" size={32} />
              <span class="who">
                {#if target.face_id}<img src={cropUrl(target.face_id)} alt="" />{:else}<span class="initials">{initials(target.name)}</span>{/if}
                <strong>{target.name}</strong><small>{photos(target.count)}</small>
              </span>
            </div>
            <ul>
              <li>{t('{photos} von „{name}“ bekommen den Namen „{target}“ – direkt in der Datei.', { photos: photos(person.count), name: person.name, target: target.name })}</li>
              {#if faces.length}
                <li>{t('{n} erkannte Gesichter gehören danach zu „{target}“, neue Fotos werden ihr zugeordnet.', { n: formatNumber(faces.length), target: target.name })}</li>
              {/if}
              <li>{t('„{name}“ verschwindet aus der Liste. Das lässt sich nicht per Klick rückgängig machen.', { name: person.name })}</li>
            </ul>
          </div>
          <footer>
            <button onclick={() => (target = null)}>{t('Andere Person wählen')}</button>
            <button class="primary" disabled={busy} onclick={merge}>{busy ? t('Wird gestartet …') : t('Zusammenführen')}</button>
          </footer>
        {:else}
          <h3>{t('Mit welcher Person zusammenführen?')}</h3>
          <!-- svelte-ignore a11y_autofocus -->
          <input type="text" bind:value={search} placeholder={t('Person suchen')} autofocus />
          <ul class="choices">
            {#each matches as candidate (candidate.id)}
              <li>
                <button onclick={() => (target = candidate)}>
                  {#if candidate.face_id}<img src={cropUrl(candidate.face_id)} alt="" loading="lazy" />{:else}<span class="initials small">{initials(candidate.name)}</span>{/if}
                  <span class="grow">{candidate.name}</span>
                  <small>{photos(candidate.count)}</small>
                </button>
              </li>
            {:else}
              <li class="muted">{t('Keine andere Person gefunden.')}</li>
            {/each}
          </ul>
          <footer><button onclick={() => (merging = false)}>{t('Abbrechen')}</button></footer>
        {/if}
      </div>
    {:else if canEdit}
      <form class="rename" onsubmit={(e) => (renameTarget ? (e.preventDefault(), startMerge(renameTarget)) : rename(e))}>
        <label class="field">
          {t('Name')}
          <input type="text" bind:value={name} required list="person-names" />
          <datalist id="person-names">{#each others as other (other.id)}<option value={other.name}></option>{/each}</datalist>
        </label>
        <button type="submit" disabled={busy || !name.trim() || name.trim() === person.name}>
          {renameTarget ? t('Zusammenführen …') : t('Umbenennen')}
        </button>
      </form>
      <p class="hint">
        {#if renameTarget}
          {t('„{name}“ gibt es schon – beide Personen werden zusammengeführt.', { name: renameTarget.name })}
        {:else}
          {t('Der neue Name wird in alle {n} Fotos geschrieben.', { n: formatNumber(person.count) })}
        {/if}
      </p>
      {#if others.length}
        <button class="merge-open" onclick={() => startMerge()}>{t('Mit anderer Person zusammenführen …')}</button>
      {/if}
      <div class="remove-person">
        {#if deleting}
          <p>
            {t('Der Name „{name}“ wird aus {photos} entfernt – direkt in den Dateien. Die Fotos selbst bleiben.', { name: person.name, photos: photos(person.count) })}
            {#if faces.length}{t('Die {n} erkannten Gesichter werden wieder zu unbekannten Gesichtern.', { n: formatNumber(faces.length) })}{/if}
            {t('Stammt der Name aus Gesichtsmarkierungen eines anderen Programms, werden diese Markierungen dabei mit entfernt.')}
          </p>
          <div class="row">
            <button onclick={() => (deleting = false)}>{t('Abbrechen')}</button>
            <button class="danger" disabled={busy} onclick={removePerson}>{busy ? t('Wird gestartet …') : t('Person entfernen')}</button>
          </div>
        {:else}
          <button class="remove-open" onclick={() => (deleting = true)}><Icon name="delete" size={18} /> {t('Person entfernen …')}</button>
        {/if}
      </div>
    {/if}

    {#if !merging}
    <div class="section">
      <h3>{t('Erkannte Gesichter')} <span class="muted">{formatNumber(faces.length)}</span></h3>
      {#if faces.length}
        {#if canEdit}<p class="hint">{t('Falsch zugeordnet? Mit ✕ lösen – der Name wird aus dem Foto entfernt und dort nicht wieder vorgeschlagen.')}</p>{/if}
        <div class="faces">
          {#each faces as face (face.id)}
            <div class="face" title={dateFormat.format(face.taken_ts * 1000)}>
              <img src={cropUrl(face.id)} alt="" loading="lazy" />
              {#if !face.confirmed}<span class="auto" title={t('automatisch erkannt')}>{t('auto')}</span>{/if}
              {#if canEdit}<button class="remove" onclick={() => remove(face)} title={t('Nicht {name}', { name: person.name })}><Icon name="close" size={16} /></button>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <p class="muted">
          {t('Keine Gesichter zugeordnet – der Name steht nur in den Metadaten der Fotos, meist aus einem anderen Programm (Picasa, Google Fotos, Lightroom, Windows-Fotogalerie).')}
        </p>
        {#if samples.length}
          <div class="samples">
            {#each samples as item (item[0])}
              <img src={thumbUrl(item, true)} alt="" loading="lazy" />
            {/each}
          </div>
        {/if}
      {/if}
    </div>

    {/if}

    {#if !merging}
    <footer>
      <button onclick={onclose}>{t('Schließen')}</button>
      <button class="primary" onclick={() => onshowphotos(person)}><Icon name="images" size={18} /> {t('Fotos anzeigen')}</button>
    </footer>
    {/if}
  </div>
</div>

<style>
  .wide {
    width: min(760px, 100%);
  }
  .merge-open {
    margin-top: 12px;
  }
  .remove-person {
    margin-top: 12px;
  }
  .remove-person p {
    margin: 0 0 10px;
    font-size: 0.9rem;
    line-height: 1.5;
  }
  .remove-person .row {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .remove-open {
    color: var(--danger);
  }
  .samples {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 6px;
    margin-top: 12px;
  }
  .samples img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    border-radius: 6px;
    background: var(--placeholder);
    display: block;
  }
  .merge h3 {
    margin-bottom: 10px;
  }
  .merge input {
    width: 100%;
  }
  .choices {
    max-height: 40vh;
    margin: 8px 0 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }
  .choices button {
    width: 100%;
    min-height: 52px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    font-weight: 400;
    text-align: left;
  }
  .choices img,
  .initials.small {
    width: 40px;
    height: 40px;
    flex: none;
    border-radius: 50%;
    object-fit: cover;
  }
  .grow {
    flex: 1;
  }
  small {
    color: var(--muted);
  }
  .preview {
    padding: 16px;
    border-radius: 12px;
    background: var(--chip);
  }
  .pair {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: var(--muted);
  }
  .who {
    display: grid;
    justify-items: center;
    gap: 2px;
    color: var(--text);
    text-align: center;
  }
  .who img,
  .who .initials {
    width: 84px;
    height: 84px;
    border-radius: 50%;
    object-fit: cover;
  }
  .initials {
    display: grid;
    place-items: center;
    background: var(--placeholder);
    color: var(--muted);
    font-weight: 500;
  }
  .who .initials {
    font-size: 1.6rem;
  }
  .preview ul {
    margin: 14px 0 0;
    padding-left: 18px;
    font-size: 0.9rem;
    line-height: 1.5;
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
