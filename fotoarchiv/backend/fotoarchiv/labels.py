"""Schlagworte (tags) und Personen: Normalisierung und Verknüpfung mit Bildern."""

import re
import sqlite3

# kind -> (Tabelle, Verknüpfungstabelle, Spalte)
TABLES = {
    "tags": ("tags", "asset_tags", "tag_id"),
    "persons": ("persons", "asset_persons", "person_id"),
}
MAX_LENGTH = 100


def normalize(names) -> list[str]:
    """Leerzeichen bereinigen, Leere und Doppelte (ohne Groß/Klein) entfernen, Reihenfolge behalten."""
    seen, result = set(), []
    for name in names:
        clean = re.sub(r"\s+", " ", str(name)).strip()[:MAX_LENGTH]
        if clean and clean.casefold() not in seen:
            seen.add(clean.casefold())
            result.append(clean)
    return result


def replace(conn: sqlite3.Connection, asset_id: int, kind: str, names: list[str]):
    table, link, column = TABLES[kind]
    conn.execute(f"DELETE FROM {link} WHERE asset_id = ?", (asset_id,))
    for name in normalize(names):
        conn.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
        conn.execute(
            f"INSERT OR IGNORE INTO {link} (asset_id, {column}) SELECT ?, id FROM {table} WHERE name = ?",
            (asset_id, name),
        )


def current(conn, asset_id: int, kind: str) -> list[str]:
    table, link, column = TABLES[kind]
    rows = conn.execute(
        f"SELECT t.name FROM {table} t JOIN {link} l ON l.{column} = t.id WHERE l.asset_id = ? ORDER BY t.name",
        (asset_id,),
    ).fetchall()
    return [row[0] for row in rows]


def remove_unused(conn: sqlite3.Connection):
    for table, link, column in TABLES.values():
        conn.execute(f"DELETE FROM {table} WHERE id NOT IN (SELECT {column} FROM {link})")
