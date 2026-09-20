<script>
  import { onMount } from 'svelte';
  import { createMap, L, pinIcon } from '../lib/map.js';
  import Icon from './Icon.svelte';
  import PlaceSearch from './PlaceSearch.svelte';

  // lat/lon: bisheriger Ort oder null. onsave({ lat, lon })
  // count > 1: der Ort gilt für eine Mehrfachauswahl
  // saveLabel: in der Einzelansicht "Übernehmen", gespeichert wird dort erst mit dem Speichern-Button
  // hint: eigener Erklärtext (z. B. Gruppe verschieben) statt des Standards
  let { lat = null, lon = null, count = 1, saveLabel = 'Speichern', hint = '', onsave, oncancel } = $props();

  let container = $state();
  // svelte-ignore state_referenced_locally
  let position = $state(lat !== null ? { lat, lon } : null);
  let map;
  let marker;

  onMount(() => {
    map = createMap(container);
    if (position) map.setView([position.lat, position.lon], 13);
    else map.setView([48, 10], 4);
    map.on('click', (e) => place(e.latlng.wrap()));
    if (position) place(position);
    return () => map.remove();
  });

  function place(latlng) {
    position = { lat: Number(latlng.lat.toFixed(6)), lon: Number((latlng.lng ?? latlng.lon).toFixed(6)) };
    if (!marker) {
      marker = L.marker([position.lat, position.lon], { icon: pinIcon(), draggable: true }).addTo(map);
      marker.on('dragend', () => place(marker.getLatLng().wrap()));
    } else {
      marker.setLatLng([position.lat, position.lon]);
    }
  }

  function goTo(result) {
    if (result.bounds) map.fitBounds(result.bounds, { maxZoom: 15 });
    else map.setView([result.lat, result.lon], 14);
    place({ lat: result.lat, lng: result.lon });
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="location-title">
    <header>
      <h2 id="location-title">Aufnahmeort</h2>
      <button class="icon" onclick={oncancel} title="Schließen"><Icon name="close" /></button>
    </header>
    {#if hint}
      <p>{hint}</p>
    {:else if count > 1}
      <p>Alle <strong>{count}</strong> ausgewählten Dateien bekommen genau diesen Ort. In die Karte tippen oder die Stecknadel verschieben.</p>
    {:else}
      <p>In die Karte tippen oder die Stecknadel verschieben. Mit der Suche springst du schnell zu einem Ort.</p>
    {/if}
    <div class="map-box">
      <div class="map" bind:this={container}></div>
      <div class="search"><PlaceSearch onselect={goTo} /></div>
    </div>
    <div class="coords">
      {#if position}{position.lat.toFixed(5)}, {position.lon.toFixed(5)}{:else}Noch kein Ort gewählt{/if}
    </div>
    <footer>
      <button onclick={oncancel}>Abbrechen</button>
      <button class="primary" disabled={!position} onclick={() => onsave(position)}>{saveLabel}</button>
    </footer>
  </div>
</div>

<style>
  .wide {
    width: min(760px, 100%);
  }
  .map-box {
    position: relative;
    isolation: isolate;
    height: min(60vh, 480px);
    border-radius: 8px;
    overflow: hidden;
  }
  .map {
    position: absolute;
    inset: 0;
    z-index: 0;
  }
  .search {
    position: absolute;
    top: 10px;
    left: 54px;
    right: 10px;
    z-index: 600;
  }
  .coords {
    margin-top: 8px;
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
  }
</style>
