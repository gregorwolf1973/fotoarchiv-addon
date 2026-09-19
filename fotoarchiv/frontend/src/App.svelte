<script>
  import { onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { api, auth, cache, filterQuery } from './lib/api.js';
  import { ZOOM_LEVELS } from './lib/layout.js';
  import { formatBytes, formatNumber } from './lib/format.js';
  import { notify, notifyError } from './lib/notices.svelte.js';
  import { isIos, openedFromShare, registerServiceWorker, standalone, takeShared } from './lib/pwa.js';
  import AccessPanel from './components/AccessPanel.svelte';
  import PasswordDialog from './components/PasswordDialog.svelte';
  import Confirm from './components/Confirm.svelte';
  import DateDialog from './components/DateDialog.svelte';
  import DuplicatesView from './components/DuplicatesView.svelte';
  import Gallery from './components/Gallery.svelte';
  import Icon from './components/Icon.svelte';
  import ImportPanel from './components/ImportPanel.svelte';
  import LabelDialog from './components/LabelDialog.svelte';
  import LocationDialog from './components/LocationDialog.svelte';
  import Login from './components/Login.svelte';
  import MapView from './components/MapView.svelte';
  import PeopleView from './components/PeopleView.svelte';
  import Notices from './components/Notices.svelte';
  import SearchBar from './components/SearchBar.svelte';
  import StorageView from './components/StorageView.svelte';
  import Uploader from './components/Uploader.svelte';
  import Viewer from './components/Viewer.svelte';

  const NO_FILTERS = { tags: [], persons: [], start: '', end: '', q: '' };
  const ZOOM_KEY = 'fotoarchiv.zoom';

  let info = $state(null);
  let items = $state.raw([]); // groß und unveränderlich: kein tiefer Proxy
  let labels = $state.raw({ tags: [], persons: [] });
  let tasks = $state.raw([]);
  let loaded = $state(false);
  let failure = $state('');
  let view = $state('photos'); // photos | map | people | trash | duplicates | storage
  let filters = $state.raw(NO_FILTERS);
  let openId = $state(null);
  let viewerIds = $state.raw(null); // eigene Blätter-Reihenfolge, z. B. Fotos auf der Karte
  let viewerList = $state.raw(null); // eigene Einträge, die nicht im Index stehen müssen (Duplikate)
  let showImport = $state(false);
  let searchOpen = $state(false);
  let dialog = $state(null);
  let zoom = $state(readZoom());
  let listKey = $state(''); // neue Suche/Ansicht: Galerie neu aufbauen, oben beginnen
  let session = $state(null); // { authenticated, public, role, user, csrf }
  let showAccess = $state(false);
  let showPassword = $state(false);
  let installPrompt = $state(null); // Android/Chrome: "App installieren" anbieten
  let iosHint = $state(false);
  const IOS_HINT_KEY = 'fotoarchiv.iosHint';
  let uploader = $state();
  let fileInput = $state();

  const selected = new SvelteSet();
  let lastToggled = null;

  const trash = $derived(view === 'trash');
  // Rechte: admin = Home Assistant, editor/viewer = Konten des Internetzugangs
  const canEdit = $derived(session?.role === 'admin' || session?.role === 'editor');
  const isAdmin = $derived(session?.role === 'admin');
  const canUpload = $derived(canEdit || session?.role === 'uploader');
  const filtered = $derived(
    !trash && Boolean(filters.tags.length || filters.persons.length || filters.start || filters.end || filters.q),
  );
  const indexById = $derived(new Map(items.map((item, i) => [item[0], i])));
  const viewerItems = $derived(
    viewerList ?? (viewerIds ? viewerIds.map((id) => items[indexById.get(id)]).filter(Boolean) : items),
  );
  const openIndex = $derived(openId === null ? -1 : viewerItems.findIndex((item) => item[0] === openId));
  const missingTools = $derived(
    info
      ? Object.entries({ libvips: info.tools.vips, exiftool: info.tools.exiftool, ffmpeg: info.tools.ffmpeg })
          .filter(([, ok]) => !ok)
          .map(([name]) => name)
      : [],
  );

  // ── Laden ──────────────────────────────────────────────────────
  let revision = null;
  let loadedQuery = null;
  let labelsRevision = null;
  let sequence = 0;
  const pending = new Map(); // eigene Aufgaben: id -> { undo }

  async function refresh() {
    const seq = ++sequence;
    try {
      const next = await api.state();
      cache.instance = next.instance;
      const query = filterQuery(filters, trash);
      if (next.revision !== revision || query !== loadedQuery) {
        const index = await api.index(filters, trash);
        if (seq !== sequence) return;
        items = index.items;
        revision = index.revision;
        if (query !== loadedQuery) listKey = query;
        loadedQuery = query;
        const ids = new Set(items.map((item) => item[0]));
        for (const id of [...selected]) if (!ids.has(id)) selected.delete(id);
      }
      if (next.revision !== labelsRevision) {
        labels = await api.labels();
        labelsRevision = next.revision;
      }
      if (next.tasks_running || pending.size) await checkTasks();
      info = next;
      failure = '';
    } catch (e) {
      failure = e.message;
    } finally {
      loaded = true;
    }
  }

  async function checkTasks() {
    const all = await api.tasks();
    tasks = all.filter((t) => t.running);
    for (const [id, { undo }] of pending) {
      const task = all.find((t) => t.id === id);
      if (!task) {
        pending.delete(id);
      } else if (!task.running) {
        pending.delete(id);
        if (task.failed.length) {
          notify(`${task.label}: ${task.failed.length} fehlgeschlagen – ${task.failed[0].message}`, { kind: 'error', timeout: 10000 });
        } else {
          notify(`Erledigt: ${task.label}`, undo ? { actionLabel: 'Rückgängig', action: undo, timeout: 8000 } : {});
        }
      }
    }
  }

  let timer;
  function kick() {
    clearTimeout(timer);
    if (session?.authenticated) tick();
  }
  async function tick() {
    await refresh();
    if (!session?.authenticated) return;
    const busy = info?.importing || info?.tasks_running || pending.size;
    clearTimeout(timer);
    timer = setTimeout(tick, busy ? 1000 : info?.converting?.pending ? 5000 : 20000);
  }

  function signedIn(next) {
    session = next;
    auth.csrf = next.csrf;
    revision = null; // alles neu laden
    labelsRevision = null;
    kick();
    if (next.public) afterPublicLogin();
  }

  async function afterPublicLogin() {
    try {
      iosHint = isIos() && !standalone() && localStorage.getItem(IOS_HINT_KEY) !== '1';
    } catch {
      iosHint = false;
    }
    if (!openedFromShare()) return;
    // Aus dem Teilen-Menü der Galerie (Android): die Dateien liegen beim Service Worker bereit
    const files = await takeShared().catch(() => []);
    if (!files.length) return;
    if (!canUpload) {
      notify('Dein Konto darf keine Fotos hochladen.', { kind: 'error' });
      return;
    }
    uploader.add(files);
  }

  function hideIosHint() {
    iosHint = false;
    try {
      localStorage.setItem(IOS_HINT_KEY, '1');
    } catch {
      /* dann eben beim nächsten Mal wieder */
    }
  }

  function installApp() {
    const prompt = installPrompt;
    installPrompt = null;
    prompt?.prompt();
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      signedOut();
    }
  }

  function signedOut() {
    clearTimeout(timer);
    auth.csrf = null;
    items = [];
    info = null;
    openId = null;
    showImport = showAccess = showPassword = false;
    dialog = null;
    selected.clear();
    session = { ...(session ?? {}), authenticated: false, public: true, role: null, user: null, csrf: null };
  }

  onMount(() => {
    // Abgelaufene Sitzung: sofort zur Anmeldung, nicht weiter Anfragen schicken (die zählen sonst als Scan)
    auth.onUnauthorized = () => session?.public && session.authenticated && signedOut();
    const beforeInstall = (e) => {
      e.preventDefault(); // eigener Knopf statt der Leiste des Browsers
      installPrompt = e;
    };
    const installed = () => (installPrompt = null);
    window.addEventListener('beforeinstallprompt', beforeInstall);
    window.addEventListener('appinstalled', installed);
    api.session().then(
      (next) => {
        if (next.public) registerServiceWorker(); // auch vor der Anmeldung: installierbar ab der ersten Seite
        if (next.authenticated) signedIn(next);
        else session = next;
      },
      (e) => ((failure = e.message), (loaded = true), (session = { authenticated: true, public: false, role: 'admin' })),
    );
    return () => {
      clearTimeout(timer);
      window.removeEventListener('beforeinstallprompt', beforeInstall);
      window.removeEventListener('appinstalled', installed);
    };
  });

  // Zoomstufe pro Gerät merken; Handys starten kleiner
  function readZoom() {
    try {
      const stored = localStorage.getItem(ZOOM_KEY);
      if (stored !== null && ZOOM_LEVELS[Number(stored)]) return Number(stored);
    } catch {
      /* kein Speicher: Standard */
    }
    return window.innerWidth < 640 ? 1 : 2;
  }
  function changeZoom(step) {
    zoom = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, zoom + step));
    try {
      localStorage.setItem(ZOOM_KEY, String(zoom));
    } catch {
      /* ohne Speicher gilt die Stufe nur bis zum Neuladen */
    }
  }

  function setFilters(next) {
    filters = next;
    selected.clear();
    kick();
  }
  function setView(next) {
    view = next;
    openId = null;
    viewerIds = viewerList = null;
    searchOpen = false;
    selected.clear();
    kick();
  }

  // ── Auswahl ────────────────────────────────────────────────────
  function toggle(index, event) {
    const id = items[index][0];
    const from = lastToggled === null ? undefined : indexById.get(lastToggled);
    if (event?.shiftKey && from !== undefined) {
      const [a, b] = from < index ? [from, index] : [index, from];
      for (let i = a; i <= b; i++) selected.add(items[i][0]);
    } else if (selected.has(id)) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
    lastToggled = id;
  }
  function toggleDay(first, last, on) {
    for (let i = first; i <= last; i++) {
      if (on) selected.add(items[i][0]);
      else selected.delete(items[i][0]);
    }
  }

  // ── Aktionen ───────────────────────────────────────────────────
  async function runBatch(body, undo = null) {
    try {
      const task = await api.batch(body);
      pending.set(task.id, { undo });
      tasks = [...tasks, task];
      selected.clear();
      kick();
    } catch (e) {
      notifyError(e);
    }
  }

  const neighbour = (id) => {
    const i = viewerItems.findIndex((item) => item[0] === id);
    return viewerItems[i + 1]?.[0] ?? viewerItems[i - 1]?.[0] ?? null;
  };

  function trackTask(task) {
    pending.set(task.id, {});
    tasks = [...tasks, task];
    kick();
  }

  function openViewer(ids, id) {
    viewerIds = ids;
    openId = id;
  }
  function openList(list, id) {
    viewerList = list;
    openId = id;
  }
  function closeViewer() {
    openId = null;
    viewerIds = viewerList = null;
  }

  async function deleteOne(id) {
    const next = neighbour(id);
    try {
      await api.remove(id);
      openId = next;
      notify('In den Papierkorb verschoben', {
        actionLabel: 'Rückgängig',
        action: () => api.restore(id).then(kick, notifyError),
      });
      kick();
    } catch (e) {
      notifyError(e);
    }
  }

  async function restoreOne(id) {
    const next = neighbour(id);
    try {
      await api.restore(id);
      openId = next;
      notify('Wiederhergestellt');
      kick();
    } catch (e) {
      notifyError(e);
    }
  }

  function confirmPurge(ids) {
    dialog = {
      type: 'confirm',
      title: 'Endgültig löschen?',
      text: `${ids.length === 1 ? 'Die Datei wird' : `${ids.length} Dateien werden`} unwiderruflich vom Datenträger gelöscht.`,
      confirmLabel: 'Endgültig löschen',
      onconfirm: () => {
        if (openId !== null && ids.includes(openId)) openId = neighbour(openId);
        runBatch({ ids, action: 'purge' });
      },
    };
  }

  function confirmEmptyTrash() {
    dialog = {
      type: 'confirm',
      title: 'Papierkorb leeren?',
      text: `Alle ${formatNumber(info.counts.trash)} Dateien im Papierkorb werden unwiderruflich gelöscht.`,
      confirmLabel: 'Papierkorb leeren',
      onconfirm: async () => {
        try {
          const task = await api.emptyTrash();
          pending.set(task.id, {});
          kick();
        } catch (e) {
          notifyError(e);
        }
      },
    };
  }

  function confirmConvert(ids, after = () => {}) {
    dialog = {
      type: 'confirm',
      title: 'Umwandeln?',
      text:
        `HEIC-Fotos werden zu JPEG, Videos, die der Browser nicht abspielen kann, zu MP4 (H.264). ` +
        `Andere Dateien bleiben, wie sie sind. Die neue Datei ersetzt das Original; das Original kommt für ` +
        `${info?.trash_days ?? 30} Tage in den Papierkorb. Ein Video braucht auf dem Pi etwa so lange, wie es dauert.`,
      confirmLabel: `${ids.length === 1 ? '1 Datei' : `${formatNumber(ids.length)} Dateien`} umwandeln`,
      onconfirm: () => {
        runBatch({ ids, action: 'convert' });
        after();
      },
    };
  }

  async function dismissConvertErrors() {
    info.converting.failed = 0; // sofort weg, nicht erst beim nächsten Abfragen
    try {
      await api.dismissConvertErrors();
    } catch (e) {
      notifyError(e);
    }
    kick();
  }

  function deleteSelected() {
    const ids = [...selected];
    runBatch({ ids, action: 'delete' }, () => runBatch({ ids, action: 'restore' }));
  }

  function selectionDate() {
    const first = items[indexById.get([...selected][0])];
    return first ? new Date(first[1] * 1000).toISOString().slice(0, 19) : '';
  }

  function keydown(e) {
    if (!canEdit || openIndex >= 0 || dialog || showImport || showAccess || showPassword || view === 'map' || view === 'people' || view === 'duplicates' || view === 'storage' || e.target.closest?.('input, textarea')) return;
    if (e.key === 'Escape' && selected.size) selected.clear();
    else if (e.key === 'Delete' && selected.size) (trash ? isAdmin && confirmPurge([...selected]) : deleteSelected());
    else if (e.key === 'a' && (e.ctrlKey || e.metaKey) && items.length) items.forEach((item) => selected.add(item[0]));
    else return;
    e.preventDefault();
  }

  function pickFiles(e) {
    uploader.add([...e.currentTarget.files]);
    e.currentTarget.value = '';
  }
</script>

<svelte:window onkeydown={keydown} />

{#if session && !session.authenticated}
  <Login cookieBlocked={session.cookie_blocked} onlogin={signedIn} />
{:else if session}
<div class="app">
  {#if selected.size}
    <header class="topbar selection">
      <button class="icon" onclick={() => selected.clear()} title="Auswahl aufheben (Esc)"><Icon name="close" /></button>
      <strong class="title">{formatNumber(selected.size)} ausgewählt</strong>
      <span class="grow"></span>
      {#if trash}
        <button onclick={() => runBatch({ ids: [...selected], action: 'restore' })} title="Wiederherstellen">
          <Icon name="restore" size={20} /><span class="label">Wiederherstellen</span>
        </button>
        {#if isAdmin}
          <button class="danger" onclick={() => confirmPurge([...selected])} title="Endgültig löschen">
            <Icon name="deleteForever" size={20} /><span class="label">Endgültig löschen</span>
          </button>
        {/if}
      {:else}
        <button class="icon" onclick={() => (dialog = { type: 'labels', kind: 'persons' })} title="Personen ändern"><Icon name="person" /></button>
        <button class="icon" onclick={() => (dialog = { type: 'labels', kind: 'tags' })} title="Schlagworte ändern"><Icon name="tag" /></button>
        <button class="icon" onclick={() => (dialog = { type: 'date' })} title="Datum setzen"><Icon name="calendar" /></button>
        <button class="icon" onclick={() => (dialog = { type: 'location' })} title="Aufnahmeort setzen"><Icon name="marker" /></button>
        <button class="icon" onclick={() => runBatch({ ids: [...selected], action: 'rotate', degrees: 270 })} title="Nach links drehen"><Icon name="rotate" /></button>
        <button class="icon" onclick={() => runBatch({ ids: [...selected], action: 'rotate', degrees: 90 })} title="Nach rechts drehen"><Icon name="rotate" flip /></button>
        {#if isAdmin}
          <button class="icon" onclick={() => confirmConvert([...selected])} title="Umwandeln: HEIC → JPEG, nicht abspielbare Videos → MP4"><Icon name="convert" /></button>
        {/if}
        <button class="icon" onclick={deleteSelected} title="In den Papierkorb (Entf)"><Icon name="delete" /></button>
      {/if}
    </header>
  {:else if trash}
    <header class="topbar">
      <button class="icon" onclick={() => setView('photos')} title="Zurück zu den Fotos"><Icon name="back" /></button>
      <div class="title-block">
        <strong class="title">Papierkorb</strong>
        {#if info}<span class="sub">Dateien werden nach {info.trash_days} Tagen endgültig gelöscht</span>{/if}
      </div>
      <span class="grow"></span>
      {#if info?.counts.trash && isAdmin}
        <button class="danger" onclick={confirmEmptyTrash}><Icon name="deleteForever" size={20} /><span class="label">Papierkorb leeren</span></button>
      {/if}
    </header>
  {:else if view === 'duplicates'}
    <header class="topbar">
      <button class="icon" onclick={() => setView('photos')} title="Zurück zu den Fotos"><Icon name="back" /></button>
      <div class="title-block">
        <strong class="title">Doppelte Fotos</strong>
        <span class="sub">Gelöschte Fotos landen im Papierkorb</span>
      </div>
      <span class="grow"></span>
    </header>
  {:else if view === 'storage'}
    <header class="topbar">
      <button class="icon" onclick={() => setView('photos')} title="Zurück zu den Fotos"><Icon name="back" /></button>
      <div class="title-block">
        <strong class="title">Speicherplatz</strong>
        <span class="sub">Die größten Dateien zuerst · Gelöschtes landet im Papierkorb</span>
      </div>
      <span class="grow"></span>
    </header>
  {:else}
    <header class="topbar">
      <div class="brand" title={info ? `${formatNumber(info.counts.images)} Fotos · ${formatNumber(info.counts.videos)} Videos · ${formatBytes(info.counts.bytes)}` : ''}>
        <Icon name="images" size={26} />
        <h1>Fotoarchiv</h1>
      </div>
      <nav class="views">
        <button class:active={view === 'photos'} onclick={() => setView('photos')} title="Fotos"><Icon name="images" size={20} /><span class="label">Fotos</span></button>
        <button class:active={view === 'map'} onclick={() => setView('map')} title="Karte"><Icon name="map" size={20} /><span class="label">Karte</span></button>
        <button class:active={view === 'people'} onclick={() => setView('people')} title="Personen"><Icon name="person" size={20} /><span class="label">Personen</span></button>
      </nav>
      <div class="search-inline"><SearchBar {labels} {filters} onchange={setFilters} /></div>
      <span class="grow"></span>
      <div class="actions">
        {#if info?.importing}<span class="busy" title="Import läuft"></span>{/if}
        <button class="icon search-toggle" class:on={searchOpen} onclick={() => (searchOpen = !searchOpen)} title="Suchen"><Icon name="search" /></button>
        {#if canUpload}
          <button onclick={() => fileInput.click()} title="Dateien hochladen">
            <Icon name="upload" size={20} /><span class="label">Hochladen</span>
          </button>
        {/if}
        {#if isAdmin}
          <button onclick={() => (showImport = true)} title="Aus Ordner importieren">
            <Icon name="import" size={20} /><span class="label">Importieren</span>
          </button>
        {/if}
        {#if canEdit}
          <button class="icon" onclick={() => setView('duplicates')} title="Doppelte Fotos"><Icon name="duplicate" /></button>
          <button class="icon" onclick={() => setView('storage')} title="Speicherplatz – Dateien nach Größe"><Icon name="storage" /></button>
          <button class="icon trash" onclick={() => setView('trash')} title="Papierkorb">
            <Icon name="delete" />
            {#if info?.counts.trash}<span class="badge">{info.counts.trash > 99 ? '99+' : info.counts.trash}</span>{/if}
          </button>
        {/if}
        {#if isAdmin && !session.public}
          <button class="icon" onclick={() => (showAccess = true)} title="Zugang übers Internet"><Icon name="shield" /></button>
        {/if}
        {#if session.public && installPrompt}
          <button onclick={installApp} title="Als App auf diesem Gerät installieren">
            <Icon name="download" size={20} /><span class="label">App installieren</span>
          </button>
        {/if}
        {#if session.public}
          <button class="icon" onclick={() => (showPassword = true)} title="Passwort ändern"><Icon name="lock" /></button>
          <button class="icon" onclick={logout} title="Abmelden ({session.user?.display_name || session.user?.username})"><Icon name="logout" /></button>
        {/if}
        <input bind:this={fileInput} type="file" multiple accept="image/*,video/*,.heic,.heif" hidden onchange={pickFiles} />
      </div>
    </header>
    {#if searchOpen}
      <div class="search-row"><SearchBar {labels} {filters} onchange={setFilters} /></div>
    {/if}
  {/if}

  {#if failure}
    <div class="banner error"><Icon name="alert" size={18} /> Server nicht erreichbar: {failure}</div>
  {/if}
  {#if info?.converting?.pending}
    <div class="banner"><span class="busy"></span> {`Umwandeln läuft: noch ${formatNumber(info.converting.pending)}${info.converting.current ? ` · gerade ${info.converting.current}` : ''}`}</div>
  {:else if info?.converting?.failed && isAdmin}
    <div class="banner error">
      <Icon name="alert" size={18} />
      <span class="banner-text">
        {formatNumber(info.converting.failed)} {info.converting.failed === 1 ? 'Datei ließ' : 'Dateien ließen'} sich nicht umwandeln. Die Originale sind unverändert.
        {#each info.converting.errors ?? [] as error (error.id)}
          <br /><span class="reason">{error.name}: {error.reason}</span>
        {/each}
      </span>
      <button class="icon small" onclick={dismissConvertErrors} title="Hinweis ausblenden"><Icon name="close" size={16} /></button>
    </div>
  {/if}
  {#if iosHint && session?.authenticated}
    <div class="banner">
      <Icon name="info" size={18} />
      <span class="banner-text">Als App aufs iPhone: unten auf <strong>Teilen</strong> tippen, dann <strong>„Zum Home-Bildschirm“</strong>.</span>
      <button class="icon small" onclick={hideIosHint} title="Hinweis ausblenden"><Icon name="close" size={16} /></button>
    </div>
  {/if}
  {#if missingTools.length}
    <div class="banner"><Icon name="alert" size={18} /> Fehlende Programme im Add-on: {missingTools.join(', ')}</div>
  {/if}
  {#if filtered && view !== 'people' && view !== 'duplicates' && view !== 'storage'}
    <div class="resultbar">
      <span>{formatNumber(items.length)} Treffer</span>
      <button class="link" onclick={() => setFilters(NO_FILTERS)}>Filter zurücksetzen</button>
    </div>
  {/if}

  {#if view === 'people'}
    <PeopleView
      {canEdit}
      revision={info?.revision}
      onchanged={kick}
      ontask={trackTask}
      onshowphotos={(person) => {
        setView('photos');
        setFilters({ ...NO_FILTERS, persons: [{ id: person.id, name: person.name }] });
      }}
    />
  {:else if view === 'duplicates'}
    <DuplicatesView revision={info?.revision} onopen={openList} ontask={trackTask} onchanged={kick} />
  {:else if view === 'storage'}
    <StorageView revision={info?.revision} {canEdit} onopen={openList} onbatch={runBatch} onconvert={isAdmin ? confirmConvert : null} />
  {:else if view === 'map'}
    <MapView {filters} {canEdit} revision={info?.revision} onopen={openViewer} onbatch={runBatch} />
  {:else if items.length}
    {#key listKey}
      <Gallery
        {items}
        {selected}
        selectable={canEdit}
        {zoom}
        onzoom={changeZoom}
        onopen={(i) => (openId = items[i][0])}
        ontoggle={toggle}
        ontoggleday={toggleDay}
      />
    {/key}
  {:else if loaded && info}
    <div class="empty">
      {#if trash}
        <Icon name="delete" size={64} />
        <h2>Der Papierkorb ist leer</h2>
      {:else if filtered}
        <Icon name="search" size={64} />
        <h2>Keine Treffer</h2>
        <p>Für diese Suche gibt es keine Fotos oder Videos.</p>
      {:else}
        <Icon name="images" size={64} />
        <h2>Noch keine Fotos</h2>
        {#if isAdmin}
          <p>Dateien einfach hierher ziehen, über <strong>Hochladen</strong> auswählen oder in den Import-Ordner legen:</p>
          <code>{info.import_dir}</code>
          <button class="primary" onclick={() => (showImport = true)}><Icon name="import" size={20} /> Import öffnen</button>
        {/if}
      {/if}
    </div>
  {/if}
</div>

{#if openIndex >= 0}
  <Viewer
    items={viewerItems}
    index={openIndex}
    {canEdit}
    canPurge={isAdmin}
    {trash}
    {labels}
    onclose={closeViewer}
    onnavigate={(i) => (openId = viewerItems[i][0])}
    onchanged={kick}
    ondelete={deleteOne}
    onrestore={restoreOne}
    onpurge={(id) => confirmPurge([id])}
  />
{/if}

{#if showImport && info}
  <ImportPanel
    {info}
    onclose={() => (showImport = false)}
    onchanged={kick}
    ontask={trackTask}
  />
{/if}

{#if dialog?.type === 'labels'}
  <LabelDialog
    kind={dialog.kind}
    count={selected.size}
    suggestions={labels[dialog.kind].map((l) => l.name)}
    oncancel={() => (dialog = null)}
    onsave={(add, remove) => {
      runBatch({ ids: [...selected], action: dialog.kind, add, remove });
      dialog = null;
    }}
  />
{:else if dialog?.type === 'date'}
  <DateDialog
    value={selectionDate()}
    count={selected.size}
    oncancel={() => (dialog = null)}
    onsave={(value) => {
      runBatch({ ids: [...selected], action: 'date', taken_at: value });
      dialog = null;
    }}
  />
{:else if dialog?.type === 'location'}
  <LocationDialog
    count={selected.size}
    oncancel={() => (dialog = null)}
    onsave={(location) => {
      // Kein Rückgängig: Die Auswahl kann vorher verschiedene Orte gehabt haben,
      // ein pauschales Zurücksetzen auf "kein Ort" würde die alten Angaben verlieren.
      runBatch({ ids: [...selected], action: 'location', location });
      dialog = null;
    }}
  />
{:else if dialog?.type === 'confirm'}
  <Confirm
    title={dialog.title}
    text={dialog.text}
    confirmLabel={dialog.confirmLabel}
    danger
    oncancel={() => (dialog = null)}
    onconfirm={() => {
      const action = dialog.onconfirm;
      dialog = null;
      action();
    }}
  />
{/if}

{#if showAccess}
  <AccessPanel onclose={() => (showAccess = false)} />
{/if}

{#if showPassword}
  <PasswordDialog onclose={() => (showPassword = false)} />
{/if}

<Uploader bind:this={uploader} enabled={canUpload} onchanged={kick} />
{/if}
<Notices {tasks} />

<style>
  .app {
    height: 100vh;
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }
  .topbar {
    flex: none;
    display: flex;
    align-items: center;
    gap: 12px;
    height: 60px;
    padding: 0 12px 0 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .topbar.selection {
    padding-left: 8px;
    background: color-mix(in srgb, var(--accent) 14%, var(--surface));
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--accent);
  }
  h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
  }
  .views {
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: 20px;
    background: var(--chip);
  }
  .views button {
    min-height: 34px;
    padding: 0 12px;
    border: 0;
    border-radius: 17px;
    background: transparent;
    color: var(--muted);
  }
  .views button.active {
    background: var(--surface);
    color: var(--accent);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.15);
  }
  .search-inline {
    flex: 1;
    max-width: 680px;
    min-width: 0;
    margin-left: 12px;
  }
  .search-row {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .search-toggle {
    display: none;
  }
  .grow {
    flex: 1;
  }
  .title {
    font-size: 1.1rem;
    font-weight: 500;
    white-space: nowrap;
  }
  .title-block {
    display: grid;
    min-width: 0;
  }
  .sub {
    font-size: 0.8rem;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .on {
    color: var(--accent);
  }
  .trash {
    position: relative;
  }
  .badge {
    position: absolute;
    top: 2px;
    right: 0;
    min-width: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--danger);
    color: #fff;
    font-size: 10px;
    line-height: 16px;
    text-align: center;
  }
  .busy {
    width: 18px;
    height: 18px;
    border: 2px solid var(--accent);
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--warning-bg);
    color: var(--text);
    font-size: 0.9rem;
  }
  .banner.error {
    background: var(--danger-bg);
  }
  .banner-text {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .banner .reason {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .resultbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 16px;
    font-size: 0.9rem;
    color: var(--muted);
  }
  button.link {
    min-height: 28px;
    padding: 0 6px;
    border: 0;
    background: transparent;
    color: var(--accent);
  }
  .empty {
    flex: 1;
    display: grid;
    align-content: center;
    justify-items: center;
    gap: 12px;
    padding: 24px;
    text-align: center;
    color: var(--muted);
  }
  .empty h2 {
    margin: 0;
    color: var(--text);
    font-weight: 500;
  }
  .empty p {
    margin: 0;
    max-width: 420px;
    line-height: 1.5;
  }
  .empty code {
    padding: 4px 8px;
    border-radius: 4px;
    background: var(--chip);
    color: var(--text);
  }
  @media (max-width: 899px) {
    .search-inline {
      display: none;
    }
    .search-toggle {
      display: inline-flex;
    }
    .label {
      display: none;
    }
  }
  @media (max-width: 1099px) {
    h1 {
      display: none;
    }
  }
  @media (max-width: 479px) {
    .views button {
      padding: 0 8px;
    }
    .topbar {
      gap: 4px;
      padding: 0 6px 0 10px;
    }
    .actions {
      gap: 4px;
    }
    .selection {
      gap: 0;
    }
    .selection .title {
      font-size: 1rem;
    }
    .selection button.icon {
      width: 36px;
    }
  }
</style>
