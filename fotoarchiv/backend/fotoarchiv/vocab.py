"""Schlagworte, die die Bilderkennung vorschlägt: Schlagwort -> Beschreibungen für CLIP.

Je Schlagwort zählt der Mittelwert seiner Beschreibungen. Die Hintergrund-Sätze stehen für
"nichts Bestimmtes": Ein Foto bekommt nur dann ein Schlagwort, wenn es diesem klar ähnlicher ist
als allen anderen Schlagworten und dem Hintergrund (Kalibrierung an 400 Fotos der Bibliothek).
Wer hier etwas ändert, löst beim nächsten Start eine Neuberechnung der Vorschläge aus – aus den
gespeicherten Bildmerkmalen, ohne die Fotos noch einmal zu lesen.
"""

import hashlib
import json

VOCAB = {
    "Strand": ["ein Foto von einem Sandstrand", "Menschen am Strand", "ein Kind im Sand am Strand"],
    "Meer": ["das offene Meer mit Wellen", "ein Foto vom Meer"],
    "See": ["ein See in der Natur", "ein Bergsee"],
    "Fluss": ["ein Fluss", "ein Bach im Wald"],
    "Berge": ["eine Berglandschaft", "hohe Berge"],
    "Wald": ["ein Wald mit Bäumen", "ein Waldweg"],
    "Schnee": ["Schnee im Winter", "eine verschneite Landschaft"],
    "Sonnenuntergang": ["ein Sonnenuntergang", "Abendrot am Himmel"],
    "Nacht": ["ein Foto bei Nacht", "Lichter in der Dunkelheit"],
    "Feuerwerk": ["ein Feuerwerk am Himmel"],
    "Stadt": ["eine Straße in einer Stadt", "Häuser in einer Altstadt"],
    "Kirche": ["eine Kirche", "das Innere einer Kirche"],
    "Burg": ["eine Burg mit Türmen", "ein Schloss"],
    "Garten": ["ein Garten mit Rasen", "Gartenarbeit"],
    "Blumen": ["Blumen", "eine Blüte in Nahaufnahme"],
    "Hund": ["ein Hund", "ein Foto von einem Hund"],
    "Katze": ["eine Katze", "ein Foto von einer Katze"],
    "Pferd": ["ein Pferd", "Reiten auf einem Pferd"],
    "Vogel": ["ein Vogel"],
    "Fisch": ["ein Fisch", "ein gefangener Fisch in der Hand"],
    "Angeln": ["Angeln am Wasser mit einer Angelrute", "ein Angler"],
    "Aquarium": ["ein Aquarium mit Fischen"],
    "Unterwasser": ["ein Foto unter Wasser beim Tauchen", "ein Korallenriff unter Wasser"],
    "Insekt": ["ein Insekt", "eine Spinne", "ein Schmetterling"],
    "Motorrad": ["ein Motorrad", "Motorradfahren"],
    "Auto": ["ein Auto", "ein Auto auf der Straße"],
    "Fahrrad": ["ein Fahrrad", "Radfahren"],
    "Boot": ["ein Boot oder Schiff auf dem Wasser"],
    "Flugzeug": ["ein Flugzeug", "der Blick aus dem Flugzeugfenster"],
    "Zug": ["ein Zug", "ein Bahnhof"],
    "Essen": ["Essen auf einem Teller", "eine Mahlzeit im Restaurant"],
    "Kuchen": ["ein Kuchen oder eine Torte", "Gebäck"],
    "Grillen": ["Grillen auf einem Grill", "Würstchen auf dem Grill"],
    "Geburtstag": ["eine Geburtstagstorte mit Kerzen", "eine Geburtstagsfeier"],
    "Weihnachten": ["ein geschmückter Weihnachtsbaum", "Weihnachtsdekoration und Geschenke"],
    "Ostern": ["Ostereier", "Osterdekoration"],
    "Hochzeit": ["eine Braut im weißen Brautkleid", "ein Brautpaar bei der Hochzeit"],
    "Baby": ["ein Baby", "ein Neugeborenes"],
    "Kinder": ["spielende Kinder", "ein Kind"],
    "Gruppenfoto": ["ein Gruppenfoto mit vielen Menschen"],
    "Schwimmbad": ["ein Schwimmbad", "ein Pool"],
    "Spielplatz": ["ein Spielplatz mit Schaukel und Rutsche", "Kinder auf einem Klettergerüst"],
    "Camping": ["ein Zelt beim Camping", "ein Wohnmobil"],
    "Lagerfeuer": ["ein Lagerfeuer", "Feuer in einer Feuerstelle"],
    "Sport": ["Fußball spielen", "Sport treiben"],
    "Skifahren": ["Skifahren im Schnee", "eine Skipiste"],
    "Party": ["eine Party mit Luftballons", "Menschen tanzen auf einer Feier"],
    "Dokument": ["ein Dokument mit Text", "ein beschriebenes Blatt Papier", "ein Brief"],
    "Bildschirmfoto": ["ein Bildschirmfoto vom Handy", "ein Screenshot einer App"],
    "Landkarte": ["eine Landkarte"],
    "Solaranlage": ["Solarmodule auf einem Dach"],
    "Baustelle": ["eine Baustelle", "Werkzeug und Handwerk"],
    "Wohnung": ["ein Wohnzimmer", "das Innere einer Wohnung"],
    "Wasserfall": ["ein Wasserfall"],
    "Palmen": ["Palmen"],
    "Kerzen": ["brennende Kerzen"],
    "Tiere": ["Tiere im Zoo", "Kühe oder Schafe auf einer Weide"],
}

BACKGROUND = [
    "ein Foto", "ein Bild", "ein unscharfes Foto", "ein Foto von etwas",
    "ein Porträt einer Person", "zwei Menschen", "Menschen in einem Raum", "Menschen im Freien", "eine Familie",
]


def fingerprint() -> str:
    """Ändert sich mit jeder Änderung an Schlagworten oder Beschreibungen."""
    text = json.dumps([VOCAB, BACKGROUND], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]
