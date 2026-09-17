# Changelog

## 0.09

- Personen zusammenführen: eigener Knopf im Personen-Dialog mit Auswahlliste, Vorschau („3 Fotos von Anna werden zu Anna Müller“) und Bestätigung; Umbenennen auf einen vorhandenen Namen fragt ebenfalls nach
- Hintergrundaufgaben (Mehrfachaktionen, Umbenennen, Zusammenführen, Papierkorb leeren, fehlende Einträge entfernen) stehen in der Datenbank und laufen nach Neustart oder Update weiter
- Ein durch Neustart unterbrochenes Foto wird wiederholt – beim Drehen nicht, dann steht es als „bitte prüfen“ im Bericht

## 0.08

- Internetzugang auf eigenem Port 8301 (Option `public_enabled`), gedacht hinter einem Reverse Proxy mit TLS
- Konten mit Rollen „Ansehen“ und „Bearbeiten“; Verwaltung, Import, Abgleich und endgültiges Löschen bleiben Home Assistant vorbehalten
- Schutz wie in Simple NAS: 10 Fehlversuche je Adresse oder Konto in 15 Minuten → Sperre 15 min, bei Wiederholung doppelt so lang (max. 24 h); Scanner-Sperre; Begrenzung der Anfragen je Adresse
- Vertrauenswürdige Proxys (`public_trusted_proxies`): X-Forwarded-For und CF-Connecting-IP werden nur von dort übernommen
- Sitzungen serverseitig (Kennung nur als Hash gespeichert), HttpOnly/Secure/SameSite-Cookie, CSRF-Schutz, Sicherheits-Header (CSP, HSTS, Frame-Verbot)
- Passwörter mit scrypt; neues Passwort oder Sperren eines Kontos beendet alle seine Sitzungen
- Verwaltung (Schild-Symbol): Konten, aktive Sitzungen, Sperren aufheben, Zugriffsprotokoll
- CrowdSec: Zugriffsprotokoll als JSON, Parser und Szenarien, Einrichtung per Klick
- Anmeldeseite; die Oberfläche blendet Funktionen ohne Berechtigung aus

## 0.07

- Gesichtserkennung (InsightFace buffalo_l: SCRFD + ArcFace über onnxruntime), läuft im Hintergrund, neueste Fotos zuerst
- Neue Ansicht „Personen“: bekannte Personen und Gruppen unbekannter Gesichter, Fortschrittsanzeige
- Gruppe benennen (einzelne falsche Gesichter vorher abwählbar) oder ausblenden; gleicher Name führt zusammen
- Namen werden als Person in die Fotos geschrieben (XMP PersonInImage), auch automatisch erkannte
- Neue Fotos derselben Person werden automatisch zugeordnet; nach dem Benennen lernt das System passende Gruppen dazu
- Person umbenennen (schreibt in alle Fotos), Gesicht lösen („nicht diese Person“, wird nicht wieder vorgeschlagen)
- Einzelansicht: Gesichtsrahmen (Taste f) mit Benennen direkt am Gesicht
- Vorhandene Personen aus den Metadaten werden verknüpft, wenn ein Foto genau ein Gesicht und eine Person hat
- Option `face_recognition` zum Abschalten; Modelle (ca. 280 MB) werden beim ersten Start geladen und per SHA-256 geprüft

## 0.06

- Galerie zoomen: 5 Stufen (Zeilenhöhe 80–300 px) über Plus/Minus unten links, Strg + Mausrad, Touchpad-Geste oder Zusammenziehen mit zwei Fingern
- Die kleinsten zwei Stufen gruppieren nach Monat statt nach Tag
- Kleine Vorschaubilder (160 px), sobald sie scharf genug sind; werden beim ersten Anzeigen aus dem normalen Vorschaubild erzeugt
- Zoomstufe wird pro Gerät gemerkt, das oberste Foto bleibt beim Zoomen stehen

## 0.05

- „Bibliothek einlesen“ heißt jetzt „Bibliothek abgleichen“ und gleicht das Archiv mit dem Datenträger ab:
  - von Hand verschobene oder umbenannte Dateien werden über die MD5-Summe ihrem Eintrag wieder zugeordnet (Schlagworte, Personen und ID bleiben)
  - Einträge, deren Datei fehlt, werden aufgelistet und lassen sich nach Bestätigung entfernen
  - Schutz: Ist die Bibliothek leer oder nicht erreichbar (Laufwerk nicht eingebunden), wird nichts entfernt
- Wird eine von Hand gelöschte Datei erneut importiert oder hochgeladen, übernimmt sie ihren alten Eintrag, statt als Duplikat abgewiesen zu werden
- Beim Wieder-Zuordnen bleibt ein verlässlicheres Datum erhalten (z. B. aus dem alten Dateinamen)

## 0.04

- Fehler behoben: Karte zeigte in Home Assistant nur „Access blocked“. HA sendet `Referrer-Policy: no-referrer`, OpenStreetMap verlangt aber einen Referer. Kacheln und Ortssuche schicken jetzt nur den Ursprung (ohne Pfad oder Ingress-Token) mit.

## 0.03

- Weltkarte (OpenStreetMap) mit gruppierten Fotos: Titelbild und Anzahl je Gruppe, Klick zoomt hinein oder öffnet die Fotos
- Fenster „Ohne Ort“: Fotos einzeln oder als Auswahl auf die Karte ziehen (Maus sofort, Touch nach langem Drücken), mit Rückgängig
- Ortssuche auf der Karte (OpenStreetMap Nominatim)
- Einzelansicht: Ort setzen oder ändern über eine Karte mit verschiebbarer Stecknadel
- Karte berücksichtigt die Suchfilter
- API: `/api/geo`, Filter `located` und `editable`, Mehrfachaktion `location`

## 0.02

- Suche nach Personen, Schlagworten, Zeitraum und Freitext
- Bearbeiten direkt in der Datei (exiftool): Datum, Personen, Schlagworte, Ort entfernen
- Drehen verlustfrei über EXIF-Orientierung bzw. Video-Rotation (nicht bei HEIC/AVIF)
- Mehrfachauswahl (Häkchen, Shift-Bereich, ganzer Tag, Strg+A, langes Drücken) mit Aktionen im Hintergrund und Fortschritt
- Papierkorb mit Wiederherstellen, Rückgängig, endgültig löschen und automatischer Bereinigung (Option `trash_days`)
- Datei wird nach Datumsänderung in den passenden Monatsordner verschoben
- Fehler behoben: libvips lieferte nach dem Bearbeiten veraltete Vorschaubilder aus seinem Cache

## 0.01

- Erste Version
- Import aus Samba-Ordner mit Fortschritt und Bericht, Einlesen einer bestehenden Bibliothek
- Upload per Drag & Drop (auch ganze Ordner)
- Duplikaterkennung per MD5, auch nach späterer Bearbeitung einer Datei
- Einsortieren nach Aufnahmedatum (EXIF, QuickTime, Dateiname, Dateidatum)
- Galerie mit Tagesgruppen und Zeitleiste zum Ziehen
- Einzelansicht mit Metadaten, Videos und Download
- Fotos (JPEG, HEIC, PNG, WebP, …) und Videos (MP4, MOV, …)
