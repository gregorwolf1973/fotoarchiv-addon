# Fotoarchiv

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Foto- und Video-Datenbank direkt in Home Assistant. Die Bilder bleiben ganz normale Dateien auf deinem Datenträger, sortiert nach `JJJJ/MM`. Die Datenbank ist nur ein Index daneben.

## Funktionen (Version 0.02)

- **Import aus einem Samba-Ordner.** Fotos und Videos in den Import-Ordner legen und in der Oberfläche **Import starten** klicken. Die Dateien werden nach Aufnahmedatum in die Bibliothek verschoben.
- **Upload per Drag & Drop.** Dateien oder ganze Ordner auf die Seite ziehen oder über **Hochladen** auswählen.
- **Duplikaterkennung per MD5.** Bereits vorhandene Dateien werden nicht noch einmal aufgenommen. Beim Ordner-Import landen sie in `_duplikate` im Import-Ordner. Die Prüfsumme vom Import wird dauerhaft gespeichert, damit ein Bild auch nach späterer Bearbeitung noch als Duplikat erkannt wird.
- **Bibliothek einlesen.** Übernimmt Dateien, die schon in der Bibliothek liegen, ohne sie zu verschieben.
- **Galerie** mit Tagesgruppen, Zeilen im Blocksatz und flüssigem Scrollen auch bei Zehntausenden Bildern.
- **Zeitleiste rechts.** Ein fester Balken mit Jahreszahlen und einem Cursor zum Ziehen, der Monat und Jahr anzeigt.
- **Einzelansicht** mit Aufnahmedatum, Ort, Personen, Schlagworten, Kamera und Download des Originals. Blättern geht mit den Pfeiltasten oder per Wischen.
- **Suche** nach Personen, Schlagworten, Zeitraum und Freitext (Dateiname, Kamera, Personen- und Schlagwortnamen). Mehrere Filter gelten gemeinsam.
- **Bearbeiten direkt in der Datei:** Drehen, Aufnahmedatum, Personen, Schlagworte und Ort entfernen. Siehe [Bearbeiten](#bearbeiten).
- **Mehrfachauswahl:** Personen und Schlagworte hinzufügen oder entfernen, Datum setzen, drehen und löschen für viele Dateien auf einmal.
- **Papierkorb:** Gelöschte Dateien lassen sich wiederherstellen und werden nach einstellbarer Zeit endgültig gelöscht.
- **Formate:** JPEG, PNG, GIF, WebP, TIFF, HEIC/HEIF, AVIF sowie MP4, MOV, M4V, 3GP, MKV, WebM, AVI und MTS.

Geplant sind: Weltkarte mit Zuordnen des Aufnahmeorts per Drag & Drop und Gesichtserkennung.

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
| `trash_days` | `30` | So viele Tage bleiben gelöschte Dateien im Papierkorb |

Beide Ordner sollten auf demselben Datenträger liegen. Dann ist das Einsortieren ein reines Umbenennen und geht sofort.

## Bedienung

| Aktion | Maus / Tastatur | Touch |
|---|---|---|
| Foto auswählen | Häkchen oben links auf dem Foto | lange drücken |
| Bereich auswählen | Shift + Klick | – |
| Ganzen Tag auswählen | Häkchen neben dem Datum | Häkchen neben dem Datum |
| Alles auswählen | Strg + A | – |
| Auswahl aufheben | Esc | ✕ in der Leiste |
| Löschen | Entf | Papierkorb-Symbol |
| In der Einzelansicht blättern | ← → | wischen |
| Infobereich ein/aus | i | ⓘ |

## Bearbeiten

Jede Änderung wird **zuerst mit exiftool in die Datei geschrieben**. Danach liest das Add-on die Datei neu ein und übernimmt den Stand in die Datenbank. So stimmen Datei und Datenbank immer überein, und andere Programme wie digiKam, Lightroom oder die Fotos-App am Handy sehen dieselben Angaben.

| Angabe | Wird geschrieben in |
|---|---|
| Aufnahmedatum (Fotos) | EXIF `DateTimeOriginal`, `CreateDate`, `ModifyDate` |
| Aufnahmedatum (Videos) | QuickTime `CreateDate` (UTC) und `Keys:CreationDate` (Ortszeit mit Zeitzone) |
| Schlagworte | XMP `dc:Subject`, bei JPEG/TIFF zusätzlich IPTC `Keywords` |
| Personen | XMP `Iptc4xmpExt:PersonInImage` |
| Ort | EXIF GPS bzw. bei Videos `Keys:GPSCoordinates` |
| Drehen (Fotos) | EXIF-Orientierung (verlustfrei, die Bilddaten bleiben unverändert) |
| Drehen (Videos) | Rotationsmatrix der Videospur (verlustfrei) |

- Nach einer Datumsänderung wird die Datei in den passenden `JJJJ/MM`-Ordner verschoben.
- Das Dateidatum (Änderungszeit) bleibt beim Schreiben erhalten.
- **Bearbeitbar** sind JPEG, PNG, WebP, TIFF, HEIC/HEIF, AVIF, MP4, MOV, M4V und 3GP. GIF, MKV, WebM, AVI und MTS können keine Metadaten speichern und werden nur angezeigt.
- **HEIC/AVIF lassen sich nicht drehen.** Die Drehung steckt dort in einem Container-Feld, das exiftool nicht schreiben kann, und die EXIF-Orientierung wird von HEIC-Programmen ignoriert. Handyfotos sind in der Regel schon richtig gedreht.
- Personen, die ein anderes Programm über **Gesichtsmarkierungen** zugeordnet hat, lassen sich hier nicht entfernen. Das kommt mit der Gesichtserkennung.

## Papierkorb

Gelöschte Dateien werden nach `.papierkorb` in der Bibliothek verschoben. Der Ordner beginnt mit einem Punkt und ist deshalb im HA-Medienbrowser nicht sichtbar. Über das Papierkorb-Symbol oben rechts lassen sich Dateien wiederherstellen oder endgültig löschen. Nach `trash_days` Tagen löscht das Add-on sie automatisch.

Eine Datei im Papierkorb gilt beim Import weiterhin als vorhanden. Sie wird also als Duplikat erkannt.

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
