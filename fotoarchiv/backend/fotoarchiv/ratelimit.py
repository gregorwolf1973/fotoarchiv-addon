"""Gleitende Zeitfenster und eskalierende Sperren, im Speicher (übernommen aus Simple NAS).

Der Zustand geht beim Neustart verloren. Das ist gewollt: Raten soll langsam werden,
ein dauerhaftes Register braucht es dafür nicht.
"""

import threading
import time
from collections import deque


def split_key(key: str) -> tuple[str, str]:
    """authfail:ip:1.2.3.4 -> ("ip", "1.2.3.4"); ban:1.2.3.4 -> ("ban", "1.2.3.4")"""
    parts = key.split(":", 2)
    if parts[0] == "authfail" and len(parts) == 3:
        return parts[1], parts[2]
    return parts[0], parts[-1] if len(parts) > 1 else ""


class Limiter:
    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._buckets: dict[str, deque] = {}
        self._locks: dict[str, tuple[float, int, float]] = {}  # key -> (bis, Anzahl Sperren, letzte Sperre)
        self._lock = threading.Lock()
        self._ops = 0

    def _prune(self, key, window, now):
        q = self._buckets.get(key)
        if q is None:
            return None
        while q and q[0] <= now - window:
            q.popleft()
        if not q:
            self._buckets.pop(key, None)
            return None
        return q

    def _sweep(self, now):
        """Alle paar hundert Aufrufe alte Zähler wegräumen."""
        self._ops += 1
        if self._ops % 200:
            return
        for key in list(self._buckets):
            q = self._buckets[key]
            if not q or q[-1] <= now - 3600:
                self._buckets.pop(key, None)

    def hit(self, key, limit, window):
        """Ein Ereignis zählen. Gibt (erlaubt, warten_sekunden) zurück."""
        now = self._clock()
        with self._lock:
            self._sweep(now)
            q = self._prune(key, window, now)
            if q is None:
                q = self._buckets[key] = deque()
            if len(q) >= limit:
                return False, max(1, int(q[0] + window - now) + 1)
            q.append(now)
            return True, 0

    def count(self, key, window):
        now = self._clock()
        with self._lock:
            q = self._prune(key, window, now)
            return len(q) if q else 0

    def record(self, key):
        """Ereignis ohne Grenzprüfung zählen (für Fehlversuche)."""
        with self._lock:
            self._buckets.setdefault(key, deque()).append(self._clock())

    def locked(self, key, limit, window):
        return self.banned(key) or self.count(key, window) >= limit

    # ── eskalierende Sperren ─────────────────────────────────────────
    def lock(self, key, base, cap, decay=24 * 3600):
        """Sperre für base * 2^(n-1) Sekunden, n = Sperren innerhalb von `decay`.
        Erste Sperre 15 min, zweite 30, dann 1 h, 2 h … bis cap."""
        now = self._clock()
        with self._lock:
            _until, n, last = self._locks.get(key, (0, 0, 0))
            if last and now - last > decay:
                n = 0
            n += 1
            duration = min(cap, base * (2 ** (n - 1)))
            self._locks[key] = (now + duration, n, now)
            return duration

    def banned(self, key):
        now = self._clock()
        with self._lock:
            entry = self._locks.get(key)
            return bool(entry and entry[0] > now)

    def ban_remaining(self, key):
        now = self._clock()
        with self._lock:
            entry = self._locks.get(key)
            return max(0, int(entry[0] - now)) if entry else 0

    def snapshot(self, window=15 * 60):
        """Aktive Sperren und laufende Fehlerzähler für die Verwaltung.

        Ohne diese Anzeige wäre der Schutz unsichtbar: Wer fünfmal ein falsches Passwort
        eintippt, sieht nichts passieren und weiß nicht, ob die Sperre kaputt oder nur
        noch nicht erreicht ist.
        """
        now = self._clock()
        locks, counters = [], []
        with self._lock:
            for key, (until, n, _last) in list(self._locks.items()):
                if until > now:
                    kind, target = split_key(key)
                    locks.append({"key": key, "kind": kind, "target": target,
                                  "remaining": int(until - now), "strikes": n})
            for key in list(self._buckets):
                if not key.startswith("authfail:"):
                    continue
                q = self._prune(key, window, now)
                if q:
                    kind, target = split_key(key)
                    counters.append({"key": key, "kind": kind, "target": target, "count": len(q)})
        locks.sort(key=lambda x: -x["remaining"])
        counters.sort(key=lambda x: -x["count"])
        return {"locks": locks, "counters": counters}

    def clear(self, key=None, prefix=None):
        with self._lock:
            if key is not None:
                self._buckets.pop(key, None)
                self._locks.pop(key, None)
            if prefix is not None:
                for k in [k for k in self._buckets if k.startswith(prefix)]:
                    self._buckets.pop(k, None)
                for k in [k for k in self._locks if k.startswith(prefix)]:
                    self._locks.pop(k, None)


# Grenzen für den Internetzugang: (Anzahl, Zeitfenster in Sekunden)
REQ_ANON_PER_IP = (120, 60)          # ohne Anmeldung: Anmeldeseite, Skripte, Stile, Manifest, Symbole
# Angemeldet: je Konto statt je IP – eine Familie teilt sich zu Hause eine Adresse. Vorschaubilder
# zählen nicht mit, beim schnellen Scrollen lädt die Galerie davon Tausende in der Minute.
REQ_AUTH_PER_USER = (3000, 60)
AUTHFAIL_IP = (10, 15 * 60)
AUTHFAIL_USER = (10, 15 * 60)
SCAN_PER_IP = (30, 10 * 60)          # API-Aufrufe ohne Anmeldung / unbekannte Pfade -> Scanner
LOCK_BASE = 15 * 60                  # erste Sperre
LOCK_CAP = 24 * 3600                 # Wiederholungstäter landen hier
