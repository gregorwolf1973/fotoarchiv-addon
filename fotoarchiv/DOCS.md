# Fotoarchiv

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Foto- und Video-Datenbank direkt in Home Assistant. Die Bilder bleiben ganz normale Dateien auf deinem Datenträger, sortiert nach `JJJJ/MM`. Die Datenbank ist nur ein Index daneben.

## Funktionen (Version 0.01)

- **Import aus einem Samba-Ordner.** Fotos und Videos in den Import-Ordner legen und in der Oberfläche **Import starten** klicken. Die Dateien werden nach Aufnahmedatum in die Bibliothek verschoben.
- **Upload per Drag & Drop.** Dateien oder ganze Ordner auf die Seite ziehen oder über **Hochladen** auswählen.
- **Duplikaterkennung per MD5.** Bereits vorhandene Dateien werden nicht noch einmal aufgenommen. Beim Ordner-Import landen sie in `_duplikate` im Import-Ordner. Die Prüfsumme vom Import wird dauerhaft gespeichert, damit ein Bild auch nach späterer Bearbeitung noch als Duplikat erkannt wird.
- **Bibliothek einlesen.** Übernimmt Dateien, die schon in der Bibliothek liegen, ohne sie zu verschieben.
- **Galerie** mit Tagesgruppen, Zeilen im Blocksatz und flüssigem Scrollen auch bei Zehntausenden Bildern.
- **Zeitleiste rechts.** Ein fester Balken mit Jahreszahlen und einem Cursor zum Ziehen, der Monat und Jahr anzeigt.
- **Einzelansicht** mit Aufnahmedatum, Ort, Personen, Schlagworten, Kamera und Download des Originals. Blättern geht mit den Pfeiltasten oder per Wischen.
- **Formate:** JPEG, PNG, GIF, WebP, TIFF, HEIC/HEIF, AVIF sowie MP4, MOV, M4V, 3GP, MKV, WebM, AVI und MTS.

Geplant sind: Bearbeiten (Drehen, Datum, Ort, Tags, Personen, jeweils direkt in die Datei geschrieben), Löschen mit Papierkorb, Suche, Weltkarte und Gesichtserkennung.

## Einrichtung

1. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories** öffnen und `https://github.com/gregorwolf1973/fotoarchiv-addon` hinzufügen.
2. **Fotoarchiv** installieren. Beim ersten Mal wird das Image auf dem Gerät gebaut, das dauert auf einem Raspberry Pi 5 etwa 5–10 Minuten.
3. Starten und **In Seitenleiste anzeigen** aktivieren.
4. Das Samba-Add-on installieren, falls noch nicht vorhanden. Der Import-Ordner ist dann unter `\\homeassistant\share\fotoarchiv-import` erreichbar.

## Konfiguration

| Option | Standard | Bedeutung |
|---|---|---|
| `library_folder` | `/media/fotoarchiv` | Bibliothek. Liegt sie unter `/media`, sind die Bilder auch im HA-Medienbrowser sichtbar. |
| `import_folder` | `/share/fotoarchiv-import` | Eingangsordner für den Samba-Import |

Beide Ordner sollten auf demselben Datenträger liegen. Dann ist das Einsortieren ein reines Umbenennen und geht sofort.

## Aufnahmedatum

Das Datum wird in dieser Reihenfolge bestimmt:

1. EXIF/XMP `DateTimeOriginal` bzw. bei Videos `CreationDate` (Ortszeit)
2. QuickTime `CreateDate` (UTC, wird in die Zeitzone von Home Assistant umgerechnet)
3. Datum im Dateinamen, z. B. `IMG_20190512_140322.jpg` oder `WhatsApp Image 2019-05-12 at 14.03.22.jpeg`
4. Änderungsdatum der Datei. Dieses Datum wird in der Einzelansicht als **unsicher** markiert.

## Speicherplatz und Backups

- Die Datenbank und die Vorschaubilder liegen im Add-on-Datenordner. Pro Bild braucht das etwa 30–40 KB.
- **Vorschaubilder sind vom Add-on-Backup ausgenommen.** Sie werden bei Bedarf neu erzeugt.
- ⚠️ **Eine vollständige Home-Assistant-Sicherung enthält auch den Ordner `/media`, also das ganze Fotoarchiv.** Bei großen Sammlungen solltest du `media` in den Backup-Einstellungen abwählen und die Fotos separat sichern, z. B. auf ein NAS.

## Sicherheit

Die Oberfläche ist nur über Home Assistant (Ingress) erreichbar. Direkte Zugriffe auf den Port werden abgewiesen, die Anmeldung übernimmt Home Assistant.

## Fehlersuche

- **„Fehlende Programme im Add-on“:** Das Image wurde unvollständig gebaut. Deinstallieren und neu installieren.
- **Ein Bild zeigt nur eine graue Fläche:** Das Vorschaubild konnte nicht erzeugt werden. Genaueres steht im Protokoll des Add-ons.
- **Dateien bleiben im Import-Ordner liegen:** Den Bericht im Import-Fenster unter „Fehler“ und „Übersprungen“ prüfen. Dateien, die beim Start noch kopiert wurden, werden übersprungen und beim nächsten Import übernommen.
