# Fotoarchiv

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Foto- und Video-Datenbank direkt in Home Assistant. Die Bilder bleiben ganz normale Dateien auf deinem Datenträger, sortiert nach `JJJJ/MM`. Die Datenbank ist nur ein Index daneben.

## Funktionen (Version 0.08)

- **Import aus einem Samba-Ordner.** Fotos und Videos in den Import-Ordner legen und in der Oberfläche **Import starten** klicken. Die Dateien werden nach Aufnahmedatum in die Bibliothek verschoben.
- **Upload per Drag & Drop.** Dateien oder ganze Ordner auf die Seite ziehen oder über **Hochladen** auswählen.
- **Duplikaterkennung per MD5.** Bereits vorhandene Dateien werden nicht noch einmal aufgenommen. Beim Ordner-Import landen sie in `_duplikate` im Import-Ordner. Die Prüfsumme vom Import wird dauerhaft gespeichert, damit ein Bild auch nach späterer Bearbeitung noch als Duplikat erkannt wird.
- **Bibliothek abgleichen.** Übernimmt Dateien, die schon in der Bibliothek liegen, ohne sie zu verschieben, und erkennt von Hand verschobene oder gelöschte Dateien. Siehe [Dateien außerhalb des Fotoarchivs ändern](#dateien-außerhalb-des-fotoarchivs-ändern).
- **Galerie** mit Tagesgruppen, Zeilen im Blocksatz und flüssigem Scrollen auch bei Zehntausenden Bildern. Die Vorschaugröße lässt sich in 5 Stufen zoomen, die kleinsten zwei gruppieren nach Monat.
- **Zeitleiste rechts.** Ein fester Balken mit Jahreszahlen und einem Cursor zum Ziehen, der Monat und Jahr anzeigt.
- **Einzelansicht** mit Aufnahmedatum, Ort, Personen, Schlagworten, Kamera und Download des Originals. Blättern geht mit den Pfeiltasten oder per Wischen.
- **Suche** nach Personen, Schlagworten, Zeitraum und Freitext (Dateiname, Kamera, Personen- und Schlagwortnamen). Mehrere Filter gelten gemeinsam.
- **Bearbeiten direkt in der Datei:** Drehen, Aufnahmedatum, Personen, Schlagworte und Ort entfernen. Siehe [Bearbeiten](#bearbeiten).
- **Mehrfachauswahl:** Personen und Schlagworte hinzufügen oder entfernen, Datum setzen, drehen und löschen für viele Dateien auf einmal.
- **Papierkorb:** Gelöschte Dateien lassen sich wiederherstellen und werden nach einstellbarer Zeit endgültig gelöscht.
- **Internetzugang** mit eigenen Konten, Sperren nach Fehlversuchen und CrowdSec-Anbindung. Siehe [Zugriff übers Internet](#zugriff-übers-internet).
- **Gesichtserkennung:** Gesichter werden im Hintergrund gefunden und gruppiert. Benannte Personen stehen in den Dateien und sind durchsuchbar. Siehe [Gesichtserkennung](#gesichtserkennung).
- **Weltkarte:** Fotos gruppiert nach Aufnahmeort. Fotos ohne Ort zieht man aus dem Fenster „Ohne Ort“ auf die Karte. Siehe [Karte](#karte).
- **Formate:** JPEG, PNG, GIF, WebP, TIFF, HEIC/HEIF, AVIF sowie MP4, MOV, M4V, 3GP, MKV, WebM, AVI und MTS.

Alle ursprünglich geplanten Funktionen sind umgesetzt.

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
| `face_recognition` | `true` | Gesichtserkennung im Hintergrund ein/aus |
| `public_enabled` | `false` | Internetzugang auf Port 8301 starten |
| `public_trusted_proxies` | `127.0.0.1`, `::1`, `172.30.32.0/23` | Reverse Proxys, deren Angabe zur Besucheradresse geglaubt wird |
| `public_cookie_secure` | `true` | Sitzungs-Cookie nur über HTTPS (nur zum Testen ausschalten) |
| `public_session_hours` | `12` | Gültigkeit einer Anmeldung |
| `public_log_export_path` | – | Optionale Kopie des Zugriffsprotokolls |

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
| Gesichtsrahmen ein/aus | f | Gesichts-Symbol |
| Vorschau größer/kleiner | Strg + Mausrad, Touchpad-Geste oder − / + unten links | zwei Finger zusammenziehen oder auseinanderziehen |

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

## Dateien außerhalb des Fotoarchivs ändern

Die Bibliothek besteht aus normalen Dateien. Du kannst sie also auch per Samba oder Dateimanager verschieben, umbenennen oder löschen. Die Datenbank bemerkt das erst beim nächsten **Importieren → Bibliothek abgleichen**:

| Du hast … | Beim Abgleich passiert … |
|---|---|
| eine Datei verschoben oder umbenannt | Sie wird über die MD5-Summe ihrem Eintrag **wieder zugeordnet**. Schlagworte, Personen und Papierkorb-Verlauf bleiben erhalten. |
| eine Datei gelöscht | Der Eintrag wird unter **Dateien fehlen** aufgelistet. Mit **Fehlende Einträge entfernen** löschst du ihn nach einer Bestätigung. |
| eine neue Datei in die Bibliothek kopiert | Sie wird aufgenommen, ohne verschoben zu werden. |

Bis zum Abgleich erscheint ein von Hand gelöschtes Foto weiter in der Galerie (aus dem Vorschaubild-Cache), lässt sich aber nicht öffnen oder bearbeiten.

Legst du eine von Hand gelöschte Datei später wieder in den Import-Ordner oder lädst sie hoch, übernimmt sie ihren alten Eintrag und wird nicht als Duplikat abgewiesen.

**Schutz vor Datenverlust:** Fehlende Einträge werden nie automatisch entfernt. Ist die Bibliothek leer, etwa weil das Laufwerk gerade nicht eingebunden ist, lehnt das Add-on das Entfernen ab.

## Gesichtserkennung

Nach dem Start durchsucht das Add-on alle Fotos nach Gesichtern, die neuesten zuerst. Der Fortschritt steht oben in der Ansicht **Personen**. Auf einem Raspberry Pi 5 dauert das etwa 1 Sekunde pro Foto, bei 30.000 Fotos also rund 8–9 Stunden. Die Oberfläche bleibt währenddessen bedienbar, die Erkennung nutzt nur zwei Prozessorkerne.

**So gehst du vor:**

1. Unter **Personen → Unbekannte Gesichter** stehen Gruppen ähnlicher Gesichter, die größten zuerst.
2. Gruppe antippen, falsche Gesichter abwählen, Namen eingeben und speichern. Der Name wird als Person in alle Fotos der Gruppe geschrieben.
3. Neue Fotos dieser Person werden ab jetzt automatisch zugeordnet und ebenfalls beschriftet (Markierung „auto“). Auch weitere, bereits vorhandene Gruppen, die der Person deutlich ähneln, werden ihr zugeordnet.
4. Fremde Personen lassen sich mit **Ausblenden** aus den Vorschlägen nehmen.

**Korrigieren:**

- **Person antippen → ✕ an einem Gesicht:** Das Gesicht wird gelöst, der Name wird aus dem Foto entfernt und dort nicht wieder vorgeschlagen.
- **In der Einzelansicht** blendet das Gesichts-Symbol (Taste **f**) Rahmen um alle Gesichter ein. Ein Rahmen lässt sich direkt benennen oder lösen.
- **Umbenennen** schreibt den neuen Namen in alle Fotos. Gibst du den Namen einer anderen Person ein, werden beide zusammengeführt.
- Entfernst du eine Person von Hand aus einem Foto (Personen-Chip), löst sich das zugehörige Gesicht ebenfalls.

**Gut zu wissen:**

- Erkannt werden Gesichter ab etwa 36 Pixeln Größe (bezogen auf 1280 Pixel Bildbreite). Sehr kleine Gesichter auf Gruppenfotos werden übersprungen. Videos werden nicht durchsucht.
- Personen, die schon in den Metadaten eines Fotos stehen, etwa aus Lightroom oder digiKam, werden automatisch verknüpft, wenn das Foto genau ein Gesicht und genau eine Person hat.
- Die Modelle **InsightFace buffalo_l** (ca. 280 MB) werden beim ersten Start von GitHub geladen und über SHA-256 geprüft. Sie sind **nur für nicht-kommerzielle Nutzung** freigegeben. Für ein privates Fotoarchiv ist das in Ordnung. Die Modelle sind vom Backup ausgenommen und werden bei Bedarf neu geladen.
- Die Erkennung läuft komplett lokal, es verlassen keine Fotos oder Gesichtsdaten Home Assistant.
- Mit `face_recognition: false` wird sie abgeschaltet. Bereits erkannte Personen bleiben in den Dateien.

## Karte

Über **Karte** oben links wechselst du in die Kartenansicht. Die Suchfilter gelten auch dort, so lassen sich zum Beispiel alle Fotos einer Person auf der Karte anzeigen.

- **Gruppen** zeigen das neueste Foto und die Anzahl. Ein Klick zoomt hinein. Liegen alle Fotos einer Gruppe am selben Punkt, öffnet der Klick sie direkt. Ein Klick auf ein einzelnes Foto öffnet die Einzelansicht mit allen Fotos im sichtbaren Kartenausschnitt.
- **Ohne Ort** listet alle bearbeitbaren Fotos ohne Aufnahmeort. Antippen wählt Fotos aus. Ziehen legt ein Foto oder die ganze Auswahl an der Stelle ab, an der du loslässt. Mit der Maus beginnt das Ziehen sofort, am Handy nach kurzem langem Drücken. Der Ort wird im Hintergrund in die Dateien geschrieben und lässt sich über „Rückgängig“ wieder entfernen.
- **Ortssuche** oben links springt zu einer Stadt oder Adresse, damit du Fotos genau ablegen kannst.
- In der **Einzelansicht** lässt sich der Ort über das Stift-Symbol setzen oder korrigieren: in die Karte tippen oder die Stecknadel verschieben.

Die Kartenkacheln kommen von **OpenStreetMap**, die Ortssuche nutzt **OpenStreetMap Nominatim**. Dafür lädt dein Browser Daten von diesen Diensten. Die Suchbegriffe gehen dabei an Nominatim, deine Fotos verlassen Home Assistant nicht.

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

- Die Datenbank, die Vorschaubilder und die Gesichtsausschnitte liegen im Add-on-Datenordner. Pro Bild braucht das etwa 30–40 KB, dazu etwa 6 KB für die kleine Vorschau. Die kleine Vorschau entsteht erst, wenn ein Bild zum ersten Mal in einer kleinen Zoomstufe angezeigt wird.
- **Vorschaubilder sind vom Add-on-Backup ausgenommen.** Sie werden bei Bedarf neu erzeugt.
- ⚠️ **Eine vollständige Home-Assistant-Sicherung enthält auch den Ordner `/media`, also das ganze Fotoarchiv.** Bei großen Sammlungen solltest du `media` in den Backup-Einstellungen abwählen und die Fotos separat sichern, z. B. auf ein NAS.

## Zugriff übers Internet

Über Home Assistant (Seitenleiste) hast du immer volle Rechte. Für den Zugriff von unterwegs gibt es einen **eigenen Internetzugang** mit eigenen Konten.

### Einrichten

1. In den Add-on-Einstellungen `public_enabled: true` setzen und das Add-on neu starten.
2. In der Oberfläche auf das **Schild-Symbol** klicken und Konten anlegen:
   - **Ansehen:** Fotos, Karte und Personen ansehen und Originale herunterladen.
   - **Bearbeiten:** zusätzlich hochladen, Datum, Ort, Schlagworte und Personen ändern, drehen, in den Papierkorb legen und Gesichter benennen.
   - Import, Abgleich, endgültiges Löschen und die Kontenverwaltung gibt es nur über Home Assistant.
3. Den Internetzugang über deinen Reverse Proxy mit TLS veröffentlichen, siehe unten. **Port 8301 nie direkt im Router freigeben.**

### Nginx Proxy Manager (Add-on)

- **Forward Hostname:** der Hostname des Fotoarchiv-Add-ons, zu finden unter *Einstellungen → Add-ons → Fotoarchiv → Info*. Er sieht etwa so aus: `a1b2c3d4-fotoarchiv`.
- **Forward Port:** `8301`, Schema `http`
- **SSL:** Zertifikat anfordern, *Force SSL* und *HSTS* aktivieren
- **Große Uploads:** Unter *Advanced* `client_max_body_size 0;` eintragen

Das Add-on NPM liegt im internen Home-Assistant-Netz `172.30.32.0/23` und ist damit schon als vertrauenswürdiger Proxy eingetragen.

### Cloudflare Tunnel

Als Dienst `http://a1b2c3d4-fotoarchiv:8301` angeben, mit dem Hostnamen wie oben. Die Besucheradresse übernimmt das Add-on aus `CF-Connecting-IP`. Cloudflare begrenzt Uploads im kostenlosen Tarif auf 100 MB pro Datei.

### Proxy auf einem anderen Gerät

Unter *Einstellungen → Add-ons → Fotoarchiv → Konfiguration → Netzwerk* einen Host-Port für 8301 eintragen. Dann die Adresse des Proxy-Geräts unter `public_trusted_proxies` ergänzen.

### Schutz

- **Fehlversuche:** Nach 10 Fehlversuchen innerhalb von 15 Minuten wird die **Adresse** gesperrt. Unabhängig davon wird auch das **Konto** gesperrt, selbst wenn die Versuche von verschiedenen Adressen kommen. Die erste Sperre dauert 15 Minuten, jede weitere doppelt so lange, höchstens 24 Stunden.
- **Scanner:** Wer ohne Anmeldung wiederholt die API oder unbekannte Pfade aufruft, wird ebenfalls gesperrt.
- **Anfragen:** Pro Adresse ist die Zahl der Anfragen pro Minute begrenzt.
- **Proxy-Angaben:** Die Besucheradresse aus `X-Forwarded-For` bzw. `CF-Connecting-IP` wird **nur** von Adressen aus `public_trusted_proxies` übernommen. Gefälschte Angaben bei direktem Zugriff bleiben wirkungslos.
- **Sitzungen:** Sie werden auf dem Server geführt. Das Cookie ist `HttpOnly`, `Secure` und `SameSite=Lax`. Ändernde Anfragen brauchen zusätzlich ein CSRF-Token.
- **Passwörter:** Sie werden mit scrypt gespeichert, mindestens 10 Zeichen. Ein neues Passwort oder das Deaktivieren eines Kontos beendet sofort alle seine Sitzungen.
- **Sicherheits-Header:** CSP, HSTS über HTTPS, keine Einbettung in fremde Seiten.

Unter **Schild-Symbol → Sitzungen & Sperren** siehst du angemeldete Nutzer und aktive Sperren. Dort lassen sich Sitzungen beenden und Sperren aufheben, etwa wenn du dich beim Testen selbst ausgesperrt hast. Unter **Protokoll** stehen Anmeldungen, Fehlversuche, Sperren und Änderungen.

### CrowdSec

Mit dem CrowdSec-Add-on werden Angreifer zusätzlich an der Firewall bzw. bei Cloudflare gesperrt. Unter **Schild-Symbol → CrowdSec → In CrowdSec einrichten** kopiert das Add-on Parser, Szenarien und die Log-Quelle in die CrowdSec-Konfiguration. Das Zugriffsprotokoll wird dann zusätzlich nach `/config/.fotoarchiv/public_access.log` geschrieben. Danach das CrowdSec-Add-on neu starten.

Szenarien:
- `fotoarchiv/public-bf`: 5 falsche Passwörter in ~50 s
- `fotoarchiv/public-scan`: 10 Aufrufe ohne Anmeldung in ~5 min
- `fotoarchiv/public-locked`: Das Add-on hat die Adresse gesperrt

## Sicherheit

Der Hauptport des Add-ons ist nur über Home Assistant (Ingress) erreichbar. Direkte Zugriffe darauf werden abgewiesen, die Anmeldung übernimmt Home Assistant. Der Internetzugang läuft getrennt davon auf Port 8301 mit eigenen Konten, siehe oben.

## Fehlersuche

- **„Fehlende Programme im Add-on“:** Das Image wurde unvollständig gebaut. Deinstallieren und neu installieren.
- **Ein Bild zeigt nur eine graue Fläche:** Das Vorschaubild konnte nicht erzeugt werden. Genaueres steht im Protokoll des Add-ons.
- **Dateien bleiben im Import-Ordner liegen:** Den Bericht im Import-Fenster unter „Fehler“ und „Übersprungen“ prüfen. Dateien, die beim Start noch kopiert wurden, werden übersprungen und beim nächsten Import übernommen.
