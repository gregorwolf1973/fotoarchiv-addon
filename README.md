# Fotoarchiv – Home Assistant Add-on

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Foto- und Video-Datenbank für Home Assistant, gebaut für Zehntausende Bilder auf einem Raspberry Pi 5.

---

## 🇩🇪 Deutsch

### Funktionen

- **Samba-Import:** Dateien in einen Ordner legen und den Import starten. Das Add-on sortiert sie nach Aufnahmedatum in `JJJJ/MM` ein.
- **Drag & Drop:** Einzelne Dateien oder ganze Ordner in den Browser ziehen.
- **Duplikate** werden per MD5-Prüfsumme erkannt und nicht doppelt aufgenommen.
- **Galerie mit Zeitleiste:** Ein fester Balken mit Jahreszahlen und ein ziehbarer Cursor mit Datumsanzeige.
- **Suche** nach Personen, Schlagworten, Zeitraum und Freitext.
- **Bearbeiten direkt in der Datei:** Datum, Personen, Schlagworte, Ort und Drehen, auch für viele Fotos auf einmal.
- **Papierkorb** mit Wiederherstellen und automatischem Leeren.
- **Weltkarte** mit gruppierten Fotos. Fotos ohne Ort zieht man einfach auf die Karte.
- **Zugriff übers Internet** mit eigenen Konten (Ansehen/Bearbeiten), Sperren nach Fehlversuchen und CrowdSec-Anbindung, hinter Nginx Proxy Manager oder Cloudflare Tunnel.
- **Gesichtserkennung** lokal auf dem Pi. Gruppen benennen, die Namen landen in den Dateien, neue Fotos werden automatisch erkannt.
- **Fotos und Videos:** JPEG, HEIC, PNG, WebP, AVIF, MP4, MOV und mehr.
- **Ohne Sonderformat:** Die Bilder bleiben normale Dateien, die Datenbank ist nur ein Index.


### Installation

1. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**
2. `https://github.com/gregorwolf1973/fotoarchiv-addon` hinzufügen
3. **Fotoarchiv** installieren, starten und **In Seitenleiste anzeigen** aktivieren

Details stehen in der [Dokumentation](fotoarchiv/DOCS.md).

---

## 🇬🇧 English

Photo and video library for Home Assistant: Samba inbox import, drag & drop upload, MD5 duplicate detection, date-sorted storage (`YYYY/MM`), justified gallery with a draggable year timeline, search by people/tags/date, editing that writes straight into the files (exiftool), bulk actions, a trash, a world map where photos without location can be dragged onto the map, local face recognition (InsightFace) whose names are written into the files, and optional internet access with accounts, lockouts and CrowdSec integration. HEIC and video support. Files stay plain files; the database is only an index.

Install by adding `https://github.com/gregorwolf1973/fotoarchiv-addon` as an add-on repository.
