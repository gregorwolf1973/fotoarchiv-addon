<script>
  import { api } from '../lib/api.js';
  import { notify, notifyError } from '../lib/notices.svelte.js';
  import Confirm from './Confirm.svelte';
  import Icon from './Icon.svelte';

  let { onclose } = $props();

  const ROLES = { viewer: 'Ansehen', uploader: 'Hochladen + Bearbeiten (ohne Löschen)', editor: 'Bearbeiten' };
  const EVENTS = {
    auth_ok: 'Anmeldung',
    auth_fail: 'Fehlversuch',
    logout: 'Abmeldung',
    rate_limited: 'Gesperrt',
    unauthorized: 'Ohne Anmeldung',
    forbidden: 'Keine Berechtigung',
    not_found: 'Unbekannter Pfad',
    change: 'Änderung',
  };
  const dateTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' });

  let tab = $state('users');
  let access = $state(null);
  let users = $state([]);
  let sessions = $state([]);
  let locks = $state({ locks: [], counters: [] });
  let entries = $state([]);
  let eventFilter = $state('');
  let crowdsec = $state(null);
  let confirm = $state(null);
  let busy = $state(false);

  let form = $state({ username: '', display_name: '', password: '', role: 'viewer' });
  let passwordFor = $state(null);
  let newPassword = $state('');

  async function run(action, success) {
    busy = true;
    try {
      await action();
      if (success) notify(success);
      await load();
    } catch (e) {
      notifyError(e);
    } finally {
      busy = false;
    }
  }

  async function load() {
    try {
      access = await api.admin.access();
      if (tab === 'users') users = await api.admin.users();
      if (tab === 'locks') [sessions, locks] = await Promise.all([api.admin.sessions(), api.admin.locks()]);
      if (tab === 'log') entries = await api.admin.log(eventFilter);
      if (tab === 'crowdsec') crowdsec = await api.admin.crowdsec();
    } catch (e) {
      notifyError(e);
    }
  }

  $effect(() => {
    tab;
    eventFilter;
    load();
    if (tab !== 'locks' && tab !== 'log') return;
    const timer = setInterval(load, 5000); // Sperren und Protokoll ändern sich laufend
    return () => clearInterval(timer);
  });

  function generate() {
    const alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return [...bytes].map((b) => alphabet[b % alphabet.length]).join('');
  }

  const createUser = (e) => {
    e.preventDefault();
    const user = { ...form };
    run(async () => {
      await api.admin.createUser(user);
      form = { username: '', display_name: '', password: '', role: 'viewer' };
    }, `Konto „${user.username}“ angelegt`);
  };

  const duration = (seconds) => (seconds >= 3600 ? `${Math.round(seconds / 360) / 10} h` : `${Math.ceil(seconds / 60)} min`);
  const when = (value) => (value ? dateTime.format(typeof value === 'number' ? value * 1000 : new Date(value)) : '–');
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && !confirm && onclose()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="modal panel" role="dialog" aria-modal="true" aria-labelledby="access-title">
    <header>
      <h2 id="access-title"><Icon name="shield" size={22} /> Zugang übers Internet</h2>
      <button class="icon" onclick={onclose} title="Schließen"><Icon name="close" /></button>
    </header>

    {#if access}
      <div class="status" class:off={!access.enabled}>
        {#if access.enabled}
          <strong>Internetzugang aktiv</strong> auf Port {access.port} des Add-ons. Veröffentliche ihn nur über einen Reverse
          Proxy mit TLS (z. B. Nginx Proxy Manager oder Cloudflare Tunnel).
          <div class="muted">
            Vertrauenswürdige Proxys: {access.trusted_proxies.join(', ')} · Sitzung {access.session_hours} h ·
            Cookie {access.cookie_secure ? 'nur über HTTPS' : 'auch über HTTP (nur zum Testen!)'}
          </div>
        {:else}
          <strong>Internetzugang ist ausgeschaltet.</strong> Konten lassen sich schon anlegen; aktiviert wird er in den
          Add-on-Einstellungen mit <code>public_enabled: true</code>.
        {/if}
      </div>
    {/if}

    <nav class="tabs">
      {#each [['users', 'Konten'], ['locks', 'Sitzungen & Sperren'], ['log', 'Protokoll'], ['crowdsec', 'CrowdSec']] as [id, label]}
        <button class:active={tab === id} onclick={() => (tab = id)}>{label}</button>
      {/each}
    </nav>

    {#if tab === 'users'}
      <table>
        <thead><tr><th>Konto</th><th>Rolle</th><th>Aktiv</th><th>Zuletzt angemeldet</th><th></th></tr></thead>
        <tbody>
          {#each users as user (user.id)}
            <tr class:disabled={!user.enabled}>
              <td><strong>{user.username}</strong>{#if user.display_name}<div class="muted">{user.display_name}</div>{/if}</td>
              <td>
                <select value={user.role} disabled={busy} onchange={(e) => run(() => api.admin.updateUser(user.id, { role: e.currentTarget.value }), 'Rolle geändert')}>
                  {#each Object.entries(ROLES) as [value, label]}<option {value}>{label}</option>{/each}
                </select>
              </td>
              <td>
                <input type="checkbox" checked={user.enabled} disabled={busy} title={user.enabled ? 'Sperren' : 'Freigeben'}
                  onchange={(e) => run(() => api.admin.updateUser(user.id, { enabled: e.currentTarget.checked }))} />
              </td>
              <td>{when(user.last_login)}{#if user.sessions}<div class="muted">{user.sessions} aktive Sitzung{user.sessions > 1 ? 'en' : ''}</div>{/if}</td>
              <td class="actions">
                <button class="small" onclick={() => ((passwordFor = user), (newPassword = generate()))}>Passwort</button>
                <button class="icon small" title="Konto löschen"
                  onclick={() => (confirm = { title: `Konto „${user.username}“ löschen?`, text: 'Alle Sitzungen dieses Kontos werden beendet.', action: () => run(() => api.admin.deleteUser(user.id), 'Konto gelöscht') })}>
                  <Icon name="delete" size={18} />
                </button>
              </td>
            </tr>
            {#if passwordFor?.id === user.id}
              <tr class="inline">
                <td colspan="5">
                  <form onsubmit={(e) => (e.preventDefault(), run(() => api.admin.updateUser(user.id, { password: newPassword }), 'Passwort geändert – alle Sitzungen beendet').then(() => (passwordFor = null)))}>
                    <input type="text" bind:value={newPassword} minlength={access?.password_min ?? 10} required autocomplete="off" />
                    <button type="button" class="small" onclick={() => (newPassword = generate())}>Neu erzeugen</button>
                    <button type="submit" class="small primary" disabled={busy}>Speichern</button>
                    <button type="button" class="icon small" onclick={() => (passwordFor = null)}><Icon name="close" size={16} /></button>
                  </form>
                </td>
              </tr>
            {/if}
          {:else}
            <tr><td colspan="5" class="muted">Noch keine Konten.</td></tr>
          {/each}
        </tbody>
      </table>

      <form class="create" onsubmit={createUser}>
        <h3>Neues Konto</h3>
        <label class="field">Benutzername<input type="text" bind:value={form.username} required pattern="[a-zA-Z0-9._@\-]{'{2,64}'}" autocomplete="off" /></label>
        <label class="field">Anzeigename<input type="text" bind:value={form.display_name} maxlength="80" autocomplete="off" /></label>
        <label class="field">
          Passwort (mind. {access?.password_min ?? 10} Zeichen)
          <span class="row">
            <input type="text" bind:value={form.password} minlength={access?.password_min ?? 10} required autocomplete="off" />
            <button type="button" class="small" onclick={() => (form.password = generate())}>Erzeugen</button>
          </span>
        </label>
        <label class="field">
          Rolle
          <select bind:value={form.role}>{#each Object.entries(ROLES) as [value, label]}<option {value}>{label}</option>{/each}</select>
        </label>
        <p class="muted hint">
          <strong>Ansehen:</strong> Fotos, Karte und Personen ansehen und herunterladen.
          <strong>Hochladen + Bearbeiten (ohne Löschen):</strong> zusätzlich hochladen, Schlagworte, Personen, Orte und Datum ändern, drehen und Gesichter benennen – aber keine Bilder löschen.
          <strong>Bearbeiten:</strong> zusätzlich hochladen, beschriften, drehen, in den Papierkorb legen und Gesichter benennen.
          Import, Abgleich und endgültiges Löschen gibt es nur hier in Home Assistant.
        </p>
        <button type="submit" class="primary" disabled={busy}><Icon name="plus" size={18} /> Konto anlegen</button>
      </form>
    {:else if tab === 'locks'}
      <h3>Aktive Sitzungen</h3>
      <table>
        <thead><tr><th>Konto</th><th>Adresse</th><th>Zuletzt aktiv</th><th>Gültig bis</th><th></th></tr></thead>
        <tbody>
          {#each sessions as session (session.id)}
            <tr>
              <td>{session.username}</td>
              <td>{session.ip}<div class="muted ua" title={session.user_agent}>{session.user_agent}</div></td>
              <td>{when(session.last_seen)}</td>
              <td>{when(session.expires_at)}</td>
              <td class="actions"><button class="small" onclick={() => run(() => api.admin.revokeSession(session.id), 'Sitzung beendet')}>Beenden</button></td>
            </tr>
          {:else}
            <tr><td colspan="5" class="muted">Niemand angemeldet.</td></tr>
          {/each}
        </tbody>
      </table>

      <h3>Sperren</h3>
      <p class="muted hint">
        Nach 10 Fehlversuchen in 15 Minuten wird das Konto gesperrt, nach 30 die Adresse (zu Hause teilt sich die Familie
        eine): zuerst 15 Minuten, bei Wiederholung doppelt so lange, höchstens 24 Stunden. Wer ohne Anmeldung wiederholt die API abtastet, wird ebenfalls gesperrt.
      </p>
      <table>
        <thead><tr><th>Art</th><th>Ziel</th><th>Noch</th><th>Sperren</th><th></th></tr></thead>
        <tbody>
          {#each locks.locks as lock (lock.key)}
            <tr>
              <td>{{ ip: 'Adresse', user: 'Konto', ban: 'Scanner' }[lock.kind] ?? lock.kind}</td>
              <td>{lock.target}</td>
              <td>{duration(lock.remaining)}</td>
              <td>{lock.strikes}×</td>
              <td class="actions"><button class="small" onclick={() => run(() => api.admin.unlock(lock.key), 'Sperre aufgehoben')}>Aufheben</button></td>
            </tr>
          {:else}
            <tr><td colspan="5" class="muted">Keine aktiven Sperren.</td></tr>
          {/each}
        </tbody>
      </table>
      {#if locks.counters.length}
        <h3>Fehlversuche (letzte 15 Minuten)</h3>
        <table>
          <tbody>
            {#each locks.counters as counter (counter.key)}
              <tr>
                <td>{counter.kind === 'ip' ? 'Adresse' : 'Konto'}</td><td>{counter.target}</td><td>{counter.count} von 10</td>
                <td class="actions"><button class="small" onclick={() => run(() => api.admin.unlock(counter.key), 'Zähler zurückgesetzt')}>Zurücksetzen</button></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {:else if tab === 'log'}
      <div class="toolbar">
        <select bind:value={eventFilter}>
          <option value="">Alle Ereignisse</option>
          {#each Object.entries(EVENTS) as [value, label]}<option {value}>{label}</option>{/each}
        </select>
        <span class="grow"></span>
        <button class="small" onclick={() => (confirm = { title: 'Protokoll leeren?', text: 'Alle Einträge werden gelöscht.', action: () => run(() => api.admin.clearLog(), 'Protokoll geleert') })}>Leeren</button>
      </div>
      <table class="log">
        <thead><tr><th>Zeit</th><th>Ereignis</th><th>Adresse</th><th>Konto</th><th>Details</th></tr></thead>
        <tbody>
          {#each entries as entry, i (i)}
            <tr class={entry.event}>
              <td>{when(entry.ts)}</td>
              <td>{EVENTS[entry.event] ?? entry.event}</td>
              <td>{entry.ip ?? ''}</td>
              <td>{entry.user ?? ''}</td>
              <td class="detail" title={entry.ua ?? ''}>{[entry.detail, entry.path].filter(Boolean).join(' ')}</td>
            </tr>
          {:else}
            <tr><td colspan="5" class="muted">Keine Einträge.</td></tr>
          {/each}
        </tbody>
      </table>
    {:else if tab === 'crowdsec' && crowdsec}
      <p>
        Mit dem CrowdSec-Add-on werden Angreifer nicht nur hier, sondern schon an der Firewall bzw. bei Cloudflare
        gesperrt. Die Einrichtung kopiert Parser, Szenarien und die Log-Quelle in dessen Konfiguration; das
        Zugriffsprotokoll wird dafür zusätzlich nach <code>{crowdsec.export_path}</code> geschrieben.
      </p>
      <ul class="checks">
        <li class:ok={crowdsec.config_found}>CrowdSec-Konfiguration {crowdsec.config_found ? 'gefunden' : 'nicht gefunden'} <span class="muted">({crowdsec.config_dir})</span></li>
        {#each Object.entries(crowdsec.installed) as [file, ok]}<li class:ok>{file}</li>{/each}
        <li class:ok={crowdsec.export_active}>Protokoll-Export {crowdsec.export_active ? 'aktiv' : 'inaktiv'}</li>
      </ul>
      <button class="primary" disabled={busy || !crowdsec.config_found}
        onclick={() => run(() => api.admin.installCrowdsec(), 'Eingerichtet – bitte das CrowdSec-Add-on neu starten')}>
        <Icon name="shield" size={18} /> {crowdsec.all_installed ? 'Erneut einrichten' : 'In CrowdSec einrichten'}
      </button>
    {/if}
  </div>
</div>

{#if confirm}
  <Confirm title={confirm.title} text={confirm.text} confirmLabel="OK" danger oncancel={() => (confirm = null)}
    onconfirm={() => {
      const action = confirm.action;
      confirm = null;
      action();
    }} />
{/if}

<style>
  .panel {
    width: min(920px, 100%);
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  h3 {
    margin: 20px 0 8px;
    font-size: 1rem;
    font-weight: 500;
  }
  .status {
    padding: 12px 14px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--success) 14%, var(--surface));
    line-height: 1.5;
  }
  .status.off {
    background: var(--warning-bg);
  }
  .tabs {
    display: flex;
    gap: 4px;
    margin: 16px 0 8px;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }
  .tabs button {
    border: 0;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    white-space: nowrap;
  }
  .tabs button.active {
    border-bottom-color: var(--accent);
    color: var(--accent);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }
  th {
    text-align: left;
    font-weight: 500;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    padding: 6px;
  }
  td {
    padding: 6px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  tr.disabled td {
    opacity: 0.55;
  }
  .actions {
    text-align: right;
    white-space: nowrap;
  }
  .inline form {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  button.small {
    min-height: 30px;
    padding: 0 10px;
    font-size: 0.8rem;
  }
  select {
    min-height: 32px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    font: inherit;
  }
  .create {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0 12px;
    margin-top: 12px;
  }
  .create h3,
  .create .hint,
  .create > button {
    grid-column: 1 / -1;
  }
  .create > button {
    justify-self: start;
    margin-top: 12px;
  }
  .create > label {
    min-width: 0; /* sonst sprengt das Passwortfeld mit Knopf die Spalte */
  }
  .row {
    display: flex;
    gap: 6px;
    min-width: 0;
  }
  .row input {
    flex: 1;
    width: 100%;
    min-width: 0;
  }
  .hint {
    font-size: 0.85rem;
    line-height: 1.5;
  }
  .muted {
    color: var(--muted);
  }
  .ua {
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.75rem;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .grow {
    flex: 1;
  }
  .log .detail {
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .log tr.auth_fail td,
  .log tr.rate_limited td {
    color: var(--danger);
  }
  .log tr.auth_ok td {
    color: var(--success);
  }
  .checks {
    padding-left: 20px;
    line-height: 1.8;
  }
  .checks li {
    color: var(--danger);
  }
  .checks li.ok {
    color: var(--success);
  }
  @media (max-width: 639px) {
    table {
      display: block;
      overflow-x: auto;
    }
  }
</style>
