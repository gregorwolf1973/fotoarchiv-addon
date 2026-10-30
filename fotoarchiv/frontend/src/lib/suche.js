// Mehrere Filter auf einmal: „Fisch + Angeln“ wird zu je einem Filter pro Teil.

/** Text an „+“ teilen; null, wenn es keine zwei nicht leeren Teile gibt. */
export function splitPlus(text) {
  if (!text.includes('+')) return null;
  const parts = text.split('+').map((p) => p.trim()).filter(Boolean);
  return parts.length >= 2 ? parts : null;
}

/**
 * Bestes Label für einen Teil: gleicher Name vor Namensanfang vor enthaltenem Text, dann das häufigste.
 * lists: [[kind, [{id, name, count}]], …] in der gewünschten Reihenfolge (z. B. Personen vor Schlagworten).
 */
export function matchLabel(part, lists) {
  const needle = part.toLocaleLowerCase();
  let best = null;
  for (const [kind, list] of lists) {
    for (const l of list) {
      const name = l.name.toLocaleLowerCase();
      const rank = name === needle ? 3 : name.startsWith(needle) ? 2 : name.includes(needle) ? 1 : 0;
      if (rank && (!best || rank > best.rank || (rank === best.rank && (l.count ?? 0) > (best.count ?? 0)))) {
        best = { kind, id: l.id, name: l.name, count: l.count, rank };
      }
    }
  }
  if (!best) return null;
  const { rank, ...label } = best;
  return label;
}

/** Alle Teile auflösen; null, sobald ein Teil zu keinem Label passt. Doppelte fallen weg. */
export function matchAll(parts, lists) {
  const found = [];
  for (const part of parts) {
    const label = matchLabel(part, lists);
    if (!label) return null;
    if (!found.some((f) => f.kind === label.kind && f.id === label.id)) found.push(label);
  }
  return found;
}
