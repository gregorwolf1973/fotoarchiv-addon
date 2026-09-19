# Fotoarchiv

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

Foto- und Video-Datenbank direkt in Home Assistant. Die Bilder bleiben ganz normale Dateien auf deinem Datenträger, sortiert nach `JJJJ/MM`. Die Datenbank ist nur ein Index daneben.

## Funktionen

- **Import aus einem Samba-Ordner.** Fotos und Videos in den Import-Ordner legen und in der Oberfläche **Import starten** klicken. Die Dateien werden nach Aufnahmedatum in die Bibliothek verschoben.
- **Handy automatisch sichern:** Eine Sync-App lädt im WLAN in den Import-Ordner hoch, das Add-on liest neue Dateien von selbst ein. Nur in eine Richtung. Siehe [Handy automatisch sichern](#handy-automatisch-sichern).
- **Als App aufs Handy:** installierbar über den Internetzugang, unter Android mit Teilen-Menü. Siehe [Als App aufs Handy](#als-app-aufs-handy-familie).
- **Upload per Drag & Drop.** Dateien oder ganze Ordner auf die Seite ziehen oder über **Hochladen** auswählen.
- **Duplikaterkennung per MD5.** Bereits vorhandene Dateien werden nicht noch einmal aufgenommen. Beim Ordner-Import landen sie in `_duplikate` im Import-Ordner. Die Prüfsumme vom Import wird dauerhaft gespeichert, damit ein Bild auch nach späterer Bearbeitung noch als Duplikat erkannt wird.
- **Doppelte und ähnliche Fotos finden:** verkleinerte Kopien, anders gespeicherte Fassungen und Serien. Die beste Fassung wird vorgeschlagen, der Rest kommt in den Papierkorb. Siehe [Doppelte Fotos](#doppelte-fotos).
- **Bibliothek abgleichen.** Übernimmt Dateien, die schon in der Bibliothek liegen, ohne sie zu verschieben, und erkennt von Hand verschobene oder gelöschte Dateien. Siehe [Dateien außerhalb des Fotoarchivs ändern](#dateien-außerhalb-des-fotoarchivs-ändern).
- **Galerie** mit Tagesgruppen, Zeilen im Blocksatz und flüssigem Scrollen auch bei Zehntausenden Bildern. Die Vorschaugröße lässt sich in 5 Stufen zoomen, die kleinsten zwei gruppieren nach Monat.
- **Zeitleiste rechts.** Ein fester Balken mit Jahreszahlen und einem Cursor zum Ziehen, der Monat und Jahr anzeigt.
- **Einzelansicht** mit Aufnahmedatum, Ort, Personen, Schlagworten, Kamera und Download des Originals. Blättern geht mit den Pfeiltasten oder per Wischen. Zoomen bis 8-fach mit Mausrad, Doppelklick oder zwei Fingern; beim Hineinzoomen wird das Original in voller Auflösung nachgeladen (JPEG, PNG, WebP, GIF, AVIF bis 60 MB – HEIC und TIFF kann der Browser nicht anzeigen, dort bleibt es bei der Großansicht).
- **Suche** nach Personen, Schlagworten, Zeitraum und Freitext (Dateiname, Kamera, Personen- und Schlagwortnamen). Mehrere Filter gelten gemeinsam.
- **Bearbeiten direkt in der Datei:** Drehen, Aufnahmedatum, Personen, Schlagworte und Ort entfernen. Siehe [Bearbeiten](#bearbeiten).
- **Mehrfachauswahl:** Personen und Schlagworte hinzufügen oder entfernen, Datum und Ort setzen, drehen und löschen für viele Dateien auf einmal.
- **Papierkorb:** Gelöschte Dateien lassen sich wiederherstellen und werden nach einstellbarer Zeit endgültig gelöscht.
- **Speicherplatz:** Nach Größe sortiert – größte oder kleinste zuerst –, gefiltert nach Videos oder Fotos und Mindestgröße, zum Ansehen und Aussortieren. Siehe [Speicherplatz und Backups](#speicherplatz-und-backups).
- **Internetzugang** mit eigenen Konten, Sperren nach Fehlversuchen und CrowdSec-Anbindung. Siehe [Zugriff übers Internet](#zugriff-übers-internet).
- **Gesichtserkennung:** Gesichter werden im Hintergrund gefunden und gruppiert. Benannte Personen stehen in den Dateien und sind durchsuchbar. Siehe [Gesichtserkennung](#gesichtserkennung).
- **Weltkarte:** Fotos gruppiert nach Aufnahmeort, mit Zeitregler für ein Jahr oder mehrere. Fotos ohne Ort zieht man aus dem Fenster „Ohne Ort“ auf die Karte. Siehe [Karte](#karte).
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
| `face_threads` | `2` | Prozessorkerne für die Gesichtserkennung (1–8). Auf dem Pi 5 sind 3 ein guter Wert, wenn Home Assistant flüssig bleiben soll. Wirkt nach einem Neustart des Add-ons. |
| `duplicate_detection` | `true` | Suche nach doppelten und ähnlichen Fotos ein/aus |
| `convert_on_import` | `false` | HEIC und nicht abspielbare Videos beim Import umwandeln, siehe [Umwandeln](#umwandeln) |
| `auto_import` | `false` | Import-Ordner jede Minute prüfen und neue Dateien selbst einlesen, siehe [Handy automatisch sichern](#handy-automatisch-sichern) |
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
| Foto vergrößern | Mausrad, Doppelklick, + / − (0 = zurück) | zwei Finger auseinanderziehen, doppelt tippen |
| Vergrößertes Foto verschieben | ziehen | mit einem Finger ziehen |
| Infobereich ein/aus | i | ⓘ |
| Gesichtsrahmen ein/aus | f | Gesichts-Symbol |
| Vorschau größer/kleiner | Strg + Mausrad, Touchpad-Geste oder − / + unten links | zwei Finger zusammenziehen oder auseinanderziehen |

## Als App aufs Handy (Familie)

Über den Internetzugang lässt sich das Fotoarchiv wie eine App installieren, ganz ohne App-Store. Jede Person bekommt ein eigenes Konto, zum Hochladen mit der Rolle **Hochladen + Bearbeiten (ohne Löschen)**.

**Android (Chrome):** Die Adresse öffnen, zum Beispiel `https://foto.example.org`, und anmelden. Oben erscheint **App installieren**, antippen und fertig. Danach steht das Fotoarchiv im **Teilen-Menü** der Galerie: Fotos auswählen, *Teilen*, *Fotoarchiv*. Die Fotos werden sofort hochgeladen.

**iPhone (Safari):** Die Adresse öffnen und anmelden. Unten auf *Teilen* tippen und dann **„Zum Home-Bildschirm“**. Einen Hinweis dazu zeigt die Seite einmal selbst an. Hochladen geht über den Knopf *Hochladen*, der die Mediathek öffnet, auch mit vielen Fotos auf einmal. Ins Teilen-Menü von Fotos lässt Apple Web-Apps nicht.

Damit das Handy nicht stundenlang beschäftigt ist:

- **Schon Vorhandenes wird nicht gesendet.** Vor dem Hochladen fragt die App, welche Dateien das Archiv schon kennt (gleicher Name und gleiche Größe, auch im Papierkorb). Teilt jemand ein ganzes Album noch einmal, gehen nur die neuen Fotos über die Leitung.
- **Schmale Leiste statt Liste:** Am Handy zeigt der Upload nur eine Leiste mit Fortschritt und Restzeit; man kann währenddessen weiter blättern. Antippen klappt die Liste auf, **Abbrechen** stoppt alles Offene.
- **Bildschirm bleibt an**, solange hochgeladen wird, damit der Upload nicht stehen bleibt. Wer die Seite schließt, wird vorher gewarnt.

Große Videos werden in Stücken von 32 MB übertragen. So passen sie durch Cloudflare (100 MB je Anfrage im kostenlosen Tarif), und nach einem Funkloch geht es an der Abbruchstelle weiter, statt von vorn. Automatisch im Hintergrund hochladen kann eine Web-App nicht, das erlauben die Handys nur echten Apps.

## Handy automatisch sichern

Das Handy lädt neue Fotos und Videos im WLAN in den Import-Ordner hoch, das Add-on liest sie von selbst ein. Das geht **nur in eine Richtung**: Das Fotoarchiv schreibt nie aufs Handy, und Löschen auf dem Handy löscht nichts im Archiv.

1. In der Konfiguration des Add-ons **`auto_import`** einschalten. Sinnvoll ist dazu `convert_on_import`, damit HEIC-Fotos und HEVC-Videos vom iPhone gleich abspielbar sind.
2. Auf dem Handy eine Sync-App einrichten, Ziel ist die Samba-Freigabe `share`, Ordner `fotoarchiv-import`. Am besten einen Unterordner pro Handy nehmen, etwa `fotoarchiv-import/gregor`.
   - **Android, FolderSync:** Ordnerpaar mit dem Kamera-Ordner (`DCIM/Camera`) als Quelle, Richtung **„Zum Remote-Ordner“**. Unbedingt **„Only resync source files if modified (ignore target deletion)“** anhaken. Der Import verschiebt die Dateien aus dem Ordner, ohne diese Option lädt FolderSync sie bei jedem Lauf erneut hoch. **„Löschungen synchronisieren“** aus. Unter *Sync-Einstellungen* „Nur WLAN“ oder gezielt das Heim-WLAN wählen, als Zeitplan zum Beispiel stündlich.
   - **iPhone, PhotoSync:** Ziel SMB mit dem Ordner oben und „nur neue Fotos übertragen“. Automatisch läuft das über eine Kurzbefehle-Automation, etwa beim Verbinden mit dem Heim-WLAN oder beim Laden.

**Was das Add-on dabei tut:**

- Jede Minute schaut es in den Import-Ordner. Dateien, die sich seit einer Minute nicht mehr geändert haben, gelten als fertig übertragen und werden importiert, wie beim Knopf *Import starten*.
- **Duplikate** sind byte-gleiche Kopien von etwas, das schon im Archiv oder im Papierkorb liegt, erkannt über MD5. Sie werden beim automatischen Import **gelöscht** statt nach `_duplikate` verschoben. So räumt sich der Ordner selbst auf, wenn die App ein Foto noch einmal schickt. Fotos, die du im Archiv in den Papierkorb gelegt hast, kommen dadurch nicht zurück.
- Beschädigte Dateien landen wie gewohnt in `_defekt`. Nicht unterstützte Dateien bleiben liegen und stoßen erst wieder einen Import an, wenn sie sich ändern.
- Der letzte Lauf steht im Import-Fenster mit dem Zusatz *automatisch*.

## Bearbeiten

Jede Änderung wird **zuerst mit exiftool in die Datei geschrieben**. Danach liest das Add-on die Datei neu ein und übernimmt den Stand in die Datenbank. So stimmen Datei und Datenbank immer überein, und andere Programme wie digiKam, Lightroom oder die Fotos-App am Handy sehen dieselben Angaben.

In der Einzelansicht sammelt der Infobereich Änderungen an **Personen, Schlagworten und Ort** zuerst nur vor. Unten erscheint dann eine Leiste mit **Speichern** und **Verwerfen**. Erst *Speichern* schreibt alles zusammen in die Datei. Ein Name, der noch ohne Enter im Feld steht, wird dabei mitgenommen. Wer mit ungespeicherten Änderungen blättert oder die Ansicht schließt, wird vorher gefragt. Datum und Drehen wirken weiterhin sofort.

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
- Personen, die ein anderes Programm über **Gesichtsmarkierungen** zugeordnet hat (Picasa, Google Fotos, Lightroom, Windows-Fotogalerie), lassen sich umbenennen und entfernen. Dabei werden die fremden Markierungen dieser Datei entfernt. Alle übrigen Namen bleiben erhalten und stehen danach in `PersonInImage`, nur die Gesichtsrahmen des anderen Programms gehen verloren.

## Dateien außerhalb des Fotoarchivs ändern

Die Bibliothek besteht aus normalen Dateien. Du kannst sie also auch per Samba oder Dateimanager verschieben, umbenennen oder löschen. Die Datenbank bemerkt das erst beim nächsten **Importieren → Bibliothek abgleichen**:

| Du hast … | Beim Abgleich passiert … |
|---|---|
| eine Datei verschoben oder umbenannt | Sie wird über die MD5-Summe ihrem Eintrag **wieder zugeordnet**. Schlagworte, Personen und Papierkorb-Verlauf bleiben erhalten. |
| eine Datei gelöscht | Der Eintrag wird unter **Dateien fehlen** aufgelistet. Mit **Fehlende Einträge entfernen** löschst du ihn nach einer Bestätigung. |
| eine neue Datei in die Bibliothek kopiert | Sie wird aufgenommen, ohne verschoben zu werden. |

Bis zum Abgleich erscheint ein von Hand gelöschtes Foto weiter in der Galerie (aus dem Vorschaubild-Cache), lässt sich aber nicht öffnen oder bearbeiten.

Legst du eine von Hand gelöschte Datei später wieder in den Import-Ordner oder lädst sie hoch, übernimmt sie ihren alten Eintrag und wird nicht als Duplikat abgewiesen.

**Gründlich prüfen:** Mit dem Häkchen *Dateien gründlich prüfen* liest der Abgleich zusätzlich jede Datei vollständig. Fotos werden ganz dekodiert, Videos mit ffprobe gelesen, und die Prüfsumme wird mit der gespeicherten verglichen. So fallen auch Schäden auf, die beim Import noch nicht zu sehen waren: abgeschnittene JPEGs, deren Anfang noch heil ist, oder Dateien, die auf einer alternden Festplatte kaputtgegangen sind.

- Befunde stehen im Bericht unter **Beschädigt** und bleiben unter **Speicherplatz → Beschädigt** mit Grund sichtbar, bis die Datei bei einer späteren Prüfung wieder in Ordnung ist oder ersetzt wurde.
- **Außerhalb verändert** heißt: Der Inhalt passt nicht mehr zur gespeicherten Prüfsumme. Hast du die Datei mit einem anderen Programm bearbeitet, ist das in Ordnung. Sonst ist es ein Hinweis auf einen Fehler des Datenträgers. Jede Änderung wird nur einmal gemeldet.
- Das dauert auf dem Raspberry Pi mehrere Stunden (jede Datei wird ganz gelesen) und lässt sich mit **Prüfung abbrechen** beenden. Einmal nach einem großen Import und danach alle paar Monate reicht.

**Schutz vor Datenverlust:** Fehlende Einträge werden nie automatisch entfernt. Ist die Bibliothek leer, etwa weil das Laufwerk gerade nicht eingebunden ist, lehnt das Add-on das Entfernen ab.

## Gesichtserkennung

Nach dem Start durchsucht das Add-on alle Fotos nach Gesichtern, die neuesten zuerst. Der Fortschritt steht oben in der Ansicht **Personen**. Auf einem Raspberry Pi 5 dauert das etwa 1 Sekunde pro Foto, bei 30.000 Fotos also rund 8–9 Stunden. Die Oberfläche bleibt währenddessen bedienbar, die Erkennung nutzt standardmäßig zwei Prozessorkerne. Mit der Option `face_threads` gibst du ihr mehr Kerne und kommst schneller durch.

**So gehst du vor:**

1. Unter **Personen → Unbekannte Gesichter** stehen Gruppen ähnlicher Gesichter, die größten zuerst.
2. Gruppe antippen, falsche Gesichter abwählen, Namen eingeben und speichern. Der Name wird als Person in alle Fotos der Gruppe geschrieben. Erkennst du jemanden am Gesicht allein nicht, zeigt das Bilder-Symbol oben im Fenster die **ganzen Fotos** – mit Aufnahmedatum und dem gemeinten Gesicht klein in der Ecke. Die Einstellung wird gemerkt.
3. Neue Fotos dieser Person werden ab jetzt automatisch zugeordnet und ebenfalls beschriftet (Markierung „auto“). Auch weitere, bereits vorhandene Gruppen, die der Person deutlich ähneln, werden ihr zugeordnet.
4. Fremde Personen lassen sich mit **Ausblenden** aus den Vorschlägen nehmen.

**Korrigieren:**

- **Person antippen → ✕ an einem Gesicht:** Das Gesicht wird gelöst, der Name wird aus dem Foto entfernt und dort nicht wieder vorgeschlagen.
- **In der Einzelansicht** blendet das Gesichts-Symbol (Taste **f**) Rahmen um alle Gesichter ein. Ein Rahmen lässt sich direkt benennen oder lösen.
- **Umbenennen** schreibt den neuen Namen in alle Fotos.
- **Person entfernen:** Person antippen → *Person entfernen …*. Der Name verschwindet aus allen Fotos, die Fotos selbst bleiben. Erkannte Gesichter werden wieder zu unbekannten Gesichtern. So wirst du auch Namen los, die ein anderes Programm früher in die Dateien geschrieben hat – solche Personen haben keine erkannten Gesichter, der Dialog zeigt dann stattdessen einige ihrer Fotos.
- **Zusammenführen:** Person antippen → *Mit anderer Person zusammenführen …* → Zielperson wählen. Die Vorschau zeigt, was passiert. Danach tragen alle Fotos den Namen der Zielperson, und die Gesichter gehören zu ihr. Dasselbe passiert, wenn du beim Umbenennen den Namen einer vorhandenen Person eingibst, dann aber mit Rückfrage.
- Entfernst du eine Person von Hand aus einem Foto (Personen-Chip), löst sich das zugehörige Gesicht ebenfalls.

**Gut zu wissen:**

- Erkannt werden Gesichter ab etwa 36 Pixeln Größe (bezogen auf 1280 Pixel Bildbreite). Sehr kleine Gesichter auf Gruppenfotos werden übersprungen. Videos werden nicht durchsucht.
- Personen, die schon in den Metadaten eines Fotos stehen, etwa aus Lightroom oder digiKam, werden automatisch verknüpft, wenn das Foto genau ein Gesicht und genau eine Person hat.
- Die Modelle **InsightFace buffalo_l** (ca. 280 MB) werden beim ersten Start von GitHub geladen und über SHA-256 geprüft. Sie sind **nur für nicht-kommerzielle Nutzung** freigegeben. Für ein privates Fotoarchiv ist das in Ordnung. Die Modelle sind vom Backup ausgenommen und werden bei Bedarf neu geladen.
- Die Erkennung läuft komplett lokal, es verlassen keine Fotos oder Gesichtsdaten Home Assistant.
- Mit `face_recognition: false` wird sie abgeschaltet. Bereits erkannte Personen bleiben in den Dateien.

## Doppelte Fotos

Dateien mit gleicher MD5-Prüfsumme nimmt das Add-on gar nicht erst auf. Dieselbe Aufnahme gibt es aber oft in mehreren Fassungen: als WhatsApp-Kopie, verkleinert, als PNG oder nachbearbeitet. Dafür berechnet das Add-on im Hintergrund für jedes Foto einen **Wahrnehmungs-Hash**. Das ist ein Fingerabdruck der groben Bildstruktur, den Verkleinern, Neukomprimieren oder ein anderes Format kaum verändert. Das geht schnell, auf dem Raspberry Pi 5 dauert es wenige Millisekunden pro Foto.

Über das Symbol **Doppelte Fotos** oben rechts (neben dem Papierkorb) gibt es zwei Listen:

- **Doppelt:** gleiches Motiv, egal wann. Vorgeschlagen wird die Fassung mit der höchsten Auflösung, danach die mit dem verlässlichsten Datum, den meisten Metadaten und der größten Datei.
- **Serien:** sehr ähnliche Fotos, die innerhalb von 30 Sekunden aufgenommen wurden, etwa mehrere Auslösungen hintereinander. Vorgeschlagen wird die größte Datei, weil sie meist die schärfste ist. Serien bitte immer selbst ansehen.

Bedienung:

- Ein Klick auf ein Vorschaubild öffnet die Einzelansicht mit allen Fotos der Gruppe.
- Der Schalter unter jedem Foto legt fest, ob es **behalten** oder **gelöscht** wird. Der Stern markiert den Vorschlag. Mehrere Fotos behalten geht auch.
- **Löschen** legt die nicht behaltenen Fotos einer Gruppe in den Papierkorb. **Alle Vorschläge übernehmen** macht das für alle Gruppen in „Doppelt“ auf einmal, nach einer Rückfrage.
- Ist **Schlagworte, Personen, Ort und Datum übertragen** angehakt (Standard), bekommt das behaltene Foto vorher die Schlagworte und Personen der gelöschten Fotos. Hat es keinen Ort, übernimmt es den Ort. Stammt sein Datum nur aus dem Dateinamen oder der Dateizeit, übernimmt es ein verlässlicheres Datum. Alles wird in die Datei geschrieben.
- **Keine Duplikate** merkt sich, dass diese Fotos zusammengehören dürfen. Sie werden nicht wieder vorgeschlagen.

Beim Import und Upload weist das Add-on auf neue Fotos hin, die einem vorhandenen Foto sehr ähnlich sind. Sie werden trotzdem aufgenommen und erscheinen unter **Doppelte Fotos**.

Grenzen: Der Vergleich erkennt dasselbe Bild, nicht dasselbe Motiv aus anderem Blickwinkel. Stark zugeschnittene oder gespiegelte Fassungen werden nicht erkannt. Sehr gleichförmige Bilder, etwa Schnee oder Himmel, können als ähnlich gelten, deshalb wird nie automatisch gelöscht. Videos werden nicht verglichen.

Mit `duplicate_detection: false` wird die Suche abgeschaltet.

## Karte

Über **Karte** oben links wechselst du in die Kartenansicht. Die Suchfilter gelten auch dort, so lassen sich zum Beispiel alle Fotos einer Person auf der Karte anzeigen.

- **Gruppen** zeigen das neueste Foto und die Anzahl. Ein Klick zoomt hinein. Liegen alle Fotos einer Gruppe am selben Punkt, öffnet der Klick sie direkt. Ein Klick auf ein einzelnes Foto öffnet die Einzelansicht mit allen Fotos im sichtbaren Kartenausschnitt.
- **Ohne Ort** listet alle bearbeitbaren Fotos ohne Aufnahmeort. Antippen wählt Fotos aus. Ziehen legt ein Foto oder die ganze Auswahl an der Stelle ab, an der du loslässt. Mit der Maus beginnt das Ziehen sofort, am Handy nach kurzem langem Drücken. Der Ort wird im Hintergrund in die Dateien geschrieben und lässt sich über „Rückgängig“ wieder entfernen.
- **Ortssuche** oben links springt zu einer Stadt oder Adresse, damit du Fotos genau ablegen kannst.
- In der **Einzelansicht** lässt sich der Ort über das Stift-Symbol setzen oder korrigieren: in die Karte tippen oder die Stecknadel verschieben.
- **Zeitraum:** Unten auf der Karte schaltet *Zeitraum* einen Zeitregler ein. Dann zeigt die Karte nur Fotos aus diesem Zeitraum, standardmäßig ein Jahr; die Länge lässt sich auf 2, 3, 5 oder 10 Jahre stellen. Mit dem Regler oder den Pfeilen ◀ ▶ wandert der Zeitraum vom ältesten Foto bis zum aktuellen Jahr. Die Zahl daneben sagt, wie viele Fotos hineinfallen. Ein Klick auf das Jahr schaltet zurück auf alle Jahre.

Die Kartenkacheln kommen von **OpenStreetMap**, die Ortssuche nutzt **OpenStreetMap Nominatim**. Dafür lädt dein Browser Daten von diesen Diensten. Die Suchbegriffe gehen dabei an Nominatim, deine Fotos verlassen Home Assistant nicht.

## Umwandeln

Manche Dateien kann der Browser nicht anzeigen oder abspielen: **HEIC**-Fotos vom iPhone und Videos in **H.265/HEVC**, 10 Bit oder alten Formaten (AVI, MTS …). Das Fotoarchiv wandelt sie um:

| Datei | wird zu | Dauer auf dem Pi 5 |
|---|---|---|
| HEIC/HEIF | JPEG (Qualität 92, sRGB) | etwa eine Sekunde |
| MOV, AVI … mit H.264 | MP4, **verlustfrei umgepackt** | Sekunden |
| H.265/HEVC, 10 Bit, andere Codecs | MP4 mit H.264 | etwa so lange, wie das Video dauert |

MP4 und WebM, die der Browser abspielen kann, bleiben unangetastet.

- **Vorhandene Dateien:** in der Galerie oder unter *Speicherplatz* auswählen und **Umwandeln** (Pfeile-Symbol) wählen. Nur über Home Assistant, nicht über den Internetzugang.
- **Neue Dateien:** mit `convert_on_import: true` werden sie gleich nach dem Import vorgemerkt.
- Umgewandelt wird nacheinander im Hintergrund mit niedriger Priorität; oben steht, wie viele noch warten.
- **Das Original kommt in den Papierkorb** und lässt sich bis zum Ablauf der Frist wiederherstellen. Der Eintrag behält Personen, Schlagworte, Ort, Datum und erkannte Gesichter; die Metadaten werden in die neue Datei übernommen.
- Wird eine Datei während des Umwandelns bearbeitet, wird sie danach erneut umgewandelt, damit nichts verloren geht.
- Schlägt etwas fehl, bleibt das Original unverändert; der Grund steht im Protokoll des Add-ons.
- **Einschränkung:** HDR-Videos (iPhone „HDR-Video") verlieren beim Umwandeln ihr HDR und können etwas blasser wirken.

## Papierkorb

Gelöschte Dateien werden nach `.papierkorb` in der Bibliothek verschoben. Der Ordner beginnt mit einem Punkt und ist deshalb im HA-Medienbrowser nicht sichtbar. Über das Papierkorb-Symbol oben rechts lassen sich Dateien wiederherstellen oder endgültig löschen. Nach `trash_days` Tagen löscht das Add-on sie automatisch.

Eine Datei im Papierkorb gilt beim Import weiterhin als vorhanden. Sie wird also als Duplikat erkannt.

## Hintergrundaufgaben

Mehrfachaktionen, Umbenennen und Zusammenführen von Personen, *Papierkorb leeren* und *Fehlende Einträge entfernen* laufen im Hintergrund, der Fortschritt steht unten. Die Aufgaben stehen in der Datenbank. Wird das Add-on mittendrin neu gestartet oder aktualisiert, laufen sie danach an derselben Stelle weiter.

Das Foto, das beim Neustart gerade in Arbeit war, wird wiederholt. Ausnahme ist das **Drehen**: Ein Foto doppelt zu drehen wäre falsch. Dieses eine Foto erscheint deshalb im Bericht als *„Durch einen Neustart unterbrochen – bitte prüfen“*.

Import und Abgleich sind keine solchen Aufgaben. Sie werden nach einem Neustart einfach erneut gestartet, bereits verarbeitete Dateien überspringen sie.

## Aufnahmedatum

Das Datum wird in dieser Reihenfolge bestimmt:

1. EXIF/XMP `DateTimeOriginal` bzw. bei Videos `CreationDate` (Ortszeit)
2. QuickTime `CreateDate` (UTC, wird in die Zeitzone von Home Assistant umgerechnet)
3. Datum im Dateinamen, z. B. `IMG_20190512_140322.jpg` oder `WhatsApp Image 2019-05-12 at 14.03.22.jpeg`
4. Änderungsdatum der Datei. Dieses Datum wird in der Einzelansicht als **unsicher** markiert.

## Speicherplatz und Backups

**Große Dateien finden:** Das Datenbank-Symbol oben rechts öffnet die Ansicht **Speicherplatz**. Sie listet die Dateien nach Größe, mit Größe, Datum, Dauer und Auflösung. Oben wählst du *Alle*, *Videos* oder *Fotos*, eine Mindestgröße und unter *Reihenfolge*, ob die **größten** oder die **kleinsten** Dateien zuerst kommen; daneben steht, wie viel Platz diese Auswahl zusammen belegt. Antippen öffnet die Datei, der Kreis links wählt sie aus (Shift + Klick wählt einen Bereich). **In den Papierkorb** verschiebt die Auswahl, der Platz wird erst frei, wenn der Papierkorb geleert wird oder die Frist abläuft.

**Kleine Dateien finden:** *Reihenfolge → Kleinste zuerst* dreht die Liste um. Das zeigt, was sich beim Aufräumen sonst nicht zeigt: versehentlich importierte Vorschaubilder und Symbole, WhatsApp-Kopien statt der Originale und Videoschnipsel von wenigen Sekunden. Die Mindestgröße bleibt dabei wirksam – für die kleinsten Dateien überhaupt also auf *alle* stellen.

- Die Datenbank, die Vorschaubilder und die Gesichtsausschnitte liegen im Add-on-Datenordner. Pro Bild braucht das etwa 30–40 KB, dazu etwa 6 KB für die kleine Vorschau. Die kleine Vorschau entsteht erst, wenn ein Bild zum ersten Mal in einer kleinen Zoomstufe angezeigt wird.
- **Vorschaubilder sind vom Add-on-Backup ausgenommen.** Sie werden bei Bedarf neu erzeugt.
- ⚠️ **Eine vollständige Home-Assistant-Sicherung enthält auch den Ordner `/media`, also das ganze Fotoarchiv.** Bei großen Sammlungen solltest du `media` in den Backup-Einstellungen abwählen und die Fotos separat sichern, z. B. auf ein NAS.

## Zugriff übers Internet

Über Home Assistant (Seitenleiste) hast du immer volle Rechte. Für den Zugriff von unterwegs gibt es einen **eigenen Internetzugang** mit eigenen Konten.

### Einrichten

1. In den Add-on-Einstellungen `public_enabled: true` setzen und das Add-on neu starten.
2. In der Oberfläche auf das **Schild-Symbol** klicken und Konten anlegen:
   - **Ansehen:** Fotos, Karte und Personen ansehen und Originale herunterladen.
   - **Hochladen + Bearbeiten (ohne Löschen):** zusätzlich hochladen, Schlagworte, Personen, Orte und Datum ändern, drehen und Gesichter benennen. Bilder löschen geht nicht: kein Papierkorb, kein Wiederherstellen, keine Duplikat-Bereinigung.
   - **Bearbeiten:** zusätzlich hochladen, Datum, Ort, Schlagworte und Personen ändern, drehen, in den Papierkorb legen und Gesichter benennen.
   - Import, Abgleich, endgültiges Löschen und die Kontenverwaltung gibt es nur über Home Assistant.
   - **Löschen vorschlagen:** Wer nicht löschen darf, findet in der Einzelansicht und in der Auswahl den Knopf *Löschen vorschlagen*, auf Wunsch mit Grund. In Home Assistant zeigt ein Symbol mit Zahl oben rechts die offenen Vorschläge. Es öffnet die Ansicht **Löschvorschläge**: Fotos auswählen und in den Papierkorb legen oder *Ablehnen*. In der Einzelansicht steht, wer das Löschen vorgeschlagen hat und warum; auch dort lässt sich direkt entscheiden.
3. Den Internetzugang über deinen Reverse Proxy mit TLS veröffentlichen, siehe unten. **Port 8301 nie direkt im Router freigeben.**

### Nginx Proxy Manager (Add-on)

- **Forward Hostname:** der Hostname des Fotoarchiv-Add-ons, zu finden unter *Einstellungen → Add-ons → Fotoarchiv → Info*. Er sieht etwa so aus: `a1b2c3d4-fotoarchiv`.
- **Forward Port:** `8301`, Schema `http`
- **SSL:** Zertifikat anfordern, *Force SSL* und *HSTS* aktivieren
- **Große Uploads:** Unter *Advanced* `client_max_body_size 0;` eintragen

Das Add-on NPM liegt im internen Home-Assistant-Netz `172.30.32.0/23` und ist damit schon als vertrauenswürdiger Proxy eingetragen.

### Cloudflare Tunnel

Als Dienst `http://a1b2c3d4-fotoarchiv:8301` angeben, mit dem Hostnamen wie oben. Die Besucheradresse übernimmt das Add-on aus `CF-Connecting-IP`. Cloudflare begrenzt Uploads im kostenlosen Tarif auf 100 MB pro Datei.

WAF-Regeln, die Pfade mit `/login` per *Managed Challenge* schützen, blockieren die Anmeldung: Der Browser kann die Abfrage bei der Anmeldung im Hintergrund nicht lösen. `/api/auth/login` für den Fotoarchiv-Hostnamen in der Regel ausnehmen, zum Beispiel mit `and not (http.host eq "foto.example.org" and http.request.uri.path eq "/api/auth/login")`. Das Add-on sperrt Fehlversuche selbst.

### Port ändern

Der Internetzugang ist im Heimnetz unter `http://<Home-Assistant-IP>:8301` erreichbar. Den Port stellst du unter *Einstellungen → Add-ons → Fotoarchiv → Konfiguration → Netzwerk* ein. Ein leeres Feld schaltet die Freigabe ab; dann erreicht ihn nur noch ein Proxy im Home-Assistant-Netz über den Add-on-Hostnamen, z. B. `http://a1b2c3d4-fotoarchiv:8301`. Zeigt dein Proxy auf die IP von Home Assistant, muss dort derselbe Port eingetragen sein, sonst meldet er 502 Bad Gateway.

Anmelden lässt sich nur über HTTPS, solange `public_cookie_secure` an ist. Über `http://…:8301` im Heimnetz klappt die Anmeldung also nicht, dafür ist der Weg über den Proxy da.

### Proxy auf einem anderen Gerät

Den Host-Port wie oben eintragen und die Adresse des Proxy-Geräts unter `public_trusted_proxies` ergänzen.

### Schutz

- **Fehlversuche:** Nach 10 Fehlversuchen innerhalb von 15 Minuten wird das **Konto** gesperrt, auch wenn die Versuche von verschiedenen Adressen kommen. Die **Adresse** wird erst nach 30 Fehlversuchen gesperrt: Zu Hause teilt sich die ganze Familie eine IP, und eine Adresssperre trifft alle. Eine Sperre lässt sich unter *Zugang übers Internet → Sitzungen & Sperren* sofort aufheben. Die erste Sperre dauert 15 Minuten, jede weitere doppelt so lange, höchstens 24 Stunden.
- **Scanner:** Wer ohne Anmeldung wiederholt die API oder unbekannte Pfade aufruft, wird ebenfalls gesperrt.
- **Anfragen:** Pro Adresse ist die Zahl der Anfragen pro Minute begrenzt.
- **Proxy-Angaben:** Die Besucheradresse aus `X-Forwarded-For` bzw. `CF-Connecting-IP` wird **nur** von Adressen aus `public_trusted_proxies` übernommen. Gefälschte Angaben bei direktem Zugriff bleiben wirkungslos.
- **Sitzungen:** Sie werden auf dem Server geführt. Das Cookie ist `HttpOnly`, `Secure` und `SameSite=Lax`. Ändernde Anfragen brauchen zusätzlich ein CSRF-Token.
- **Passwörter:** Sie werden mit scrypt gespeichert, mindestens 10 Zeichen. Ein neues Passwort oder das Deaktivieren eines Kontos beendet sofort alle seine Sitzungen.
- **Eigenes Passwort:** Jede angemeldete Person kann ihr Passwort über das Schloss-Symbol oben rechts selbst ändern. Dafür braucht sie das bisherige Passwort. Falsche Eingaben zählen wie fehlgeschlagene Anmeldungen und führen zur selben Sperre. Die eigene Sitzung bleibt bestehen, alle anderen Geräte werden abgemeldet.
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
- **Ein Bild zeigt nur ein durchgestrichenes Bildsymbol:** Das Vorschaubild konnte nicht erzeugt werden. Genaueres steht im Protokoll des Add-ons („Vorschaubild für … fehlgeschlagen“). Neu versucht wird nach einer Stunde oder sobald die Datei bearbeitet wird.
- **Ein Video lässt sich nicht abspielen, obwohl es ein MP4 ist:** Die Endung verrät nur den Container, nicht den Codec darin. Neuere Handys nehmen oft in H.265/HEVC auf, das die meisten Browser nicht abspielen können. Das Vorschaubild erscheint trotzdem, weil ffmpeg den Codec lesen kann. Die Einzelansicht zeigt dann einen Hinweis; das Original lässt sich herunterladen und lokal abspielen.
- **Datei landet in `_defekt` im Import-Ordner:** Sie ist beschädigt, meist weil das Kopieren oder Hochladen abgebrochen ist (bei Videos: „Video unvollständig“, das Inhaltsverzeichnis am Dateiende fehlt). Die Datei noch einmal vom Original kopieren. Abgebrochene Uploads über den Browser werden ebenfalls abgelehnt.
- **Beschädigte Dateien schon im Archiv finden:** *Speicherplatz* → *Beschädigt* listet alles, woraus sich kein Vorschaubild erzeugen ließ. Gibt es das Original noch, die Einträge löschen und das Original neu importieren. Bei abgeschnittenen Videos ohne Original kann das Werkzeug `untrunc` den vorhandenen Teil oft retten (es braucht dafür ein heiles Video vom selben Gerät).
- **Dateien bleiben im Import-Ordner liegen:** Den Bericht im Import-Fenster unter „Fehler“ und „Übersprungen“ prüfen. Dateien, die beim Start noch kopiert wurden oder sich in der letzten Minute geändert haben, werden übersprungen und beim nächsten Import übernommen. Große Videos also erst fertig kopieren lassen, dann importieren – oder einfach später noch einmal auf *Import starten* tippen.
