<script module>
  // Kartenausschnitt und Zeitraum beim Wechsel der Ansicht behalten
  const saved = { center: null, zoom: null, period: null };
</script>

<script>
  import { onMount, untrack } from 'svelte';
  import Supercluster from 'supercluster';
  import { api, thumbUrl } from '../lib/api.js';
  import { formatNumber } from '../lib/format.js';
  import { createMap, L } from '../lib/map.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import LocationDialog from './LocationDialog.svelte';
  import MapTimeline from './MapTimeline.svelte';
  import PlaceSearch from './PlaceSearch.svelte';
  import UnlocatedPanel from './UnlocatedPanel.svelte';

  // onopen(ids, id): Einzelansicht mit dieser Liste; onbatch(body, undo): Mehrfachaktion starten
  let { filters, revision, canEdit = true, onopen, onbatch } = $props();

  const MAX_ZOOM = 19; // wie die OSM-Kacheln; bis hierhin wird gebündelt, sonst stapeln sich die Bilder
  const MARKER = 64; // px, größtes Vorschaubild auf der Karte
  const PANEL_KEY = 'fotoarchiv.map.panel';

  let container = $state();
  let map;
  let layer;
  let points = $state.raw([]); // [id, ts, w, h, video, rev, lat, lon]
  let unlocated = $state.raw([]);
  let dropActive = $state(false);
  let menu = $state(null); // Rechtsklick-Menü: { x, y, ids, lat, lon, feature, item }
  let editing = $state(null); // Ortsdialog aus dem Menü: { ids, lat, lon, mode: 'shift' | 'place' }
  let collapsed = $state(readCollapsed());

  function readCollapsed() {
    try {
      return localStorage.getItem(PANEL_KEY) === '1';
    } catch {
      return false;
    }
  }
  function togglePanel() {
    collapsed = !collapsed;
    try {
      localStorage.setItem(PANEL_KEY, collapsed ? '1' : '0');
    } catch {
      /* egal */
    }
  }

  // ── Daten ──────────────────────────────────────────────────────
  let sequence = 0;
  async function load(currentFilters) {
    const seq = ++sequence;
    try {
      const [geo, open] = await Promise.all([
        api.geo(currentFilters),
        api.index(currentFilters, false, { located: false, editable: true }),
      ]);
      if (seq !== sequence) return;
      points = geo.items;
      unlocated = open.items;
    } catch (e) {
      notifyError(e);
    }
  }

  $effect(() => {
    revision;
    const current = filters;
    untrack(() => load(current));
  });

  // ── Zeitraum ───────────────────────────────────────────────────
  const THIS_YEAR = new Date().getFullYear();
  const yearOf = (ts) => new Date(ts * 1000).getUTCFullYear(); // taken_ts: Ortszeit als UTC-Sekunden
  const years = $derived.by(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const p of points) {
      const year = yearOf(p[1]);
      if (year < min) min = year;
      if (year > max) max = year;
    }
    return Number.isFinite(min) ? { min, max: Math.max(max, THIS_YEAR), newest: max } : { min: THIS_YEAR, max: THIS_YEAR, newest: THIS_YEAR };
  });
  let period = $state(saved.period ?? { on: false, start: null, span: 1 });

  function changePeriod(next) {
    // Beim Einschalten mit dem neuesten Jahr beginnen, in dem es Fotos gibt
    if (next.on && next.start === null) next = { ...next, start: Math.max(years.min, years.newest - next.span + 1) };
    period = next;
    saved.period = next;
  }

  // Die Karte zeigt nur, was in den Zeitraum fällt; aus dem Fenster "Ohne Ort" geht das nicht
  const shown = $derived.by(() => {
    if (!period.on || period.start === null) return points;
    const from = Date.UTC(period.start, 0, 1) / 1000;
    const to = Date.UTC(period.start + period.span, 0, 1) / 1000;
    return points.filter((p) => p[1] >= from && p[1] < to);
  });

  const clusters = $derived.by(() => {
    const index = new Supercluster({
      // extent 256 = Leaflets Kachelgröße, damit radius in Bildschirmpixeln zählt. Etwas mehr als ein
      // Vorschaubild samt Rahmen, sonst überlappen sich benachbarte Bilder.
      extent: 256,
      radius: MARKER + 8,
      maxZoom: MAX_ZOOM,
      // Jede Gruppe merkt sich ihr neuestes Foto als Titelbild
      map: (p) => ({ best: p.index, ts: p.ts }),
      reduce: (acc, p) => {
        if (p.ts > acc.ts) {
          acc.ts = p.ts;
          acc.best = p.best;
        }
      },
    });
    index.load(
      shown.map((item, i) => ({
        type: 'Feature',
        properties: { index: i, ts: item[1] },
        geometry: { type: 'Point', coordinates: [item[7], item[6]] },
      })),
    );
    return index;
  });

  // ── Karte ──────────────────────────────────────────────────────
  onMount(() => {
    map = createMap(container);
    layer = L.layerGroup().addTo(map);
    if (saved.center) map.setView(saved.center, saved.zoom);
    else map.setView([30, 10], 2);
    map.on('contextmenu', () => (menu = null)); // Rechtsklick auf die Karte selbst: nichts
    map.on('movestart', () => (menu = null));
    map.on('moveend', () => {
      saved.center = map.getCenter();
      saved.zoom = map.getZoom();
      render();
    });
    // Größenänderungen (Fenster, eingeklapptes Seitenfenster) an Leaflet melden
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      map.remove();
    };
  });

  let fitted = saved.center !== null;
  $effect(() => {
    clusters;
    untrack(() => {
      if (!map) return;
      if (!fitted && points.length) {
        fitted = true;
        const bounds = L.latLngBounds(points.map((p) => [p[6], p[7]]));
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
      }
      render();
    });
  });

  function render() {
    if (!map || !layer) return;
    const b = map.getBounds();
    const bbox = b.getEast() - b.getWest() >= 360 ? [-180, -85, 180, 85] : [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    layer.clearLayers();
    for (const feature of clusters.getClusters(bbox, Math.min(Math.round(map.getZoom()), MAX_ZOOM))) {
      const [lon, lat] = feature.geometry.coordinates;
      const props = feature.properties;
      const count = props.cluster ? props.point_count : 1;
      const item = shown[props.cluster ? props.best : props.index];
      const size = count > 1 ? MARKER : 52;
      const icon = L.divIcon({
        className: 'photo-marker',
        html: `<img src="${thumbUrl(item)}" alt="" loading="lazy">${count > 1 ? `<span>${count > 9999 ? '9999+' : count}</span>` : ''}`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      const marker = L.marker([lat, lon], { icon, keyboard: false });
      marker.on('click', () => (props.cluster ? openCluster(feature, lat, lon) : openInView(item[0])));
      marker.on('contextmenu', (e) => {
        L.DomEvent.stop(e.originalEvent);
        const rect = container.getBoundingClientRect();
        menu = { x: e.originalEvent.clientX - rect.left, y: e.originalEvent.clientY - rect.top, ids: groupIds(feature, item), lat, lon, feature, item };
      });
      marker.addTo(layer);
    }
  }

  function groupIds(feature, item) {
    if (!feature.properties.cluster) return [item[0]];
    return clusters.getLeaves(feature.properties.cluster_id, Infinity).map((l) => shown[l.properties.index][0]);
  }

  // ── Verschieben (Rechtsklick-Menü) ─────────────────────────────
  // Eine Gruppe wandert als Ganzes: alle Fotos darin um denselben Versatz, ihre Anordnung bleibt
  function shiftGroup(ids, dlat, dlon) {
    dlat = Number(dlat.toFixed(6));
    dlon = Number(dlon.toFixed(6));
    if (!dlat && !dlon) return;
    const moving = new Set(ids);
    // Sofort anzeigen, der Server schreibt im Hintergrund in die Dateien
    points = points.map((p) => (moving.has(p[0]) ? [...p.slice(0, 6), Math.max(-90, Math.min(90, p[6] + dlat)), ((p[7] + dlon + 540) % 360) - 180] : p));
    onbatch({ ids, action: 'shift', dlat, dlon }, () => shiftGroup(ids, -dlat, -dlon));
  }

  function placeGroup(ids, location) {
    // Alle auf genau diesen Punkt (Ortsdialog); Rückgängig stellt jeden alten Ort einzeln wieder her
    const moving = new Set(ids);
    const before = points.filter((p) => moving.has(p[0])).map((p) => [p[0], p[6], p[7]]);
    points = points.map((p) => (moving.has(p[0]) ? [...p.slice(0, 6), location.lat, location.lon] : p));
    onbatch({ ids, action: 'location', location }, () => restore(before));
  }

  function removeLocation(ids) {
    const moving = new Set(ids);
    const before = points.filter((p) => moving.has(p[0])).map((p) => [p[0], p[6], p[7]]);
    points = points.filter((p) => !moving.has(p[0]));
    onbatch({ ids, action: 'location', location: null }, () => restore(before));
  }

  async function restore(before) {
    try {
      await Promise.all(before.map(([id, lat, lon]) => api.update(id, { location: { lat, lon } })));
    } catch (e) {
      notifyError(e);
    }
    load(filters);
  }

  function showGroup(m) {
    if (m.feature.properties.cluster) {
      const leaves = clusters.getLeaves(m.feature.properties.cluster_id, Infinity).map((l) => shown[l.properties.index]);
      leaves.sort((a, b) => b[1] - a[1] || b[0] - a[0]);
      onopen(leaves.map((i) => i[0]), leaves[0][0]);
    } else {
      openInView(m.item[0]);
    }
  }

  function openCluster(feature, lat, lon) {
    const zoom = clusters.getClusterExpansionZoom(feature.properties.cluster_id);
    if (zoom <= MAX_ZOOM && zoom > map.getZoom()) {
      map.flyTo([lat, lon], zoom, { duration: 0.5 });
      return;
    }
    // Alle am selben Ort: direkt ansehen
    const leaves = clusters.getLeaves(feature.properties.cluster_id, Infinity).map((l) => shown[l.properties.index]);
    leaves.sort((a, b) => b[1] - a[1] || b[0] - a[0]);
    onopen(leaves.map((i) => i[0]), leaves[0][0]);
  }

  function openInView(id) {
    const bounds = map.getBounds();
    const inView = shown.filter((p) => bounds.contains([p[6], p[7]]));
    onopen(inView.map((p) => p[0]), id);
  }

  // ── Ablegen aus dem Fenster "Ohne Ort" ─────────────────────────
  function overMap(x, y) {
    const rect = container?.getBoundingClientRect();
    const inside = !!rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    dropActive = inside;
    return inside;
  }

  function drop(ids, x, y) {
    dropActive = false;
    const rect = container.getBoundingClientRect();
    const latlng = map.containerPointToLatLng(L.point(x - rect.left, y - rect.top)).wrap();
    const location = { lat: Number(latlng.lat.toFixed(6)), lon: Number(latlng.lng.toFixed(6)) };
    // Sofort anzeigen, der Server schreibt im Hintergrund in die Dateien
    const moving = new Set(ids);
    points = [...points, ...unlocated.filter((i) => moving.has(i[0])).map((i) => [...i, location.lat, location.lon])];
    unlocated = unlocated.filter((i) => !moving.has(i[0]));
    onbatch({ ids, action: 'location', location }, () => onbatch({ ids, action: 'location', location: null }));
  }

  function goTo(place) {
    if (place.bounds) map.flyToBounds(place.bounds, { maxZoom: 15, duration: 0.8 });
    else map.flyTo([place.lat, place.lon], 13, { duration: 0.8 });
  }
</script>

<svelte:window onclick={() => (menu = null)} onkeydown={(e) => e.key === 'Escape' && (menu = null)} />

{#if editing}
  <LocationDialog
    lat={editing.lat}
    lon={editing.lon}
    count={editing.mode === 'place' ? editing.ids.length : 1}
    hint={editing.mode === 'shift' ? `Die Stecknadel steht in der Mitte der Gruppe (${formatNumber(editing.ids.length)} Fotos). Verschiebe sie an die richtige Stelle – alle Fotos wandern mit, ihre Anordnung bleibt.` : ''}
    onsave={(location) => {
      if (editing.mode === 'shift') shiftGroup(editing.ids, location.lat - editing.lat, location.lon - editing.lon);
      else placeGroup(editing.ids, location);
      editing = null;
    }}
    oncancel={() => (editing = null)}
  />
{/if}

<div class="map-view">
  <div class="map-wrap" class:drop={dropActive}>
    <div class="map" bind:this={container}></div>
    <div class="overlay"><PlaceSearch onselect={goTo} /></div>
    <div class="period">
      <MapTimeline {period} minYear={years.min} maxYear={years.max} count={shown.length} onchange={changePeriod} />
    </div>
    {#if dropActive}<div class="drop-hint">Hier loslassen, um den Ort zu setzen</div>{/if}
    {#if menu}
      <div class="menu" style:left="{menu.x}px" style:top="{menu.y}px" role="menu">
        <div class="menu-title">{menu.ids.length === 1 ? '1 Foto' : `${formatNumber(menu.ids.length)} Fotos`}</div>
        {#if canEdit}
          {#if menu.ids.length > 1}
            <button role="menuitem" onclick={() => (editing = { ...menu, mode: 'shift' })}>Gruppe verschieben …</button>
            <button role="menuitem" onclick={() => (editing = { ...menu, mode: 'place' })}>Alle auf einen Punkt …</button>
          {:else}
            <button role="menuitem" onclick={() => (editing = { ...menu, mode: 'place' })}>Ort ändern …</button>
          {/if}
          <button role="menuitem" onclick={() => removeLocation(menu.ids)}>Ort entfernen</button>
        {/if}
        <button role="menuitem" onclick={() => showGroup(menu)}>Ansehen</button>
      </div>
    {/if}
  </div>
  {#if canEdit}
  <UnlocatedPanel
    items={unlocated}
    {collapsed}
    ontoggle={togglePanel}
    ondragmove={overMap}
    ondrop={drop}
    {onopen}
  />
  {/if}
</div>

<style>
  .map-view {
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .map-wrap {
    position: relative;
    flex: 1;
    min-width: 0;
    isolation: isolate; /* Leaflets z-Indizes (bis 1000) bleiben innerhalb der Karte */
  }
  .map {
    position: absolute;
    inset: 0;
    z-index: 0;
  }
  .map-wrap.drop::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 500;
    border: 4px dashed var(--accent);
    pointer-events: none;
  }
  .overlay {
    position: absolute;
    top: 12px;
    left: 56px;
    right: 12px;
    z-index: 600;
    pointer-events: none;
  }
  .overlay :global(form) {
    pointer-events: auto;
  }
  .period {
    position: absolute;
    left: 50%;
    bottom: 28px; /* über der Quellenangabe von OpenStreetMap */
    z-index: 600;
    transform: translateX(-50%);
    max-width: calc(100% - 24px);
    pointer-events: none;
  }
  .menu {
    position: absolute;
    z-index: 700;
    min-width: 180px;
    padding: 4px 0;
    border-radius: 10px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.3);
    pointer-events: auto;
  }
  .menu-title {
    padding: 6px 14px 4px;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .menu button {
    display: block;
    width: 100%;
    min-height: 40px;
    padding: 0 14px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: inherit;
    font-weight: 400;
    text-align: left;
  }
  .menu button:hover {
    background: var(--chip);
  }
  .drop-hint {
    position: absolute;
    left: 50%;
    bottom: 24px;
    z-index: 600;
    transform: translateX(-50%);
    padding: 8px 16px;
    border-radius: 18px;
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 500;
    pointer-events: none;
    white-space: nowrap;
  }
  .map-view :global(.photo-marker) {
    border: 3px solid #fff;
    border-radius: 8px;
    background: var(--placeholder);
    box-shadow: 0 2px 8px rgb(0 0 0 / 0.45);
    cursor: pointer;
  }
  .map-view :global(.photo-marker:hover) {
    z-index: 1000 !important;
    transform-origin: center;
    border-color: var(--accent);
  }
  .map-view :global(.photo-marker img) {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 5px;
    display: block;
  }
  .map-view :global(.photo-marker span) {
    position: absolute;
    top: -10px;
    right: -12px;
    min-width: 20px;
    padding: 0 6px;
    border-radius: 11px;
    background: var(--accent);
    color: var(--on-accent);
    font: 600 12px/22px Roboto, 'Segoe UI', sans-serif;
    text-align: center;
  }
  @media (max-width: 719px) {
    .map-view {
      flex-direction: column;
    }
    .overlay {
      left: 52px;
    }
  }
</style>
