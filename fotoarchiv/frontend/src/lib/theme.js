// Farbschema: "auto" folgt der Einstellung des Geräts, "light"/"dark" erzwingen es über data-theme am <html>.
export const THEMES = ['auto', 'light', 'dark'];
const STORAGE_KEY = 'fotoarchiv.theme';

export function readTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(saved) ? saved : 'auto';
  } catch {
    return 'auto';
  }
}

export function applyTheme(theme, root = document.documentElement) {
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
  else delete root.dataset.theme;
}

export function saveTheme(theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Ohne Speicher gilt die Wahl nur bis zum Neuladen.
  }
  applyTheme(theme);
}

export const nextTheme = (theme) => THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
