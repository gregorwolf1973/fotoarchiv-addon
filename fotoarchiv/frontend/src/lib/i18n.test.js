import assert from 'node:assert/strict';
import { test } from 'node:test';
import en from './i18n/en.js';
import it from './i18n/it.js';
import { detectLanguage, translate, translateServer } from './i18n.js';

test('gespeicherte Wahl geht vor', () => {
  assert.equal(detectLanguage('it', ['de-DE']), 'it');
});

test('erste bekannte Browsersprache gilt, Unbekanntes wird übersprungen', () => {
  assert.equal(detectLanguage(null, ['fr-FR', 'it-CH', 'de']), 'it');
  assert.equal(detectLanguage('xx', ['DE-at']), 'de');
});

test('ohne passende Sprache Englisch', () => {
  assert.equal(detectLanguage(null, ['fr']), 'en');
  assert.equal(detectLanguage(null, []), 'en');
});

test('fehlt die Übersetzung, bleibt der deutsche Text', () => {
  assert.equal(translate({}, 'Löschen'), 'Löschen');
  assert.equal(translate(undefined, '{n} Fotos', { n: 2 }), '2 Fotos');
});

test('Servertexte: Zahlen werden zu {n}, Unbekanntes bleibt Deutsch', () => {
  const dictionary = { 'Bild fehlt': 'Image missing', '{n} Dateien wiederherstellen': 'Restore {n} files' };
  assert.equal(translateServer(dictionary, 'Bild fehlt'), 'Image missing');
  assert.equal(translateServer(dictionary, '12 Dateien wiederherstellen'), 'Restore 12 files');
  assert.equal(translateServer(dictionary, '12 Dateien löschen'), '12 Dateien löschen');
  assert.equal(translateServer(dictionary, null), null);
});

test('Platzhalter werden in der Übersetzung ersetzt', () => {
  assert.equal(translate({ '{n} Fotos': '{n} photos' }, '{n} Fotos', { n: 3 }), '3 photos');
  assert.equal(translate({}, '{a} und {b}', { a: 'x' }), 'x und {b}');
  assert.equal(translate({}, '{n}', { n: 0 }), '0');
});

test('Übersetzungen enthalten dieselben Platzhalter wie der deutsche Text', () => {
  const placeholders = (text) => (text.match(/\{\w+\}/g) ?? []).sort();
  for (const dictionary of [en, it]) {
    for (const [german, translated] of Object.entries(dictionary)) {
      assert.deepEqual(placeholders(translated), placeholders(german), german);
    }
  }
});

test('Englisch und Italienisch haben dieselben Schlüssel', () => {
  assert.deepEqual(Object.keys(en).sort(), Object.keys(it).sort());
});
