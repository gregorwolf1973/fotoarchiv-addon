# Changelog

## 0.23

- Fängt Cloudflare eine Anfrage mit einer Sicherheitsabfrage ab (etwa eine WAF-Regel auf `/login`), nennt die Oberfläche das jetzt klar statt nur „Forbidden“
- Doku: WAF-Regeln für den Login-Pfad

## 0.22

- Port 8301 für den Internetzugang ist ab Werk am Host freigegeben und unter *Konfiguration → Netzwerk* einstellbar – vorher war er leer, und ein Proxy, der auf die IP von Home Assistant zeigt, meldete 502 Bad Gateway
- Doku: Abschnitt „Port ändern“

## 0.21

- Karte: Fotos werden jetzt bis zur höchsten Zoomstufe gebündelt und überlappen sich nicht mehr – vorher lagen sie ab Zoom 18 als Haufen übereinander
- Hinweis „Datei ließ sich nicht umwandeln“ nennt Dateiname und Grund direkt (das Protokoll ist nach einem Neustart leer) und lässt sich mit dem **X** ausblenden
- Ort, Datum und Schlagworte lassen sich auch in Videos mit Anhang am Dateiende schreiben (etwa Samsungs SEF-Anhang, exiftool meldete „Possible garbage at end of file“); der Anhang entfällt dabei, das Video bleibt unverändert

## 0.20

- Speicherplatz: neue Auswahl **Reihenfolge** – neben den größten Dateien lassen sich jetzt auch die kleinsten zuerst anzeigen
- Nützlich, um versehentlich importierte Vorschaubilder, Symbole und Videoschnipsel zu finden; die Mindestgröße wirkt dabei weiter, für die kleinsten Dateien also auf „alle“ stellen

## 0.19

- Große Importe schneller: Die Prüfung auf beschädigte Dateien läuft erst nach der Duplikatprüfung, Duplikate kosten also keinen ffprobe-Lauf mehr
- Die Dateisuche betritt `_duplikate`, `_defekt` und versteckte Ordner nicht mehr und liest den Dateityp aus dem Verzeichnis statt jede Datei einzeln abzufragen – bei Hunderttausenden Dateien spürbar schneller
- Während der Suche zeigt das Import-Fenster, wie viele Dateien schon gefunden sind, statt minutenlang „0 von 0“

## 0.18

- Bibliothek abgleichen mit **gründlicher Prüfung** (Häkchen im Import-Fenster): jede Datei wird vollständig gelesen – Fotos ganz dekodiert, Videos mit ffprobe – und mit der gespeicherten Prüfsumme verglichen
- Findet abgeschnittene JPEGs mit heilem Kopf (daraus entstand bisher still ein halb graues Vorschaubild) und Dateien, die auf dem Datenträger kaputtgegangen oder außerhalb verändert wurden
- Befunde werden gespeichert und unter Speicherplatz → Beschädigt mit Grund angezeigt; im Bericht neue Listen „Beschädigt“ und „Außerhalb verändert“
- Die Prüfung lässt sich abbrechen

## 0.17

- Behoben: Der Import konnte Dateien übernehmen, die per Samba noch kopiert wurden. Weil Import-Ordner (`/share`) und Bibliothek (`/media`) in Home Assistant getrennt eingehängt sind, wird dabei kopiert statt umbenannt – das Addon kopierte einen halben Stand und löschte danach das Original. So entstanden abgeschnittene Videos („moov atom not found“)
- Dateien, die sich in der letzten Minute geändert haben, gelten als „wird noch kopiert“ und kommen beim nächsten Import dran
- Beim Kopieren zwischen Import-Ordner und Bibliothek wird geprüft, ob sich das Original währenddessen verändert hat; dann bleibt es liegen und nichts wird gelöscht

## 0.16

- Beschädigte Dateien kommen nicht mehr ins Archiv: Beim Import wird geprüft, ob sich ein Foto öffnen bzw. ein Video lesen lässt. Halbe Dateien (abgebrochen kopiert) landen in `_defekt` im Import-Ordner und stehen im Bericht unter „Beschädigt“
- Uploads werden auf Vollständigkeit geprüft: Kommen weniger Bytes an als angekündigt, wird die Datei abgelehnt statt halb gespeichert
- Speicherplatz: neuer Filter „Beschädigt“ zeigt Dateien, aus denen sich kein Vorschaubild erzeugen ließ
- Ursache war ein Fund im Protokoll: 27 abgeschnittene Videos und Fotos, bei denen ffmpeg „moov atom not found“ meldete

## 0.15

- Umwandeln: HEIC → JPEG, nicht abspielbare Videos (H.265/HEVC, 10 Bit, alte Formate) → H.264-MP4, MOV mit H.264 wird verlustfrei zu MP4 umgepackt
- Knopf „Umwandeln“ in der Auswahlleiste und in der Ansicht „Speicherplatz“ (nur über Home Assistant), mit Rückfrage
- Neue Option `convert_on_import` (Standard aus): neue Dateien gleich beim Import umwandeln
- Das Original kommt in den Papierkorb, der Eintrag behält Personen, Schlagworte, Ort und Gesichter; umgewandelt wird im Hintergrund mit niedriger Priorität, der Fortschritt steht oben
- Hinweis bei nicht abspielbaren Videos verweist auf „Umwandeln“

## 0.14

- Einzelansicht zoomen: Mausrad, Doppelklick, Tasten + / − / 0, am Touchscreen zwei Finger und Doppeltippen, bis 8-fach. Vergrößert lässt sich das Foto verschieben, ungezoomt blättert Wischen wie bisher
- Beim Hineinzoomen wird das Original in voller Auflösung nachgeladen (nicht bei HEIC/TIFF, die der Browser nicht anzeigen kann)
- Fenster „Wer ist das?“: Der Umschalter für ganze Fotos sitzt jetzt neben dem Schließen-Knopf
- Speicherplatz: Abstände in der Detailzeile korrigiert

## 0.13

- Neue Ansicht „Speicherplatz“ (Datenbank-Symbol oben rechts): die größten Dateien zuerst, Filter nach Videos/Fotos und Mindestgröße, Summe der Auswahl, Mehrfachauswahl mit Shift-Bereich und Löschen in den Papierkorb
- API: `/api/largest`

## 0.12

- Personen entfernen: neuer Knopf im Personen-Dialog. Der Name wird aus allen Fotos genommen, erkannte Gesichter werden wieder unbekannt
- Behoben: Personen aus Gesichtsmarkierungen anderer Programme (Picasa, Google Fotos, Lightroom, Windows-Fotogalerie) ließen sich weder umbenennen noch entfernen. Beim Umbenennen standen danach sogar beide Namen im Foto. Jetzt werden die fremden Markierungen der betroffenen Datei entfernt, alle übrigen Namen bleiben erhalten
- Personen ohne erkannte Gesichter zeigen im Dialog einige ihrer Fotos

## 0.11

- Ort für viele Fotos auf einmal setzen: neuer Knopf in der Auswahlleiste, neben dem Datum
- Unbekannte Gesichter: Das Bilder-Symbol im Fenster „Wer ist das?“ zeigt die ganzen Fotos statt nur der Gesichtsausschnitte, mit Datum und dem gemeinten Gesicht in der Ecke. Die Ansicht wird gemerkt
- Videos, die der Browser nicht abspielen kann (meist H.265/HEVC), zeigen jetzt einen Hinweis mit Download-Knopf statt eines stummen Standbilds
- Videos starten nicht mehr von selbst: Der Autostart wurde von Browsern mit Ton ohnehin blockiert
- Neue Option `face_threads`: Prozessorkerne für die Gesichtserkennung (bisher fest 2)
- Behoben: Fotos, deren Vorschaubild sich nicht erzeugen lässt, konnten eine Sperre durch CrowdSec auslösen. Beim Scrollen kam für jedes eine 404-Antwort, und eine solche Serie sieht wie ein Scanner aus (Szenario `http-probing`). Jetzt kommt ein Ersatzbild, und ein gescheitertes Vorschaubild wird erst nach einer Stunde oder nach einer Änderung an der Datei neu versucht

## 0.10

- Doppelte und sehr ähnliche Fotos finden: Wahrnehmungs-Hash im Hintergrund, eigene Ansicht „Doppelte Fotos“ mit den Listen „Doppelt“ (verkleinert, neu gespeichert, anderes Format) und „Serien“ (ähnlich, innerhalb von 30 Sekunden)
- Beste Fassung wird vorgeschlagen (Auflösung, Datum, Metadaten, Größe), Auswahl je Foto änderbar, Rest in den Papierkorb, einzeln oder alle Vorschläge auf einmal
- Optional werden Schlagworte, Personen, Ort und ein verlässlicheres Datum vorher aufs behaltene Foto übertragen
- „Keine Duplikate“ merkt sich Gruppen, die nicht wieder vorgeschlagen werden sollen
- Import und Upload weisen auf Fotos hin, die einem vorhandenen sehr ähnlich sind
- Neue Option `duplicate_detection` zum Abschalten
- Behoben: Nach einem Neuaufbau der Datenbank konnte der Browser alte Vorschaubilder aus dem Cache zeigen

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
