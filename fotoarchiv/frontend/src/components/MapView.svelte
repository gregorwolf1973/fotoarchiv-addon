<script module>
  // Kartenausschnitt beim Wechsel der Ansicht behalten
  const saved = { center: null, zoom: null };
</script>

<script>
  import { onMount, untrack } from 'svelte';
  import Supercluster from 'supercluster';
  import { api, thumbUrl } from '../lib/api.js';
  import { createMap, L } from '../lib/map.js';
  import { notifyError } from '../lib/notices.svelte.js';
  import PlaceSearch from './PlaceSearch.svelte';
  import UnlocatedPanel from './UnlocatedPanel.svelte';

  // onopen(ids, id): Einzelansicht mit dieser Liste; onbatch(body, undo): Mehrfachaktion starten
  let { filters, revision, canEdit = true, onopen, onbatch } = $props();

  const MAX_ZOOM = 17;
  const PANEL_KEY = 'fotoarchiv.map.panel';

  let container = $state();
  let map;
  let layer;
  let points = $state.raw([]); // [id, ts, w, h, video, rev, lat, lon]
  let unlocated = $state.raw([]);
  let dropActive = $state(false);
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

  const clusters = $derived.by(() => {
    const index = new Supercluster({
      radius: 64,
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
      points.map((item, i) => ({
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
    for (const feature of clusters.getClusters(bbox, Math.round(map.getZoom()))) {
      const [lon, lat] = feature.geometry.coordinates;
      const props = feature.properties;
      const count = props.cluster ? props.point_count : 1;
      const item = points[props.cluster ? props.best : props.index];
      const size = count > 1 ? 64 : 52;
      const icon = L.divIcon({
        className: 'photo-marker',
        html: `<img src="${thumbUrl(item)}" alt="" loading="lazy">${count > 1 ? `<span>${count > 9999 ? '9999+' : count}</span>` : ''}`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      L.marker([lat, lon], { icon, keyboard: false })
        .on('click', () => (props.cluster ? openCluster(feature, lat, lon) : openInView(item[0])))
        .addTo(layer);
    }
  }

  function openCluster(feature, lat, lon) {
    const zoom = clusters.getClusterExpansionZoom(feature.properties.cluster_id);
    if (zoom <= MAX_ZOOM && zoom > map.getZoom()) {
      map.flyTo([lat, lon], zoom, { duration: 0.5 });
      return;
    }
    // Alle am selben Ort: direkt ansehen
    const leaves = clusters.getLeaves(feature.properties.cluster_id, Infinity).map((l) => points[l.properties.index]);
    leaves.sort((a, b) => b[1] - a[1] || b[0] - a[0]);
    onopen(leaves.map((i) => i[0]), leaves[0][0]);
  }

  function openInView(id) {
    const bounds = map.getBounds();
    const inView = points.filter((p) => bounds.contains([p[6], p[7]]));
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

<div class="map-view">
  <div class="map-wrap" class:drop={dropActive}>
    <div class="map" bind:this={container}></div>
    <div class="overlay"><PlaceSearch onselect={goTo} /></div>
    {#if dropActive}<div class="drop-hint">Hier loslassen, um den Ort zu setzen</div>{/if}
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
