"""Zu Hause direkt ins Heimnetz: Wer über den Proxy kommt, aber dieselbe öffentliche Adresse hat wie
Home Assistant, sitzt im eigenen Netz. Der Internetzugang schickt ihn auf die Heimnetz-Adresse
(public_home_url), damit große Videos nicht durch den Cloudflare-Tunnel müssen.

Die eigene Adresse fragt das Add-on bei Cloudflare ab (cdn-cgi/trace) und merkt sie sich eine Weile.
Kommt eine fremde Adresse, fragt es nach einer Minute erneut – nach der Zwangstrennung des Anschlusses
ändert sich die eigene Adresse.
"""

import ipaddress
import logging
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

TRACE_URL = "https://1.1.1.1/cdn-cgi/trace"
MAX_AGE = 600   # s: so lange gilt die gemerkte Adresse
RETRY = 60      # s: frühestens dann neu fragen, wenn eine fremde Adresse kommt


def trace() -> str | None:
    """Eigene öffentliche Adresse, wie Cloudflare sie sieht."""
    with urllib.request.urlopen(TRACE_URL, timeout=3) as response:
        for line in response.read().decode("ascii", "replace").splitlines():
            if line.startswith("ip="):
                return str(ipaddress.ip_address(line[3:].strip()))
    return None


class PublicAddress:
    def __init__(self, fetch=trace, clock=time.monotonic):
        self._fetch = fetch
        self._clock = clock
        self._ip = None
        self._at = float("-inf")   # letzte Abfrage, auch eine gescheiterte
        self._ok = False
        self._lock = threading.Lock()

    def matches(self, ip: str) -> bool:
        """Ist ip die eigene öffentliche Adresse? Blockiert beim Nachfragen bis zu drei Sekunden."""
        try:
            ip = str(ipaddress.ip_address(ip))
        except ValueError:
            return False
        with self._lock:
            now = self._clock()
            age = now - self._at
            # nach einer gescheiterten Abfrage schon nach einer Minute wieder fragen
            if age > (MAX_AGE if self._ok else RETRY) or (ip != self._ip and age > RETRY):
                self._at = now
                try:
                    self._ip = self._fetch() or self._ip
                    self._ok = True
                except Exception as error:  # ohne Antwort bleibt die alte Adresse
                    log.warning("Eigene öffentliche Adresse nicht ermittelt: %s", error)
                    self._ok = False
            return self._ip is not None and ip == self._ip
