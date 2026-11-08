import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyTheme, nextTheme } from './theme.js';

test('Umschalter läuft automatisch → hell → dunkel → automatisch', () => {
  assert.equal(nextTheme('auto'), 'light');
  assert.equal(nextTheme('light'), 'dark');
  assert.equal(nextTheme('dark'), 'auto');
  assert.equal(nextTheme('quatsch'), 'auto');
});

test('hell und dunkel setzen data-theme, automatisch entfernt es', () => {
  const root = { dataset: {} };
  applyTheme('dark', root);
  assert.equal(root.dataset.theme, 'dark');
  applyTheme('light', root);
  assert.equal(root.dataset.theme, 'light');
  applyTheme('auto', root);
  assert.equal('theme' in root.dataset, false);
});
