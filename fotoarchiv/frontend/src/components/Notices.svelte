<script>
  import { dismiss, notices } from '../lib/notices.svelte.js';
  import Icon from './Icon.svelte';

  // tasks: laufende Hintergrundaufgaben vom Server
  let { tasks = [] } = $props();
</script>

<div class="notices" aria-live="polite">
  {#each tasks as task (task.id)}
    <div class="notice">
      <span class="spinner"></span>
      <span class="text">{task.label}</span>
      <span class="progress">{task.done} / {task.total}</span>
    </div>
  {/each}
  {#each notices as notice (notice.id)}
    <div class="notice" class:error={notice.kind === 'error'}>
      {#if notice.kind === 'error'}<Icon name="alert" size={18} />{/if}
      <span class="text">{notice.text}</span>
      {#if notice.action}
        <button class="action" onclick={() => (notice.action(), dismiss(notice.id))}>{notice.actionLabel}</button>
      {/if}
      <button class="icon small" onclick={() => dismiss(notice.id)} title="Schließen"><Icon name="close" size={16} /></button>
    </div>
  {/each}
</div>

<style>
  .notices {
    position: fixed;
    left: 50%;
    bottom: 16px;
    z-index: 80;
    transform: translateX(-50%);
    display: grid;
    gap: 8px;
    width: min(520px, calc(100vw - 32px));
    pointer-events: none;
  }
  .notice {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 48px;
    padding: 4px 6px 4px 16px;
    border-radius: 8px;
    background: #323232;
    color: #fff;
    box-shadow: 0 4px 16px rgb(0 0 0 / 0.3);
    pointer-events: auto;
  }
  .notice.error {
    background: #8e1c1c;
  }
  .text {
    flex: 1;
    line-height: 1.4;
  }
  .progress {
    font-variant-numeric: tabular-nums;
    opacity: 0.8;
    padding-right: 10px;
  }
  .action {
    min-height: 32px;
    border: 0;
    background: transparent;
    color: #81d4fa;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .action:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.1);
  }
  button.icon {
    color: #fff;
  }
  button.icon:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.1);
  }
  .spinner {
    width: 16px;
    height: 16px;
    flex: none;
    border: 2px solid #81d4fa;
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
