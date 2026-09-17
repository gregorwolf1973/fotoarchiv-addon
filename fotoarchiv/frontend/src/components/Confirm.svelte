<script>
  let { title, text, confirmLabel = 'OK', danger = false, onconfirm, oncancel } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && oncancel()} role="presentation">
  <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
    <header><h2 id="confirm-title">{title}</h2></header>
    <p>{text}</p>
    <footer>
      <button onclick={oncancel}>Abbrechen</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class={danger ? 'danger' : 'primary'} onclick={onconfirm} autofocus>{confirmLabel}</button>
    </footer>
  </div>
</div>
