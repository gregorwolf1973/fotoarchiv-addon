<script>
  import { api } from '../lib/api.js';
  import { notify } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // Eigenes Passwort ändern (nur im Internetzugang; über Home Assistant gibt es kein Passwort)
  let { onclose } = $props();

  const MIN = 10;
  let current = $state('');
  let next = $state('');
  let repeat = $state('');
  let busy = $state(false);
  let error = $state('');

  const problem = $derived(
    !next ? '' : next.length < MIN ? `mindestens ${MIN} Zeichen` : repeat && repeat !== next ? 'Wiederholung stimmt nicht überein' : '',
  );
  const valid = $derived(current && next.length >= MIN && next === repeat);

  async function save() {
    if (!valid || busy) return;
    busy = true;
    error = '';
    try {
      await api.changePassword(current, next);
      notify('Passwort geändert. Andere Geräte wurden abgemeldet.');
      onclose();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="password-title">
    <form onsubmit={(e) => (e.preventDefault(), save())}>
      <header>
        <h2 id="password-title">Passwort ändern</h2>
        <button type="button" class="icon" onclick={onclose} title="Schließen"><Icon name="close" /></button>
      </header>
      <p>Danach bleibst du hier angemeldet, auf allen anderen Geräten musst du dich neu anmelden.</p>
      <label class="field">
        Bisheriges Passwort
        <!-- svelte-ignore a11y_autofocus -->
        <input type="password" bind:value={current} autocomplete="current-password" required autofocus />
      </label>
      <label class="field">
        Neues Passwort (mind. {MIN} Zeichen)
        <input type="password" bind:value={next} autocomplete="new-password" minlength={MIN} required />
      </label>
      <label class="field">
        Neues Passwort wiederholen
        <input type="password" bind:value={repeat} autocomplete="new-password" required />
      </label>
      {#if problem}<p class="hint">{problem}</p>{/if}
      {#if error}<p class="error">{error}</p>{/if}
      <footer>
        <button type="button" onclick={onclose}>Abbrechen</button>
        <button type="submit" class="primary" disabled={!valid || busy}>Ändern</button>
      </footer>
    </form>
  </div>
</div>

<style>
  .hint {
    color: var(--warning);
    font-size: 0.85rem;
  }
  .error {
    color: var(--danger);
    font-size: 0.9rem;
  }
</style>
