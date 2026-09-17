# Changelog

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
