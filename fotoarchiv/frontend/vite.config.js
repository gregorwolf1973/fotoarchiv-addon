import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  base: './', // relative Pfade für das Ingress-Präfix
  plugins: [svelte()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8300' },
  },
});
