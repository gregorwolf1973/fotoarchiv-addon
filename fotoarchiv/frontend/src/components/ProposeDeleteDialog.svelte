<script>
  import { t } from '../lib/i18n.js';
  import Icon from './Icon.svelte';

  // Für Konten, die selbst nicht löschen dürfen: der Vorschlag geht an den Admin in Home Assistant
  let { count = 1, onsave, oncancel } = $props();

  let reason = $state('');
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="propose-title">
    <form onsubmit={(e) => (e.preventDefault(), onsave(reason.trim()))}>
      <header>
        <h2 id="propose-title">{t('Löschen vorschlagen')}</h2>
        <button type="button" class="icon" onclick={oncancel} title={t('Schließen')}><Icon name="close" /></button>
      </header>
      <p>
        {count === 1
          ? t('Dieses Foto wird dem Admin zum Löschen vorgeschlagen. Er entscheidet, ob es in den Papierkorb kommt.')
          : t('Diese {count} Fotos werden dem Admin zum Löschen vorgeschlagen. Er entscheidet, ob sie in den Papierkorb kommen.', { count })}
      </p>
      <label class="field">
        {t('Grund (freiwillig)')}
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" bind:value={reason} maxlength="300" placeholder={t('z. B. unscharf, doppelt, falsches Foto')} autofocus />
      </label>
      <footer>
        <button type="button" onclick={oncancel}>{t('Abbrechen')}</button>
        <button type="submit" class="primary">{t('Vorschlagen')}</button>
      </footer>
    </form>
  </div>
</div>
