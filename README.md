<p align="center">
  <img src="fotoarchiv/logo.png" alt="Fotoarchiv" width="250">
</p>

<h1 align="center">Fotoarchiv – Photo &amp; Video Library for Home Assistant</h1>

<p align="center">
  <b>Self-hosted Google Photos alternative as a Home Assistant add-on.</b><br>
  Timeline, world map, face recognition, duplicate finder, family sharing as an installable app –
  and your photos stay plain files on your own disk.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgregorwolf1973%2Ffotoarchiv-addon"><img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Add repository to Home Assistant"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fgregorwolf1973%2Ffotoarchiv-addon%2Fmain%2Ffotoarchiv%2Fconfig.yaml&amp;query=%24.version&amp;label=version&amp;color=03a9f4" alt="Version">
  <img src="https://img.shields.io/badge/Home%20Assistant-add--on-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant add-on">
  <img src="https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-green" alt="Architectures">
  <img src="https://img.shields.io/badge/Raspberry%20Pi%205-tested-C51A4A?logo=raspberrypi&amp;logoColor=white" alt="Raspberry Pi 5">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://buymeacoffee.com/gregorwolf1973"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&amp;logoColor=black" alt="Buy me a coffee"></a>
</p>

---

## Why Fotoarchiv?

- **Runs where your smart home already runs.** One click in Home Assistant, no extra server, no Docker compose files. Built and tested for **tens of thousands of photos on a Raspberry Pi 5**.
- **No lock-in.** Photos and videos stay normal files sorted into `YYYY/MM` folders. Tags, people, dates and locations are written **into the files** (EXIF/XMP via exiftool), so digiKam, Lightroom or your phone see the same data. The database is only an index – your photos and everything you wrote into them stay intact without it.
- **Made for families.** Everyone gets their own login and can install Fotoarchiv on their phone like an app – Android can share photos straight from the gallery.

## Features

| | |
|---|---|
| 🖼️ **Gallery** | Justified layout grouped by day, 5 zoom levels, smooth scrolling through tens of thousands of photos, draggable year timeline |
| 🗺️ **World map** | Photos clustered by location, **time slider** to show only one year (or 2, 5, 10), drag photos without GPS onto the map to place them |
| 🙂 **Face recognition** | Runs locally (InsightFace), groups faces, names are written into the files and are searchable |
| 🔍 **Search** | People, tags, date range and free text; click the search field to pick from all tags |
| ✏️ **Edit in the file** | Date, location, tags, people, rotation – single photos or hundreds at once, with undo |
| 🧹 **Duplicates** | Exact duplicates (MD5) never get imported twice; similar shots, WhatsApp copies and resized versions are found and cleaned up while keeping tags and locations |
| 📱 **Family app (PWA)** | Installable on Android and iPhone, share-to-upload on Android, resumable chunked uploads (works through Cloudflare's 100 MB limit), skips photos the archive already has |
| 🔐 **Internet access** | Own accounts with roles (view / upload & edit without deleting / edit), lockout after failed logins, CrowdSec integration, works behind Nginx Proxy Manager or Cloudflare Tunnel |
| 📥 **Import** | Samba inbox folder, drag & drop in the browser, **automatic import** for phone sync apps (FolderSync, PhotoSync) |
| 🎞️ **Formats** | JPEG, HEIC/HEIF, PNG, WebP, AVIF, TIFF, GIF, MP4, MOV, M4V, 3GP, MKV, WebM, AVI, MTS, MPG, WMV – HEIC and HEVC/H.265 can be converted automatically so every browser plays them |
| 🗑️ **Trash** | Deleted files can be restored and are removed after a configurable number of days |

## Installation

1. Click the **Add repository** button above – or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add
   `https://github.com/gregorwolf1973/fotoarchiv-addon`
2. Install **Fotoarchiv**, start it and enable **Show in sidebar**.
3. Drop photos into the import folder or drag them into the browser.

The first installation builds the image on your device (about 5–10 minutes on a Raspberry Pi 5).
Full documentation (German): **[DOCS.md](fotoarchiv/DOCS.md)**

## Support

If Fotoarchiv saves your family photos, a coffee keeps the development going ☕

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Found a bug or have an idea? Please open an [issue](https://github.com/gregorwolf1973/fotoarchiv-addon/issues). A ⭐ helps others find the project.

## License

The code is released under the [MIT License](LICENSE).
Face recognition uses the InsightFace model pack `buffalo_l`, which is **not** part of this repository: the add-on downloads it on first start from the official InsightFace release. Those models are licensed for **non-commercial use only**. If you don't want that, switch off `face_recognition` – everything else works without it.

---

## 🇩🇪 Deutsch

**Fotoarchiv** ist eine Foto- und Video-Datenbank als Home-Assistant-Add-on – eine selbst gehostete Alternative zu Google Fotos, gebaut für Zehntausende Bilder auf einem Raspberry Pi 5.

- **Galerie** mit Tagesgruppen und ziehbarer Jahres-Zeitleiste
- **Weltkarte** mit Zeitregler: nur die Fotos eines Jahres (oder 2, 5, 10 Jahre) zeigen; Fotos ohne Ort einfach auf die Karte ziehen
- **Gesichtserkennung** lokal auf dem Pi, die Namen landen in den Dateien
- **Suche** nach Personen, Schlagworten, Zeitraum und Freitext
- **Bearbeiten direkt in der Datei:** Datum, Ort, Schlagworte, Personen, Drehen – auch für viele Fotos auf einmal
- **Doppelte und ähnliche Fotos finden** und aufräumen, Schlagworte und Ort bleiben erhalten
- **Familien-App:** auf Android und iPhone installierbar, unter Android Hochladen direkt aus dem Teilen-Menü, große Videos in Stücken, schon Vorhandenes wird nicht erneut übertragen
- **Zugang übers Internet** mit eigenen Konten und Rollen (Ansehen / Hochladen + Bearbeiten ohne Löschen / Bearbeiten), Sperren nach Fehlversuchen, CrowdSec
- **Import** per Samba-Ordner, Drag & Drop oder automatisch für Handy-Sync-Apps
- **HEIC und H.265** werden auf Wunsch umgewandelt, damit jeder Browser sie zeigt
- **Keine Abhängigkeit:** Die Bilder bleiben normale Dateien in `JJJJ/MM`, die Datenbank ist nur ein Index

**Installation:** Oben auf **Add repository** klicken oder unter **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories** die Adresse `https://github.com/gregorwolf1973/fotoarchiv-addon` hinzufügen, dann **Fotoarchiv** installieren. Alle Details in der **[Dokumentation](fotoarchiv/DOCS.md)**.

**Lizenz:** Der Code steht unter der [MIT-Lizenz](LICENSE). Die Modelle der Gesichtserkennung (InsightFace `buffalo_l`) gehören nicht dazu: Das Add-on lädt sie beim ersten Start von InsightFace, und sie dürfen nur nicht-kommerziell genutzt werden. Ohne Gesichtserkennung (`face_recognition` aus) läuft alles andere genauso.

<sub>Keywords: Home Assistant photo gallery, Home Assistant add-on photos, self-hosted photo library, Google Photos alternative, Immich alternative, PhotoPrism alternative, family photo sharing, Raspberry Pi photo server, face recognition, EXIF XMP editor, duplicate photo finder, photo map, Fotoverwaltung, Fotogalerie, Bilderverwaltung</sub>
