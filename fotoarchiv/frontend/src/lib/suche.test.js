import assert from 'node:assert/strict';
import { test } from 'node:test';
import { matchAll, matchLabel, splitPlus } from './suche.js';

const lists = [
  ['persons', [{ id: 7, name: 'Angela', count: 3 }]],
  ['tags', [{ id: 1, name: 'Fisch', count: 1784 }, { id: 2, name: 'Angeln', count: 1618 }, { id: 3, name: 'Fischmarkt', count: 9 }]],
  ['auto', [{ id: 'Angelrute', name: 'Angelrute', count: 40 }]],
];

test('Nur mit „+“ und mindestens zwei Teilen', () => {
  assert.equal(splitPlus('Fisch'), null);
  assert.equal(splitPlus('Fisch +'), null);
  assert.deepEqual(splitPlus(' Fisch + angel '), ['Fisch', 'angel']);
  assert.deepEqual(splitPlus('a+b+c'), ['a', 'b', 'c']);
});

test('Gleicher Name vor Anfang vor enthaltenem Text, sonst das häufigste', () => {
  assert.equal(matchLabel('fisch', lists).id, 1); // genau, nicht Fischmarkt
  assert.equal(matchLabel('angel', lists).id, 2); // Anfang: Angeln (1618) vor Angela (3) und Angelrute (40)
  assert.equal(matchLabel('markt', lists).id, 3);
  assert.equal(matchLabel('Angela', lists).kind, 'persons');
  assert.equal(matchLabel('Katze', lists), null);
});

test('Alle Teile müssen passen, doppelte zählen einmal', () => {
  assert.deepEqual(matchAll(['Fisch', 'angel'], lists).map((l) => l.name), ['Fisch', 'Angeln']);
  assert.equal(matchAll(['Fisch', 'Katze'], lists), null);
  assert.equal(matchAll(['Fisch', 'fisch'], lists).length, 1);
});
