// Mehrsprachigkeit: Der deutsche Text ist zugleich der Schlüssel. t('{n} Fotos', { n: 3 }) schlägt ihn im
// Wörterbuch der Sprache nach; fehlt er, erscheint er auf Deutsch. Eine Sprachänderung lädt die Seite neu,
// deshalb muss t() nicht reaktiv sein.
import en from './i18n/en.js';
import it from './i18n/it.js';
import es from './i18n/es.js';

export const LANGUAGES = [
  { code: 'de', label: 'Deutsch', locale: 'de-DE' },
  { code: 'en', label: 'English', locale: 'en-GB' },
  { code: 'it', label: 'Italiano', locale: 'it-IT' },
  { code: 'es', label: 'Español', locale: 'es-ES' },
];

const STORAGE_KEY = 'fotoarchiv.language';
const DICTIONARIES = { en, it, es };

/** Gespeicherte Wahl, sonst die erste passende Browsersprache, sonst Englisch. */
export function detectLanguage(saved, browserLanguages = []) {
  const known = (code) => LANGUAGES.some((l) => l.code === code);
  if (known(saved)) return saved;
  for (const entry of browserLanguages) {
    const code = String(entry).toLowerCase().split('-')[0];
    if (known(code)) return code;
  }
  return 'en';
}

export function translate(dictionary, text, params) {
  const result = dictionary?.[text] ?? text;
  if (!params) return result;
  return result.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

function readSaved() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

const browser = typeof navigator === 'undefined' ? [] : navigator.languages || [navigator.language];

export const language = detectLanguage(readSaved(), browser);
/** Für Intl und toLocaleString, z. B. new Intl.NumberFormat(locale). */
export const locale = LANGUAGES.find((l) => l.code === language).locale;

if (typeof document !== 'undefined') document.documentElement.lang = language;

export const t = (text, params) => translate(DICTIONARIES[language], text, params);

/** Schlagwort der Bilderkennung in der Sprache der Oberfläche; der Server liefert es je Sprache in "names". */
export const autoName = (entry) => entry?.names?.[language] ?? entry?.name;

/** Text vom Server: wie t(), aber Zahlen im Text gelten als {n} ("12 Dateien …" trifft "{n} Dateien …"). */
export function translateServer(dictionary, text) {
  if (typeof text !== 'string') return text;
  if (dictionary?.[text]) return dictionary[text];
  const number = text.match(/\d+/)?.[0];
  if (number === undefined) return text;
  const pattern = dictionary?.[text.replace(number, '{n}')];
  return pattern ? pattern.replace('{n}', number) : text;
}

export const tServer = (text) => translateServer(DICTIONARIES[language], text);

export function setLanguage(code) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // Ohne Speicher gilt die Wahl nicht dauerhaft; die Browsersprache bleibt.
  }
  location.reload();
}
