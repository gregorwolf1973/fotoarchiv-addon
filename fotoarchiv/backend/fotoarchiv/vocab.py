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


# Anzeige- und Schreibnamen der Schlagworte in den Sprachen der Oberfläche (en, it, es). Intern bleibt der deutsche
# Name der Schlüssel; die Liste gehört nicht zum Fingerabdruck, eine neue Übersetzung rechnet also nichts neu.
LANGUAGES = ("en", "it", "es")
NAMES = {
    "Strand": ("Beach", "Spiaggia", "Playa"),
    "Meer": ("Sea", "Mare", "Mar"),
    "See": ("Lake", "Lago", "Lago"),
    "Fluss": ("River", "Fiume", "Río"),
    "Berge": ("Mountains", "Montagne", "Montañas"),
    "Wald": ("Forest", "Bosco", "Bosque"),
    "Schnee": ("Snow", "Neve", "Nieve"),
    "Sonnenuntergang": ("Sunset", "Tramonto", "Puesta de sol"),
    "Nacht": ("Night", "Notte", "Noche"),
    "Feuerwerk": ("Fireworks", "Fuochi d'artificio", "Fuegos artificiales"),
    "Stadt": ("City", "Città", "Ciudad"),
    "Kirche": ("Church", "Chiesa", "Iglesia"),
    "Burg": ("Castle", "Castello", "Castillo"),
    "Garten": ("Garden", "Giardino", "Jardín"),
    "Blumen": ("Flowers", "Fiori", "Flores"),
    "Hund": ("Dog", "Cane", "Perro"),
    "Katze": ("Cat", "Gatto", "Gato"),
    "Pferd": ("Horse", "Cavallo", "Caballo"),
    "Vogel": ("Bird", "Uccello", "Pájaro"),
    "Fisch": ("Fish", "Pesce", "Pez"),
    "Angeln": ("Fishing", "Pesca", "Pesca"),
    "Aquarium": ("Aquarium", "Acquario", "Acuario"),
    "Unterwasser": ("Underwater", "Sott'acqua", "Bajo el agua"),
    "Insekt": ("Insect", "Insetto", "Insecto"),
    "Motorrad": ("Motorcycle", "Moto", "Moto"),
    "Auto": ("Car", "Auto", "Coche"),
    "Fahrrad": ("Bicycle", "Bicicletta", "Bicicleta"),
    "Boot": ("Boat", "Barca", "Barco"),
    "Flugzeug": ("Plane", "Aereo", "Avión"),
    "Zug": ("Train", "Treno", "Tren"),
    "Essen": ("Food", "Cibo", "Comida"),
    "Kuchen": ("Cake", "Torta", "Pastel"),
    "Grillen": ("Barbecue", "Grigliata", "Barbacoa"),
    "Geburtstag": ("Birthday", "Compleanno", "Cumpleaños"),
    "Weihnachten": ("Christmas", "Natale", "Navidad"),
    "Ostern": ("Easter", "Pasqua", "Pascua"),
    "Hochzeit": ("Wedding", "Matrimonio", "Boda"),
    "Baby": ("Baby", "Bebè", "Bebé"),
    "Kinder": ("Children", "Bambini", "Niños"),
    "Gruppenfoto": ("Group photo", "Foto di gruppo", "Foto de grupo"),
    "Schwimmbad": ("Swimming pool", "Piscina", "Piscina"),
    "Spielplatz": ("Playground", "Parco giochi", "Parque infantil"),
    "Camping": ("Camping", "Campeggio", "Camping"),
    "Lagerfeuer": ("Campfire", "Falò", "Hoguera"),
    "Sport": ("Sport", "Sport", "Deporte"),
    "Skifahren": ("Skiing", "Sci", "Esquí"),
    "Party": ("Party", "Festa", "Fiesta"),
    "Dokument": ("Document", "Documento", "Documento"),
    "Bildschirmfoto": ("Screenshot", "Screenshot", "Captura de pantalla"),
    "Landkarte": ("Map", "Mappa", "Mapa"),
    "Solaranlage": ("Solar panels", "Pannelli solari", "Paneles solares"),
    "Baustelle": ("Construction site", "Cantiere", "Construcción"),
    "Wohnung": ("Home", "Casa", "Casa"),
    "Wasserfall": ("Waterfall", "Cascata", "Cascada"),
    "Palmen": ("Palm trees", "Palme", "Palmeras"),
    "Kerzen": ("Candles", "Candele", "Velas"),
    "Tiere": ("Animals", "Animali", "Animales"),
}


def translations(name: str) -> dict:
    """Name des Schlagworts je Sprache, z. B. {"de": "Essen", "en": "Food", …}; unbekannte Namen bleiben, wie sie sind."""
    return {"de": name, **dict(zip(LANGUAGES, NAMES.get(name, (name,) * len(LANGUAGES))))}


def localized(name: str, language: str | None) -> str:
    return translations(name).get(language or "de", name)


_BY_ANY_NAME = {variant.casefold(): key for key in VOCAB for variant in translations(key).values()}


def internal(name: str) -> str | None:
    """Schlagwort in irgendeiner Sprache -> interner (deutscher) Name, oder None."""
    return _BY_ANY_NAME.get(str(name).strip().casefold())


def fingerprint() -> str:
    """Ändert sich mit jeder Änderung an Schlagworten oder Beschreibungen."""
    text = json.dumps([VOCAB, BACKGROUND], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]
