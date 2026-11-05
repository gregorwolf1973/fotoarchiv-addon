<script>
  import { t } from '../lib/i18n.js';
  import ChipInput from './ChipInput.svelte';
  import Icon from './Icon.svelte';

  let { kind, count, suggestions, onsave, oncancel } = $props();

  const title = $derived(kind === 'tags' ? t('Schlagworte ändern') : t('Personen ändern'));
  const icon = $derived(kind === 'tags' ? 'tag' : 'person');
  let add = $state([]);
  let remove = $state([]);
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="label-title">
    <header>
      <h2 id="label-title">{title}</h2>
      <button class="icon" onclick={oncancel} title={t('Schließen')}><Icon name="close" /></button>
    </header>
    <p>{t('Gilt für {count} ausgewählte Dateien. Andere vorhandene Einträge bleiben erhalten.', { count })}</p>
    <div class="field">
      <span>{t('Hinzufügen')}</span>
      <ChipInput values={add} {suggestions} {icon} placeholder={t('Name eingeben, Enter')} onchange={(v) => (add = v)} />
    </div>
    <div class="field">
      <span>{t('Entfernen')}</span>
      <ChipInput values={remove} {suggestions} {icon} placeholder={t('Name eingeben, Enter')} onchange={(v) => (remove = v)} />
    </div>
    <footer>
      <button onclick={oncancel}>{t('Abbrechen')}</button>
      <button class="primary" disabled={!add.length && !remove.length} onclick={() => onsave(add, remove)}>
        {t('Übernehmen')}
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
