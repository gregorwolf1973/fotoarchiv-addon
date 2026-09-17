<script>
  import { searchPlaces } from '../lib/map.js';
  import Icon from './Icon.svelte';

  let { onselect } = $props();

  let query = $state('');
  let results = $state([]);
  let busy = $state(false);
  let message = $state('');

  async function search(e) {
    e.preventDefault();
    if (!query.trim()) return;
    busy = true;
    message = '';
    try {
      results = await searchPlaces(query.trim());
      if (!results.length) message = 'Nichts gefunden';
    } catch (err) {
      results = [];
      message = err.message;
    } finally {
      busy = false;
    }
  }

  function choose(result) {
    onselect(result);
    results = [];
    query = result.name.split(',')[0];
  }
</script>

<form class="place-search" onsubmit={search}>
  <div class="box">
    <Icon name="marker" size={18} />
    <input type="text" bind:value={query} placeholder="Ort suchen, Enter" aria-label="Ort suchen" enterkeyhint="search" />
    {#if busy}<span class="spinner"></span>{/if}
  </div>
  {#if results.length || message}
    <ul>
      {#each results as result}
        <li><button type="button" onclick={() => choose(result)}>{result.name}</button></li>
      {/each}
      {#if message}<li class="message">{message}</li>{/if}
    </ul>
  {/if}
</form>

<style>
  .place-search {
    position: relative;
    width: min(320px, 100%);
  }
  .box {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 10px;
    border-radius: 20px;
    background: var(--surface);
    color: var(--muted);
    box-shadow: 0 2px 8px rgb(0 0 0 / 0.25);
  }
  input[type='text'] {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    outline: none;
  }
  ul {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    margin: 0;
    padding: 6px 0;
    list-style: none;
    border-radius: 12px;
    background: var(--surface);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.25);
  }
  li button {
    width: 100%;
    min-height: 40px;
    padding: 6px 14px;
    border: 0;
    border-radius: 0;
    background: transparent;
    font-weight: 400;
    text-align: left;
    line-height: 1.35;
  }
  .message {
    padding: 8px 14px;
    color: var(--muted);
  }
  .spinner {
    width: 14px;
    height: 14px;
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
</style>
