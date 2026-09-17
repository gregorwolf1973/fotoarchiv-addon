<script>
  import { api } from '../lib/api.js';
  import Icon from './Icon.svelte';

  // cookieBlocked: sicheres Cookie über http – der Browser würde die Anmeldung verwerfen
  let { cookieBlocked = false, onlogin } = $props();

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let busy = $state(false);

  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    busy = true;
    error = '';
    try {
      const session = await api.login(username.trim(), password);
      password = '';
      onlogin(session);
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <form class="card" onsubmit={submit} autocomplete="on">
    <div class="brand">
      <Icon name="images" size={40} />
      <h1>Fotoarchiv</h1>
    </div>
    {#if cookieBlocked}
      <p class="warning">
        <Icon name="alert" size={18} />
        Diese Seite ist nicht über HTTPS aufgerufen. Die Anmeldung funktioniert nur über den Reverse Proxy mit TLS –
        oder, nur zum Testen im eigenen Netz, mit <code>public_cookie_secure: false</code>.
      </p>
    {/if}
    <label class="field">
      Benutzername
      <!-- svelte-ignore a11y_autofocus -->
      <input type="text" bind:value={username} autocomplete="username" autocapitalize="none" autocorrect="off" required autofocus />
    </label>
    <label class="field">
      Passwort
      <input type="password" bind:value={password} autocomplete="current-password" required />
    </label>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <button type="submit" class="primary" disabled={busy || !username.trim() || !password}>
      <Icon name="lock" size={18} />
      {busy ? 'Anmelden …' : 'Anmelden'}
    </button>
  </form>
</div>

<style>
  .login {
    min-height: 100vh;
    min-height: 100dvh;
    display: grid;
    place-items: center;
    padding: 16px;
    box-sizing: border-box;
  }
  .card {
    display: grid;
    gap: 4px;
    width: min(380px, 100%);
    padding: 28px 24px;
    border-radius: 16px;
    background: var(--surface);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.12);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
    color: var(--accent);
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--text);
  }
  input {
    width: 100%;
  }
  button {
    justify-content: center;
    margin-top: 16px;
    min-height: 42px;
  }
  .error {
    margin: 12px 0 0;
    color: var(--danger);
  }
  .warning {
    display: flex;
    gap: 8px;
    margin: 0 0 8px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--warning-bg);
    font-size: 0.875rem;
    line-height: 1.45;
  }
</style>
