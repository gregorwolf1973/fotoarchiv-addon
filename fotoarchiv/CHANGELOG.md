# Changelog

## 0.57

- **Manuell gedrehte Fotos bleiben so:** Was jemand von Hand dreht, prüft die Bilderkennung nicht mehr und dreht es auch nicht zurück. Bekannt sind alle Drehungen ab jetzt; von früher nur die Mehrfach-Drehungen, die noch im Aufgabenverlauf stehen
- **Einstellungen** (Zahnrad oben rechts, nur in Home Assistant): Stand der Bilderkennung, *Alle prüfen, auch die manuell gedrehten* und *Alle Informationen in die Bilder schreiben*
- **Alle Informationen in die Bilder schreiben:** offene Schlagwort-Vorschläge, noch nicht geschriebene Personennamen und Angaben aus Begleitdateien kommen in die Dateien. Läuft als Hintergrundaufgabe und schreibt nur, was fehlt
- **Behoben:** Bei Fotos mit Begleitdatei (Google-Takeout-JSON, XMP) fielen Datum, Ort, Personen und Schlagworte daraus nach jeder Änderung aus der Datenbank – auch nach dem Drehen. Jetzt kommen diese Angaben vor der ersten Änderung in die Datei selbst

## 0.56

- **Bilderkennung** (neu, abschaltbar mit `image_recognition`). Sie lädt beim ersten Start ihre Modelle (ca. 1,6 GB) und geht im Hintergrund alle Fotos und Videos durch. Die Gesichtserkennung hat Vorrang. Siehe *Bilderkennung* in der Dokumentation
- **Suche in normaler Sprache:** Im Suchfeld beschreiben, was auf dem Foto ist, etwa „Hund am Strand“ oder „Weihnachtsbaum“, dann *Fotos von „…“* wählen. Die Suche versteht auch Deutsch, lässt sich mit allen Filtern kombinieren und gilt auch auf der Karte
- **Schlagwort-Vorschläge** für gut 50 häufige Motive. Sie stehen nur in der Datenbank, bis jemand sie übernimmt: einzeln in der Einzelansicht (✓/✕) oder für alle Treffer eines Vorschlags über die Leiste über der Galerie. Abgelehnte kommen nicht wieder
- **Falsch gedrehte Fotos:** Eindeutige Fälle dreht das Add-on selbst, wenn das Modell sich einig ist und ein Gesicht die neue Lage bestätigt (abschaltbar mit `auto_rotate`). Verdachtsfälle ohne diese Bestätigung kommen in die neue Liste **Drehen prüfen** (Drehen-Symbol mit Zahl oben rechts). Dort zeigt sich jedes Foto schon gedreht: Falsche antippen, dann *Übernehmen*. Automatisch gedrehte lassen sich dort und in der Einzelansicht rückgängig machen
- Die Modelle laufen in einem eigenen Prozess mit niedriger Priorität und geben ihren Speicher nach einigen Minuten ohne Arbeit wieder frei

## 0.55

- **Fotos mit Video-Endung:** Manche Kopien alter Handys tragen *.mp4*, obwohl ein JPEG darin steckt. Solche Dateien erkennt das Fotoarchiv jetzt am Inhalt statt am Namen. Beim Import werden sie gleich mit der richtigen Endung als Foto einsortiert. Liegen sie schon im Archiv, benennt *Umwandeln* sie nur um (*.jpg*, *.png* …) und führt sie ab dann als Foto, mit Vorschaubild, Gesichtserkennung und Duplikatsuche. Bisher machte *Umwandeln* daraus ein Video aus einem einzigen Bild. Der Inhalt bleibt Byte für Byte gleich, deshalb kommt nichts in den Papierkorb
- Taucht die Datei eines Eintrags unter neuem Namen wieder auf, übernimmt der Eintrag auch die Art (Foto oder Video), die zur neuen Endung passt
- **Umwandeln alter AVIs:** Manche AVIs geben im Dateikopf eine zu kurze Länge an, zum Beispiel 13,8 s, obwohl die Bilder bis 15,1 s reichen. Die Prüfung nach dem Umwandeln lehnte das vollständige Ergebnis deshalb mit *Länge passt nicht* ab. Jetzt zählt in diesem Fall, wie weit die Bilder im Original wirklich reichen

## 0.54

- **Zuletzt eingelesen:** Neuer Punkt **Neu** in der Kopfzeile. Er zeigt alle Fotos nach dem Tag, an dem sie ins Archiv kamen, das Neueste oben – auch ein Foto von 2015, das heute importiert wurde, steht ganz oben. Nach einem Import mit neuen Fotos führt *Eingelesene ansehen* im Import-Fenster direkt dorthin
- **Auswahl herunterladen:** Neuer Knopf (Pfeil nach unten) in der Auswahlleiste. Ein Foto kommt als Original, mehrere als ein ZIP mit den Originalen, bis zu 5000 auf einmal. Das ZIP wird beim Herunterladen zusammengestellt, ohne Zwischendatei und unkomprimiert (Fotos und Videos sind es schon), gleichnamige Dateien heißen darin *(2)*, *(3)* … Über den Internetzugang gilt ein Download nur für das Konto, das ihn angefordert hat

## 0.53

- **Automatischer Import wartet, bis die Kopie fertig ist:** Er beginnt erst, wenn sich im ganzen Import-Ordner eine Minute lang nichts mehr geändert hat. Bisher zählte jede Datei für sich, und weil Kopierprogramme am Ende das alte Datum einer Datei setzen, wirkte ein eben kopiertes Foto sofort fertig. Der Import lief dann mitten in die Kopie hinein: Fotos aus Google Takeout kamen ohne ihre JSON-Begleitdatei ins Archiv (also ohne Datum und Ort daraus), eine gerade geschriebene JSON wurde mit ihrem doppelten Foto gelöscht, und die Kopie brach ab. Jeder neue Versuch meldete dann, dass der Ordner schon existiert
- Auch beim Knopf *Import starten* gilt eine Datei erst nach einer Minute ohne jede Änderung als fertig kopiert. Dafür zählt jetzt auch der Zeitpunkt der letzten Änderung am Dateieintrag (ctime), den kein Kopierprogramm zurücksetzen kann
- Leere Ordner im Import-Ordner räumt der Import nur noch weg, wenn er sie selbst geleert hat oder sich eine Minute lang nichts in ihnen getan hat. Einen Ordner, den eine laufende Kopie gerade angelegt hat, lässt er stehen
- Eine JSON-Begleitdatei, die gerade geschrieben wird, bleibt liegen, wenn ihr doppeltes Foto gelöscht wird

## 0.52

- **Favoritenordner:** Unter **Favoriten** eigene Ordner anlegen, umbenennen und löschen. Ein Ordner enthält nur Verweise auf Fotos – die Dateien bleiben, wo sie sind, und ein Foto kann in mehreren Ordnern stecken
- **Drag & Drop:** Am Computer steht links neben der Galerie eine Leiste mit den Ordnern; Fotos (oder die ganze Auswahl) einfach auf einen Ordner ziehen. Doppelklick auf einen Ordner benennt ihn um
- Am Handy: Fotos auswählen und auf den **Stern** tippen, dann Ordner wählen oder neu anlegen
- Im Ordner nimmt *Aus Ordner entfernen* bzw. `Entf` ein Foto nur aus dem Ordner; das Foto bleibt im Archiv
- Beim Aussortieren doppelter Fotos übernimmt das behaltene Foto die Favoritenordner des gelöschten

## 0.51

- **Hochladen vom Handy robuster:** Fotos unter 32 MB wurden bisher in einem Rutsch und ohne zweiten Versuch hochgeladen – ein kurzer Verbindungsabbruch, eine Fehlerseite des Proxys oder eine halb angekommene Datei endete sofort als *Fehler*. Jetzt gibt es wie bei großen Dateien bis zu sechs weitere Versuche. War eine Datei doch schon angekommen, meldet der nächste Versuch sie als vorhanden; doppelt ins Archiv kommt nichts
- Die Upload-Liste zeigt den **Grund** für *Fehler*, *beschädigt* und *übersprungen* direkt unter dem Dateinamen (am Handy gab es nur einen Tooltip, also gar nichts). Statt eines leeren Textes steht dort jetzt der Statuscode bzw. *Netzwerkfehler*
- **Erneut versuchen:** Nach dem Hochladen schickt ein Knopf alle fehlgeschlagenen Dateien noch einmal, ohne sie neu auswählen zu müssen
- Nicht importierte Uploads stehen jetzt mit Grund im Log des Add-ons – bisher sah das Ergebnis nur der Browser, der hochgeladen hat
- **Log:** pyvips schrieb jede Info von libvips mit, rund ein Dutzend Zeilen je Vorschaubild. Dadurch verschwanden echte Fehlermeldungen nach wenigen Minuten aus dem Log. Warnungen und Fehler von libvips erscheinen weiterhin
- Vorschaubilder: Erzeugten Import und Galerie dasselbe Vorschaubild gleichzeitig, scheiterte einer der beiden mit *No such file or directory* (gemeinsame Zwischendatei). Jeder Aufruf hat jetzt seine eigene

## 0.50

- **JSON-Begleitdateien aus Cloud-Exporten** werden beim Import gelesen: Google Takeout (`bild.jpg.json`, `bild.jpg.supplemental-metadata.json`, auch gekürzt), Mi Cloud, Samsung Cloud und andere (`bild.json`). Aufnahmezeitpunkt, Ort, Personen und Schlagworte daraus landen im Eintrag; das Datum zählt wie ein Kameradatum und schlägt damit den Dateinamen. Was in der Datei selbst steht, hat weiterhin Vorrang
- Die JSON wandert wie eine XMP-Begleitdatei mit ins Archiv (dort einheitlich als `bild.jpg.json`), in den Papierkorb und zurück; beim Umwandeln werden ihre Angaben in die neue Datei geschrieben
- Bisher blieben solche JSON-Dateien im Import-Ordner liegen und wurden als *Dateityp wird nicht unterstützt* gezählt

## 0.49

- **XMP-Begleitdateien** werden ausgewertet: Liegt neben `video.avi` eine `video.avi.xmp`, kommen Aufnahmedatum, Ort, Schlagworte, Personen und Kamera daraus in den Eintrag. AVI, MPG und WMV können selbst nichts speichern – dort ist das die einzige Quelle. Was in der Datei selbst steht, hat weiterhin Vorrang
- Die Begleitdatei wandert mit: ins Archiv, in den Papierkorb, zurück beim Wiederherstellen, und beim endgültigen Löschen geht sie mit. Beim Umwandeln nach MP4 werden ihre Angaben in die neue Datei geschrieben
- Begleitdateien werden im Import-Bericht nicht mehr als *Dateityp wird nicht unterstützt* gezählt

## 0.48

- Doppelte Fotos: Die Strenge des Vergleichs ist jetzt einstellbar – `duplicate_bits` (Standard 6, Bereich 1–7) für die Liste *Doppelt* und `series_bits` (Standard 12, Bereich 1–24) für *Serien*. Landet zu viel bloß Ähnliches unter *Doppelt*, sorgt 4 oder 5 für eine strengere Liste. Wirkt nach einem Neustart des Add-ons, die Fingerabdrücke bleiben erhalten

## 0.47

- Karte: Das Ziehen von Fotos mit der Maus ist wieder weg, es war zu fehleranfällig. Verschoben wird nur noch über das Rechtsklick-Menü, das jetzt für Gruppen zwei Wege bietet: *Gruppe verschieben …* (Anordnung bleibt) und *Alle auf einen Punkt …*

## 0.46

- Karte: Fotos und ganze Gruppen lassen sich **mit der Maus verschieben**; eine Gruppe wandert als Ganzes, die Anordnung bleibt. Mit „Rückgängig“
- Karte: **Rechtsklick-Menü** (am Handy lange drücken) mit *Ort ändern …* (Ortsdialog mit Suche, alle auf einen Punkt), *Ort entfernen* und *Ansehen*

## 0.45

- Karte: Knopf **Satellit** oben rechts (Esri World Imagery mit Grenzen und Ortsnamen), auch im Ortsdialog; die Wahl bleibt auf dem Gerät gespeichert
- Neue Option **`map_language`**: `de` = deutscher Kartenstil, `local` = jedes Land in seiner eigenen Sprache

## 0.44

- Karte im **deutschen Kartenstil** (openstreetmap.de): Länder und Orte heißen jetzt auf Deutsch, die Landessprache steht in Klammern – bisher standen z. B. arabische oder griechische Schriftzeichen auf der Karte

## 0.43

- Karte: Im Fenster „Ohne Ort“ wählt **Shift+Klick** einen ganzen Bereich aus, wie in der Galerie

## 0.42

- **Umwandeln: Halbbilder werden aufgelöst.** DV-, DVD- und Camcorder-Aufnahmen (interlaced) bekamen bisher Kammartefakte bei Bewegung; jetzt rechnet yadif Vollbilder daraus. Auch abspielbare H.264-Videos mit Halbbildern werden dafür umgewandelt
- **Fortschritt in Prozent** im Hinweis „Umwandeln läuft“, bei stundenlangen DVD-Videos endlich sichtbar
- **Abgeschnittene Originale werden gerettet:** Verspricht der Dateikopf mehr, als die Datei enthält (Nullbytes am Ende einer abgebrochenen Kopie), wird der lesbare Teil umgewandelt und unter *Speicherplatz → Beschädigt* mit Grund vermerkt, statt die Umwandlung abzulehnen
- **Bessere Qualität bei SD und HD:** x264-Preset nach Auflösung (SD `medium`, HD `faster`, ab 1080p weiter `veryfast`)

## 0.41

- Behoben: Fotos standen dauerhaft unter **Speicherplatz → Beschädigt**, obwohl ihr Vorschaubild längst da war. Ein einmal fehlgeschlagener Versuch (etwa wenn beim Hochladen viele Vorschaubilder gleichzeitig entstehen) wurde nie wiederholt und nie zurückgesetzt. Jetzt wird erneut versucht, und wenn die Datei in Ordnung ist, verschwindet der Eintrag aus der Liste

## 0.40

- **Keine doppelten Umwandlungen mehr:** Wer ein Original aus dem Papierkorb wiederherstellt und noch einmal „Umwandeln“ wählt, bekam bisher eine zweite Fassung mit `_1` im Namen. Jetzt meldet das Add-on, wo die fertige Datei liegt, und lässt das Original in Ruhe

## 0.39

- **iPhone: Einzelansicht ließ sich nicht mehr schließen**, wenn Safari statt des Fotos die ganze Seite zoomte und das X aus dem Bild schob. Der Seitenzoom ist in der Einzelansicht jetzt gesperrt (gezoomt wird das Foto selbst), das X weicht Notch/Dynamic Island aus (Safe-Area), und **Wischen nach unten schließt** die Ansicht zusätzlich

## 0.38

- **Ordner hochladen** (nur am PC/Mac): neuer Knopf neben „Hochladen“ wählt einen ganzen Ordner samt Unterordnern; versteckte Dateien (.DS_Store u. Ä.) werden übersprungen. Wie bisher gilt: schon vorhandene Dateien werden nicht erneut gesendet, große Uploads laufen in 32-MB-Stücken mit Fortsetzen. Auf iPhone/iPad und Android gibt es keinen Ordner-Dialog – dort erscheint der Knopf nicht

## 0.37

- **Umwandeln aus dem Papierkorb:** Die Auswahl im Papierkorb bietet jetzt „Umwandeln“ an (nur über Home Assistant). Die Dateien werden zuerst wiederhergestellt und dann wie gewohnt umgewandelt – für Videos, die im Papierkorb gelandet sind, weil sie sich nicht abspielen ließen

## 0.36

- Neue Videoformate: **MPG/MPEG** (ältere Kameras, DVD-Rekorder) und **WMV** (Windows). Browser spielen sie nicht ab; mit „Beim Import umwandeln“ werden sie gleich zu H.264-MP4, sonst über „Umwandeln“ in der Auswahl

## 0.35

- Anmeldung: Die Sperre einer **Adresse** greift erst nach 30 statt 10 Fehlversuchen in 15 Minuten. Zu Hause teilt sich die Familie eine IP; die Tippfehler mehrerer Leute sperrten sonst alle aus. Die Sperre des einzelnen **Kontos** bleibt bei 10 Fehlversuchen

## 0.34

- **Löschen vorschlagen:** Konten ohne Löschrecht („Ansehen“ und „Hochladen + Bearbeiten“) schlagen Fotos zum Löschen vor, einzeln oder in der Auswahl, auf Wunsch mit Grund
- In Home Assistant zeigt ein Symbol mit Zahl die offenen Vorschläge; die Ansicht **Löschvorschläge** listet die Fotos zum Löschen oder Ablehnen. Die Einzelansicht nennt, wer was vorgeschlagen hat

## 0.33

- Behoben: Im Internetzugang kam beim Scrollen durch die Galerie „Zu viele Anfragen“ (429), und Manifest und App-Symbole ließen sich dann gar nicht laden. Angemeldete haben jetzt einen eigenen Zähler je Konto statt je IP (eine Familie teilt sich zu Hause eine Adresse), Vorschaubilder zählen nicht mehr mit, und Anfragen ohne Anmeldung haben ihren eigenen Zähler
- Lizenz: MIT (die Modelle der Gesichtserkennung lädt das Add-on von InsightFace nach, sie sind nur nicht-kommerziell nutzbar)

## 0.32

- Karte: **Zeitregler** – nur Fotos aus einem Zeitraum zeigen (1 Jahr, einstellbar bis 10 Jahre), per Regler oder ◀ ▶ vom ältesten Foto bis heute verschieben, mit Anzahl der Fotos im Zeitraum
- README neu: englisch für die Suche auf GitHub, Knopf zum Hinzufügen in Home Assistant, Übersicht aller Funktionen

## 0.31

- Behoben: Ein neu hochgeladenes Foto konnte die Vorschau eines endgültig gelöschten zeigen. SQLite vergab dessen ID erneut, und der Browser hatte die Vorschau unter derselben Adresse im Cache. IDs werden jetzt nie wiederverwendet
- Einmalig bekommen alle Bild-Adressen eine neue Kennung, damit schon falsch gecachte Vorschauen auf allen Geräten verschwinden (die Vorschaubilder werden dafür einmal neu geladen)

## 0.30

- Rolle **Hochladen + Bearbeiten (ohne Löschen)** (vorher „Ansehen + Hochladen“): darf jetzt auch Schlagworte, Personen, Orte und Datum ändern, drehen und Gesichter benennen – nur keine Bilder löschen (kein Papierkorb, kein Wiederherstellen, keine Duplikat-Bereinigung)
- Hochladen am Handy: Vorab-Prüfung, damit schon vorhandene Fotos gar nicht erst übertragen werden (gleicher Name und gleiche Größe)
- Upload-Anzeige am Handy als schmale Leiste mit Gesamtfortschritt und Restzeit, aufklappbar; neuer Knopf **Abbrechen**
- Während des Hochladens bleibt der Bildschirm an; beim Schließen der Seite mit offenen Uploads kommt eine Warnung
- Suche: Ein Klick ins leere Suchfeld zeigt alle Schlagworte zur Auswahl, die häufigsten zuerst

## 0.29

- **Als App installierbar** (Internetzugang): unter Android mit Knopf *App installieren*, am iPhone über „Zum Home-Bildschirm“ (die Seite zeigt einmal einen Hinweis). Eigenes Symbol, Vollbild ohne Browserleiste
- **Teilen-Menü unter Android:** In der Galerie Fotos auswählen, *Teilen*, *Fotoarchiv*, und sie werden hochgeladen
- **Große Dateien in Stücken hochladen** (32 MB): Videos über 100 MB passen jetzt durch Cloudflare, und nach einem Verbindungsabbruch geht der Upload an der Abbruchstelle weiter
- Abgebrochene Teil-Uploads werden nach einem Tag aufgeräumt

## 0.28

- Einzelansicht: Die Pfeile zum Blättern bleiben an derselben Stelle – bei Videos saßen sie bisher höher als bei Fotos, und am Handy wanderten sie mit der Höhe des Infobereichs

## 0.27

- Internetzugang: Jede angemeldete Person kann ihr **Passwort selbst ändern** (Schloss-Symbol oben rechts). Dafür ist das bisherige Passwort nötig, falsche Eingaben zählen wie fehlgeschlagene Anmeldungen. Danach werden alle anderen Geräte abgemeldet

## 0.26

- Neue Option **`auto_import`**: Das Add-on prüft den Import-Ordner jede Minute und liest neue, fertig kopierte Dateien selbst ein. Gedacht für Handys, die per FolderSync oder PhotoSync im WLAN hochladen, nur in eine Richtung
- Beim automatischen Import werden Duplikate (byte-gleich, schon im Archiv oder Papierkorb) gelöscht statt nach `_duplikate` verschoben
- Nicht unterstützte Dateien im Import-Ordner stoßen den automatischen Import nicht immer wieder an
- Doku: Abschnitt „Handy automatisch sichern“ mit Einstellungen für FolderSync und PhotoSync

## 0.25

- Internetzugang: neue Rolle **Ansehen + Hochladen** – darf alles ansehen und Fotos und Videos hochladen, aber nichts ändern oder löschen

## 0.24

- Einzelansicht: Personen, Schlagworte und Ort werden erst mit **Speichern** in die Datei geschrieben, nicht mehr bei jeder einzelnen Eingabe. Solange etwas offen ist, zeigt der Infobereich unten *Speichern* und *Verwerfen*
- Ein Name, der noch ohne Enter im Feld steht, wird beim Speichern mitgenommen
- Blättern oder Schließen mit ungespeicherten Änderungen fragt vorher nach
- Der Ortsdialog der Einzelansicht heißt dafür jetzt *Übernehmen*

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
