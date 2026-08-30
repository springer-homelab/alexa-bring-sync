"""
====================================================================================================
🛒 Bring! Direct API Client & Intelligent NLU Grocery Parser for Home Assistant
====================================================================================================

Architektur & Pipeline:
  1. Alexa Sprachbefehl (Echo Dot / HA alexa_media_player)
  2. Intent-Guard: is_valid_shopping_command() filtert Timer-, Musik- & KI-Gespräche ab
  3. Normalisierung: normalize_spoken_german() wandelt Zahlwörter, Brüche, Dezimalstellen in Ziffern
  4. Floskel-Stripping: strip_command_phrases() entfernt Sprachbefehls-Prefixe und -Suffixe
  5. Einheiten-Extraktion: extract_specification() trennt '2kg', '5m', '3.5%', '1 Sack' sauber ab
  6. Listen-Splitting: smart_split_consecutive() teilt Aufzählungen, schützt aber Mehrwortbegriffe
  7. Duden-Morphologie: match_catalog_name() synthetisiert Komposita ('Mandelmilch') & trennt Adjektive ('Saure Sahne')
  8. Bring! API Sync: execute_bring_sync() sendet Batch-Changes in < 150ms per HTTPS an Bring!
  9. State Sensor: fetch_active_bring_items() aktualisiert .bring_active.json für Home Assistant

Autoren: Springer Homelab
Version: 2.1.0 (Production Release)
====================================================================================================
"""

import sys
import os
import json
import urllib.request
import urllib.parse
import re
import yaml

# ==================================================================================================
# 1. KONFIGURATION & DATEIPFADE
# ==================================================================================================

CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_FILE = os.path.join(CONFIG_DIR, 'secrets.yaml')
CACHE_FILE = os.path.join(CONFIG_DIR, '.storage', 'bring_auth_cache.json')
CATALOG_CACHE_FILE = os.path.join(CONFIG_DIR, '.storage', 'bring_catalog_cache.json')
ACTIVE_ITEMS_FILE = os.path.join(CONFIG_DIR, '.bring_active.json')

API_BASE = 'https://api.getbring.com/rest'
API_KEY = 'cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp'
CLIENT = 'android'
APPLICATION = 'bring'
COUNTRY = 'DE'


# ==================================================================================================
# 2. LINGUISTISCHE STAMMFORMEN- & STEMMING-ENGINE
# ==================================================================================================

def stem_german(word):
    """
    Generischer deutscher Stammformen-Algorithmus (nur für internen Abgleich):
    Erzeugt einen gemeinsamen Vergleichs-Schlüssel für Einzahl und Mehrzahl
    (z. B. 'Bananen' und 'Banane' -> 'banan', 'Äpfel' und 'Apfel' -> 'apfel').
    Auf Bring! landet immer der vollständige, korrekte Name (z. B. 'Bananen' oder 'Äpfel').
    """
    w = word.lower().strip()
    # Umlaute normalisieren
    w = w.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
    
    # Plural-Endungen sauber entfernen (ab mindestens 4 Buchstaben)
    if len(w) >= 4:
        w = re.sub(r'(?:en|ern|er|e|s|n)$', '', w)
    return w


# ==================================================================================================
# 3. ZAHLWÖRTER-, BRUCH- & DEZIMAL-NORMALISIERUNG
# ==================================================================================================

def normalize_spoken_german(text):
    """
    Wandelt gesprochene deutsche Zahlwörter, Brüche, traditionelle Maßeinheiten und
    Dezimalzahlen ('2 komma 5' -> 2.5) in maschinenlesbare Ziffern um.
    """
    t = text.strip()

    # 1. Null
    t = re.sub(r'\bnull\b', '0', t, flags=re.IGNORECASE)

    # 2. Brüche & traditionelle Maßeinheiten (z. B. 'anderthalb' -> 1.5, 'ein pfund' -> 500g, 'ein halbes dutzend' -> 6)
    fraction_map = [
        (r'\banderthalb\b|\beineinhalb\b', '1.5'),
        (r'\bzweieinhalb\b', '2.5'),
        (r'\bdreieinhalb\b', '3.5'),
        (r'\bviereinhalb\b', '4.5'),
        (r'\bfünfeinhalb\b', '5.5'),
        (r'\bdreiviertel\b|\bdrei\s*viertel\b', '0.75'),
        (r'(?:\bein\s+)?halbes\s+dutzend\b', '6'),
        (r'(?:\bein\s+)?dutzend\b', '12'),
        (r'(?:\bein\s+)?halbes\s+pfund\b', '250g'),
        (r'(?:\bein\s+)?pfund\b', '500g'),
        (r'(?:\bein\s+)?halbes\b|(?:\bein\s+)?halber\b|(?:\bein\s+)?halb\b|(?:\beine\s+)?halbe\b', '0.5'),
        (r'(?:\bein\s+)?viertel\b', '0.25')
    ]
    for pattern, val in fraction_map:
        t = re.sub(pattern, val, t, flags=re.IGNORECASE)

    # 3. Hunderter & Tausender (z. B. 'zweihundertfünfzig' -> '200 50', 'fünfhundert' -> '500')
    hundred_prefixes = {'ein': 100, 'zwei': 200, 'drei': 300, 'vier': 400, 'fünf': 500, 'sechs': 600, 'sieben': 700, 'acht': 800, 'neun': 900}
    for h_name, h_val in hundred_prefixes.items():
        t = re.sub(rf'\b{h_name}\s*hundert', f'{h_val} ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bhundert\b', '100 ', t, flags=re.IGNORECASE)
    t = re.sub(r'\btausend\b', '1000 ', t, flags=re.IGNORECASE)

    # 4. Zweistellige Zahlen (z. B. 'zweiundzwanzig' -> 22, 'fünfunddreißig' -> 35)
    ones = {'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9}
    tens = {'zwanzig': 20, 'dreißig': 30, 'vierzig': 40, 'fünfzig': 50, 'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90}
    for one_k, one_v in ones.items():
        for ten_k, ten_v in tens.items():
            compound = f"{one_k}und{ten_k}"
            total = one_v + ten_v
            t = re.sub(rf'\b{compound}\b', str(total), t, flags=re.IGNORECASE)

    # 5. Einzelne Zahlwörter (1 bis 90)
    word_to_num = {
        'zwanzig': '20', 'dreißig': '30', 'vierzig': '40', 'fünfzig': '50', 'sechzig': '60', 'siebzig': '70', 'achtzig': '80', 'neunzig': '90',
        'dreizehn': '13', 'vierzehn': '14', 'fünfzehn': '15', 'sechzehn': '16', 'siebzehn': '17', 'achtzehn': '18', 'neunzehn': '19',
        'zwölf': '12', 'elf': '11', 'zehn': '10', 'neun': '9', 'acht': '8', 'sieben': '7', 'sechs': '6', 'fünf': '5', 'vier': '4', 'drei': '3', 'zwei': '2',
        'eins': '1', 'eine': '1', 'einen': '1', 'einem': '1', 'einer': '1', 'ein': '1'
    }
    for w, n in word_to_num.items():
        t = re.sub(rf'\b{w}\b', str(n), t, flags=re.IGNORECASE)

    # 6. Addition von Hunderter + Zehner/Einer (z. B. '200 50' -> 250, '100 25' -> 125)
    t = re.sub(r'\b(\d{1,4}00)\s+(\d{1,2})\b', lambda m: str(int(m.group(1)) + int(m.group(2))), t)

    # 7. Gesprochene Dezimalzahlen (z. B. '2 komma 5' -> '2.5', '0 komma 5' -> '0.5', '1 punkt 5' -> '1.5')
    t = re.sub(r'\b(\d+)\s*(?:komma|punkt|,|\.)\s*(\d+)\b', r'\1.\2', t, flags=re.IGNORECASE)

    # 8. Markennamen & Titel normalisieren (z. B. 'Doktor Oetker' -> 'Dr. Oetker', 'Ben und Jerrys' -> 'Ben and Jerrys')
    t = re.sub(r'\bdoktor\s+oetker\b', 'Dr. Oetker', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdr\s+oetker\b', 'Dr. Oetker', t, flags=re.IGNORECASE)
    t = re.sub(r'\bgusto\s+gustavo\b', 'Gustavo Gusto', t, flags=re.IGNORECASE)
    t = re.sub(r'\bben\s+(?:und|and|&)\s+jerrys\b', 'Ben and Jerrys', t, flags=re.IGNORECASE)
    t = re.sub(r'\bhäagen\s+dazs\b|\bhaagen\s+dazs\b', 'Haagen Dazs', t, flags=re.IGNORECASE)
    t = re.sub(r'\bmilch\s+schnitte\b', 'Milchschnitte', t, flags=re.IGNORECASE)

    return t.strip()


# ==================================================================================================
# 4. SPRACHBEFEHL-FILTER & FLOSKEL-STRIPPER (PREFIX/SUFFIX)
# ==================================================================================================

def strip_command_phrases(text):
    """
    Entfernt typische deutsche Alexa-Befehlsfloskeln am Anfang und Ende des Satzes
    (z. B. 'setze ... auf die Einkaufsliste', 'Milch und Käse auf die Liste schreiben', 'ändere Bananen auf 3').
    """
    t = text.strip()

    # Mengen-Änderungsbefehle (z. B. 'ändere die Menge von Bananen auf 3', 'ändere Bananen auf 3', 'erhöhe Bananen auf 4')
    for qp in [
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:änder(?:e)?|korrigier(?:e)?|erhöh(?:e)?|setz(?:e)?|pass(?:e)?)\s+(?:(?:die\s+)?(?:menge|anzahl)\s*(?:von|der)?\s+)?(.+?)\s+(?:auf|zu|in|an)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)\s+(.+?)\s+draus$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+aus\s+(.+?)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
    ]:
        qm = re.match(qp, t, re.IGNORECASE)
        if qm:
            g1, g2 = qm.group(1).strip(), qm.group(2).strip()
            if re.match(r'^\d', g1):
                qty, item = g1, g2
            else:
                item, qty = g1, g2
            item = re.sub(r'^(?:die|das|der|den|dem|meine|unsere)\s+', '', item, flags=re.IGNORECASE).strip()
            return f"{qty} {item}"

    patterns = [
        # Prefix Löschbefehle
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+?)\s+(?:von|aus|von\s+der|von\s+den|von\s+unserer|von\s+meiner)\s+(?:der|meiner|unserer|den|die)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:nimm|tu)\s+(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s*runter$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+)$',

        # Suffix Löschbefehle
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s+(?:löschen|entfernen|streichen|runternehmen)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:löschen|entfernen|streichen|abhaken)$',

        # Suffix Hinzufügebefehle (z. B. "Milch und Käse auf die Liste schreiben", "Zwiebeln zur Einkaufsliste hinzufügen")
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:auf|zu|zur|in|an)\s+(?:die|meine|unsere|den|der|das|meinen|unseren)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)\s*(?:schreiben|setzen|packen|hinzufügen|draufpacken|draufsetzen|drauftun)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:hinzufügen|dazuschreiben|draufpacken|draufsetzen)$',

        # Prefix Hinzufügebefehle
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu|pack)\s+(?:bitte\s+)?(?:noch\s+)?(.+?)\s+(?:auf|zu|zur|in|an|der)\s+(?:die|meine|unsere|den|der|das|meinen|unseren)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf)?$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:wir\s+brauchen\s+noch|kauf\s+bitte|kauf(?:en)?|besorg(?:e)?)\s+(.+)$',
        r'^(?:alexa,?\s*)?(?:sag|sage|frage|öffne)\s+(?:meinem?\s+)?(?:einkaufszettel|einkaufsliste|bring|liste)(?::|\s+)?\s*(.+)$',
        r'^(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu)\s+(?:bitte\s+)?(?:noch\s+)?(.+?)(?:\s+(?:auf|zu|zur|in|der)\s+(?:die|den|meine|unsere|der|das|meinen)\s+(?:einkaufsliste|liste|zettel))?$'
    ]
    for p in patterns:
        m = re.match(p, t, re.IGNORECASE)
        if m:
            t = m.group(1)
            break
    t = re.sub(r'^(?:alexa,?\s*)?(?:noch|bitte|mal|eben|schnell)\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:auf|zu|zur|in|an|der|den|die|das|meine|unsere|meinen)?\s*(?:die|meine|unsere|den|der|das|meinen)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf|\s*ab)?$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:zur|zu|auf|an|für|hinzu|drauf|runter|weg|bitte|danke|noch|löschen|entfernen|streichen|schreiben|packen|setzen)$', '', t, flags=re.IGNORECASE)
    return t.strip()


# ==================================================================================================
# 5. INTENT-GUARD & STOPPWORT-VALIDIERUNG
# ==================================================================================================

GERMAN_STOPWORDS = {
    'in', 'an', 'auf', 'aus', 'bei', 'mit', 'nach', 'seit', 'von', 'zu', 'über', 'unter', 'vor', 'zwischen',
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'einer', 'eines',
    'wie', 'was', 'wo', 'wann', 'warum', 'wieso', 'weshalb', 'wer', 'wen', 'wem', 'wessen', 'welche', 'welcher', 'welches', 'welchen',
    'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'hat', 'haben', 'hatte', 'hatten',
    'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'meiner', 'meinem', 'meinen', 'meine', 'unserer', 'unserem', 'unsere',
    'noch', 'schon', 'nicht', 'kein', 'keine', 'keinen', 'viel', 'viele', 'alles', 'nichts', 'etwas',
    'grad', 'minuten', 'sekunden', 'stunden', 'uhr', 'timer', 'wecker', 'danke', 'bitte', 'ja', 'nein', 'nee', 'mal', 'eben', 'lang', 'brauchen'
}

QUESTION_PREFIXES = (
    'was ', 'wie ', 'wo ', 'wann ', 'warum ', 'wieso ', 'weshalb ', 'wer ', 'welche ', 'welcher ', 'welches ', 'welchen ',
    'ist ', 'sind ', 'gibt ', 'hast ', 'kannst ', 'lies ', 'zeige ', 'öffne ', 'starte ', 'spiel ', 'stelle ', 'stell '
)

def is_valid_shopping_command(text):
    """
    Prüft, ob der übergebene Text ein echter Einkaufslisten-Befehl ist.
    Filtert Alexa+ KI-Unterhaltungen, Fragen, Wecker und Timer sicher heraus.
    """
    t = text.strip().lower()
    if t.endswith('?'):
        return False
    if any(t.startswith(q) for q in QUESTION_PREFIXES):
        return False

    # Mengen-Änderungsbefehle (z. B. 'ändere die Menge von Bananen auf 3', 'ändere Bananen auf 3', 'erhöhe Bananen auf 4')
    for qp in [
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:änder(?:e)?|korrigier(?:e)?|erhöh(?:e)?|setz(?:e)?|pass(?:e)?)\s+(?:(?:die\s+)?(?:menge|anzahl)\s*(?:von|der)?\s+)?(.+?)\s+(?:auf|zu|in|an)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)\s+(.+?)\s+draus$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+aus\s+(.+?)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
    ]:
        if re.match(qp, t, re.IGNORECASE):
            return True

    for p in [
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|tu)\s+(.+?)\s+(?:auf|zu|zur|in|an|der)\s+(?:die|meine|unsere|den|der|das)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf)?$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+?)\s+(?:von|aus|von\s+der|von\s+den|von\s+unserer|von\s+meiner)\s+(?:der|meiner|unserer|den|die)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:nimm|tu)\s+(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s*runter$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s+(?:löschen|entfernen|streichen|runternehmen)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:löschen|entfernen|streichen|abhaken)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:wir\s+brauchen\s+noch|wir\s+benötigen\s+noch)\s+(.+)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:kaufe|kauf|besorg|besorge)\s+bitte\s+(.+)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:kaufe|kauf|besorg|besorge)\s+(.+)$',
        r'^(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|tu)\s+(.+?)\s+(?:auf|zu|zur|in|der)\s+(?:die|den|meine|unsere|der|das)\s+(?:einkaufsliste|liste|zettel)$'
    ]:
        if re.match(p, t, re.IGNORECASE):
            return True
    if any(k in t for k in ['einkaufsliste', 'einkaufszettel', 'bring liste', 'bringliste']):
        if any(v in t for v in ['setz', 'pack', 'schreib', 'füg', 'kauf', 'lösch', 'entfern', 'streich', 'nimm', 'änder']):
            return True
    return False

def is_valid_grocery_item(name, catalog_names):
    """
    Validiert, dass der extrahierte Begriff ein echter Artikelname ist.
    """
    n_clean = name.strip()
    n_low = n_clean.lower()
    if not n_clean or len(n_clean) < 2:
        return False
    if any(cat.lower() == n_low for cat in catalog_names):
        return True
    if n_low in GERMAN_STOPWORDS:
        return False
    return True

def detect_operation(raw_text):
    """
    Erkennt die Bring!-Listenoperation:
    - 'TO_PURCHASE': Artikel auf die Einkaufsliste setzen
    - 'TO_RECENTLY': Artikel von der Einkaufsliste entfernen / abhaken
    """
    low = raw_text.lower()
    delete_words = ['lösch', 'lösche', 'entfern', 'entferne', 'streich', 'streiche', 'nimm', 'runter', 'weg', 'löschen', 'entfernen', 'streichen']
    for w in delete_words:
        if w in low:
            return 'TO_RECENTLY'
    return 'TO_PURCHASE'


# ==================================================================================================
# 6. EINHEITEN-, GEBINDE- & SPEZIFIKATIONS-EXTRAKTION (SUPERMARKT + BAUMARKT)
# ==================================================================================================

UNITS_LIST = [
    # Gewicht & Volumen
    'kg', 'kilo', 'kilogramm',
    'g', 'gramm',
    'l', 'liter',
    'ml', 'milliliter', 'cl', 'dl',

    # Baumarkt, Handwerk & Flächen
    'qm', 'quadratmeter',
    'meter', 'm',
    'zentimeter', 'centimeter', 'cm',
    'millimeter', 'mm',
    'zoll',

    # Verpackungsarten & Gebinde
    'packung', 'packungen', 'pkg', 'pack', 'packs', 'pck', 'paket', 'pakete',
    'stk', 'stück',
    'flasche', 'flaschen',
    'dose', 'dosen',
    'bund', 'bunt',
    'beutel',
    'glas', 'gläser',
    'scheibe', 'scheiben',
    'kasten', 'kästen', 'kiste', 'kisten',
    'tüte', 'tüten',
    'becher',
    'zehe', 'zehen', 'knolle', 'knollen',
    'tafel', 'tafeln',
    'tube', 'tuben', 'kartusche', 'kartuschen',
    'stange', 'stangen',
    'zweig', 'zweige',
    'rolle', 'rollen',
    'karton', 'kartons',
    'portion', 'portionen',
    'paar',
    'schale', 'schalen',
    'netz', 'netze',
    'steige', 'steigen',
    'sack', 'säcke',
    'eimer',
    'kanister',
    'bogen', 'blatt',
    'latte', 'latten', 'leiste', 'leisten',
    'brett', 'bretter', 'platte', 'platten',
    '%', 'prozent'
]

UNITS_PATTERN = '|'.join(sorted(UNITS_LIST, key=len, reverse=True))

NOUN_UNITS = {
    'kiste': 'Kiste', 'kisten': 'Kisten',
    'kasten': 'Kasten', 'kästen': 'Kästen',
    'bund': 'Bund', 'bunt': 'Bund',
    'packung': 'Packung', 'packungen': 'Packungen', 'pkg': 'Pkg.', 'pack': 'Pack', 'packs': 'Packs', 'pck': 'Pck.', 'paket': 'Paket', 'pakete': 'Pakete',
    'flasche': 'Flasche', 'flaschen': 'Flaschen',
    'dose': 'Dose', 'dosen': 'Dosen',
    'beutel': 'Beutel',
    'glas': 'Glas', 'gläser': 'Gläser',
    'scheibe': 'Scheibe', 'scheiben': 'Scheiben',
    'tüte': 'Tüte', 'tüten': 'Tüten',
    'becher': 'Becher',
    'zehe': 'Zehe', 'zehen': 'Zehen',
    'knolle': 'Knolle', 'knollen': 'Knollen',
    'tafel': 'Tafel', 'tafeln': 'Tafeln',
    'tube': 'Tube', 'tuben': 'Tuben', 'kartusche': 'Kartusche', 'kartuschen': 'Kartuschen',
    'stange': 'Stange', 'stangen': 'Stangen',
    'zweig': 'Zweig', 'zweige': 'Zweige',
    'rolle': 'Rolle', 'rollen': 'Rollen',
    'karton': 'Karton', 'kartons': 'Kartons',
    'portion': 'Portion', 'portionen': 'Portionen',
    'paar': 'Paar',
    'schale': 'Schale', 'schalen': 'Schalen',
    'netz': 'Netz', 'netze': 'Netze',
    'steige': 'Steige', 'steigen': 'Steigen',
    'sack': 'Sack', 'säcke': 'Säcke',
    'eimer': 'Eimer',
    'kanister': 'Kanister',
    'stück': 'Stück', 'stk': 'Stück',
    'zoll': 'Zoll'
}

def format_specification(spec_str):
    """
    Formatiert die Mengenangabe nach Duden-Regeln:
    - Metrische Einheiten: kurz & klein (z. B. '500g', '2l', '250ml')
    - Deutsche Gebinde/Substantive: großgeschrieben (z. B. '1 Kiste', '2 Bund', '3 Flaschen')
    """
    if not spec_str:
        return ''
    s = spec_str.strip()
    s = re.sub(r'(\d+(?:\.\d+)?)\s*gramm\b', r'\1g', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*kilo(?:gramm)?\b', r'\1kg', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*milliliter\b', r'\1ml', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*liter\b', r'\1l', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*meter\b', r'\1m', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:zentimeter|centimeter)\b', r'\1cm', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*millimeter\b', r'\1mm', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*quadratmeter\b', r'\1qm', s, flags=re.IGNORECASE)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*prozent\b', r'\1%', s, flags=re.IGNORECASE)

    words = s.split()
    formatted_words = []
    for w in words:
        w_low = w.lower()
        if w_low in NOUN_UNITS:
            formatted_words.append(NOUN_UNITS[w_low])
        else:
            formatted_words.append(w)
    return " ".join(formatted_words)

def extract_specification(text):
    """
    Trennt Mengenangaben (z. B. '2kg', '5m', '3.5%', '2 Kartuschen', '1 Kiste', 'Cola 1 Kiste', 'Bananen 3') ab.
    Unterstützt sowohl führende ('1 Kiste Cola') als auch nachgestellte Mengenangaben ('Cola 1 Kiste').
    Entfernt führende deutsche Artikel ('die Milch' -> 'Milch').
    """
    t = text.strip()
    t = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', t, flags=re.IGNORECASE).strip()

    # Muster 1: Ziffer + Einheit AM ANFANG (z. B. '1 Kiste Sprudel', '500g Hackfleisch')
    pattern_unit = rf'^\s*(\d+(?:[.,]\d+)?\s*(?:{UNITS_PATTERN}))\s+(?:von\s+(?:den|der|dem|meinen)?\s*)?(.+)$'
    m = re.match(pattern_unit, t, re.IGNORECASE)
    if m:
        raw_spec = m.group(1).strip()
        name = m.group(2).strip()
        spec = format_specification(raw_spec)
        name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', name, flags=re.IGNORECASE).strip()
        return name, spec

    # Muster 2: Reine Zahl AM ANFANG (z. B. '6 Eier', '3 Gurken')
    pattern_plain = r'^\s*(\d+(?:[.,]\d+)?)\s+(?:von\s+(?:den|der|dem)?\s*)?([a-zA-ZäöüÄÖÜß].+)$'
    m = re.match(pattern_plain, t, re.IGNORECASE)
    if m:
        spec = m.group(1).strip()
        name = m.group(2).strip()
        name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', name, flags=re.IGNORECASE).strip()
        return name, spec

    # Muster 3: Mengenangabe mit Einheit AM ENDE (z. B. 'Cola 1 Kiste', 'Hackfleisch 500g')
    pattern_end_unit = rf'^(.+?)\s+(\d+(?:[.,]\d+)?\s*(?:{UNITS_PATTERN}))$'
    m = re.match(pattern_end_unit, t, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        raw_spec = m.group(2).strip()
        spec = format_specification(raw_spec)
        return name, spec

    # Muster 4: Reine Zahl AM ENDE (z. B. 'Bananen 3', 'Gurken 2')
    pattern_end_plain = r'^([a-zA-ZäöüÄÖÜß\s\.\&\-\']+?)\s+(\d+(?:[.,]\d+)?)$'
    m = re.match(pattern_end_plain, t, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        spec = m.group(2).strip()
        return name, spec

    return t, ''


# ==================================================================================================
# 7. DUDEN-MORPHOLOGIE & MEHRWORT-LEXIKA (KOMPOSITA, ADJEKTIVE, FREMDWÖRTER)
# ==================================================================================================

# Eigenschaftswörter, die mit Nomen getrennt geschrieben werden (z. B. 'Saure Sahne', 'Alkoholfreies Bier')
GROCERY_ADJECTIVES = {
    'wiener', 'saure', 'saurer', 'saures', 'rote', 'roter', 'rotes', 'grüne', 'grüner', 'grünes',
    'frische', 'frischer', 'frisches', 'passierte', 'passierter', 'passiertes',
    'gehackte', 'gehackter', 'gehacktes', 'getrocknete', 'getrockneter', 'getrocknetes',
    'geriebene', 'geriebener', 'geriebenes', 'braune', 'brauner', 'braunes',
    'italienische', 'italienischer', 'italienisches', 'griechische', 'griechischer',
    'gemischte', 'gemischter', 'gemischtes', 'stille', 'stiller', 'stilles',
    'scharfe', 'scharfer', 'scharfes', 'süße', 'süßer', 'süßes', 'milde', 'milder', 'mildes',
    'feine', 'feiner', 'feines', 'grobe', 'grober', 'grobes', 'schwarze', 'schwarzer', 'schwarzes',
    'weiße', 'weißer', 'weißes', 'helle', 'heller', 'helles', 'dunkle', 'dunkler', 'dunkles',
    'gefrorene', 'gefrorener', 'gefrorenes', 'tiefgekühlte', 'tiefgekühlter', 'tiefgekühltes',
    'bio', 'freiland', 'vegan', 'vegane', 'veganer', 'veganes', 'veganen',
    'vegetarisch', 'vegetarische', 'vegetarischer', 'vegetarisches', 'vegetarischen',
    'pflanzlich', 'pflanzliche', 'pflanzlicher', 'pflanzliches',
    'laktosefrei', 'laktosefreie', 'laktosefreies', 'glutenfrei', 'glutenfreie', 'glutenfreies',
    'alkoholfrei', 'alkoholfreie', 'alkoholfreier', 'alkoholfreies', 'alkoholfreien',
    'koffeinfrei', 'koffeinfreie', 'koffeinfreier', 'koffeinfreies', 'koffeinfreien',
    'zuckerfrei', 'zuckerfreie', 'zuckerfreier', 'zuckerfreies', 'zuckerfreien',
    'fettarm', 'fettarme', 'fettarmer', 'fettarmes', 'fettarmen',
    'nativ', 'native', 'nativer', 'natives', 'nativen',
    'kaltgepresst', 'kaltgepresste', 'kaltgepresster', 'kaltgepresstes',
    'regional', 'regionale', 'regionales', 'asiatische', 'asiatischer'
}

# Bestimmende Nomen-Präfixe für Komposita (z. B. 'Puten Brust' -> 'Putenbrust', 'Hafer Milch' -> 'Hafermilch')
COMPOUND_PREFIXES = {
    'oliven', 'sonnenblumen', 'raps', 'kokos', 'mandel', 'soja', 'hafer', 'dinkel',
    'puder', 'vanille', 'back', 'kakao', 'kakaopulver', 'vollmilch', 'zartbitter', 'schoko',
    'mineral', 'erdnuss', 'haselnuss', 'walnuss', 'cashew', 'kräuter', 'knoblauch', 'chili',
    'balsamico', 'weizen', 'roggen', 'mais', 'tiefkühl', 'tk',
    'puten', 'rinder', 'schweine', 'truthahn', 'kalbs', 'lamm', 'geflügel', 'hähnchen', 'hühner', 'fisch', 'lachs', 'thunfisch', 'garnelen',
    'kirsch', 'strauch', 'rispen', 'stauden', 'suppen', 'gewürz', 'koch', 'brat',
    'schafs', 'ziegen', 'hütten', 'mager', 'frisch', 'trocken', 'hart', 'weich', 'voll',
    'apfel', 'orangen', 'trauben', 'multi', 'multivitamin', 'zitronen', 'erdbeer',
    'himbeer', 'blaubeer', 'heidelbeer', 'pfefferminz', 'kamillen', 'fenchel',
    'toiletten', 'klo', 'küchen', 'alu', 'frischhalte', 'gefrier',
    'spül', 'spülmaschinen', 'wasch', 'putz', 'müll'
}

# Unselbstständige Suffixe (z. B. 'Wurst Aufschnitt' -> 'Wurstaufschnitt', 'Spülmaschinen Tabs' -> 'Spülmaschinentabs')
DEPENDENT_SUFFIXES = {
    'aufschnitt', 'geschnetzeltes', 'hackfleisch', 'filet', 'schnitzel', 'kotelett',
    'flocken', 'tabs', 'stäbchen', 'beutel', 'papier', 'paste', 'pulver', 'folie', 'rollen'
}

# Häufige deutsche Nomen-Komposita
VALID_BASE_COMPOUNDS = {
    'wurstaufschnitt', 'käseaufschnitt', 'salatgurke', 'salatgurken', 'kirschtomaten',
    'kochschinken', 'bratwurst', 'currywurst', 'leberwurst', 'teewurst', 'fleischwurst',
    'bockwurst', 'mettwurst', 'feta käse', 'fetakäse', 'frischkäse', 'frisch käse',
    'schmelzkäse', 'bergkäse', 'hartkäse', 'weichkäse', 'hafermilch', 'mandelmilch',
    'sojamilch', 'kokosmilch', 'vollmilch', 'heumilch', 'schlagsahne', 'sauresahne',
    'kaffeesahne', 'kräuterquark', 'speisequark', 'naturjoghurt', 'fruchtjoghurt',
    'nudelsalat', 'kartoffelsalat', 'eiersalat', 'thunfischsalat', 'gurkensalat',
    'tomatenmark', 'currypaste', 'backpulver', 'vanillezucker', 'puderzucker',
    'vollkornbrot', 'weißbrot', 'toastbrot', 'roggenbrot', 'aufbackbrötchen',
    'staudensellerie', 'pfefferminztee', 'kamillentee', 'fencheltee', 'alufolie',
    'frischhaltefolie', 'küchenrollen', 'backpapier', 'müllbeutel', 'toilettenpapier'
}

# Fremdwörter und internationale Bezeichnungen, die getrennt bleiben müssen
FOREIGN_TERMS = {
    'gustavo gusto', 'dr oetker', 'dr. oetker', 'ben and jerrys', 'ben & jerrys', 'haagen dazs',
    'ritter sport', 'ferrero rocher', 'mon cheri', 'mon chéri', 'kinder bueno', 'kinder riegel',
    'kinder country', 'kinder pingui', 'kinder maxi king', 'kinder joy', 'milch schnitte', 'coca cola',
    'coca-cola', 'coke zero', 'pepsi max', 'red bull', 'monster energy', 'paulaner spezi', 'san pellegrino',
    'funny frisch', 'funny-frisch', 'mini babybel', 'fritz kola', 'fritz-kola', 'fritz limo',
    'club mate', 'mio mio', 'mio mio mate', 'fuze tea', 'yogi tea', 'hohes c', 'true fruits',
    'oro di parma', 'coppenrath & wiese', 'coppenrath und wiese', 'head & shoulders', 'head and shoulders',
    'blend-a-med', 'blend a med', 'oral-b', 'oral b',
    'pollo fino', 'creme fraiche', 'crème fraîche', 'sour cream', 'cream cheese',
    'peanut butter', 'curry paste', 'pulled pork', 'ice tea', 'hot dog', 'french dressing',
    'sweet chili', 'sweet sour', 'barbecue sauce', 'bbq sauce', 'maple syrup',
    'tortilla chips', 'nacho chips', 'taco shells', 'salsa verde', 'salsa dip',
    'teriyaki sauce', 'sriracha sauce', 'sweet chili sauce', 'garam masala', 'tikka masala',
    'sushi reis', 'basmati reis', 'jasmin reis', 'mie nudeln', 'udon nudeln', 'ramen nudeln',
    'pesto genovese', 'pesto rosso', 'parmigiano reggiano', 'grana padano', 'pecorino romano',
    'prosciutto di parma', 'serrano schinken', 'iberico schinken', 'chicken nuggets', 'chicken wings',
    'ginger ale', 'tonic water', 'cold brew', 'chai latte', 'balsamico essig'
}

# Eigenständige Markenprodukte, die nicht aufgeteilt werden sollen
STANDALONE_PRODUCTS = {
    'coca cola zero': 'Coca-Cola Zero',
    'coca-cola zero': 'Coca-Cola Zero',
    'coke zero': 'Coke Zero',
    'pepsi max': 'Pepsi Max',
    'paulaner spezi': 'Paulaner Spezi',
    'red bull': 'Red Bull',
    'monster energy': 'Monster Energy',
    'fritz kola': 'Fritz-Kola',
    'fritz-kola': 'Fritz-Kola',
    'club mate': 'Club-Mate',
    'mio mio mate': 'Mio Mio Mate',
    'kinder bueno': 'Kinder Bueno',
    'kinder riegel': 'Kinder Riegel',
    'kinder country': 'Kinder Country',
    'kinder pingui': 'Kinder Pingui',
    'kinder maxi king': 'Kinder Maxi King',
    'kinder joy': 'Kinder Joy',
    'kinder schokolade': 'Kinder Schokolade',
    'ferrero rocher': 'Ferrero Rocher',
    'mon cheri': 'Mon Chéri',
    'mon chéri': 'Mon Chéri',
    'ritter sport': 'Ritter Sport',
    'funny frisch': 'Funny-Frisch',
    'funny-frisch': 'Funny-Frisch',
    'mini babybel': 'Mini Babybel'
}

# Bekannte Markennamen und ihre saubere Duden-Schreibweise
BRAND_MAP = {
    # Getränke: Softdrinks, Eistee, Energy
    'coca cola': 'Coca-Cola', 'coca-cola': 'Coca-Cola', 'coke zero': 'Coke Zero', 'coca cola zero': 'Coca-Cola Zero',
    'pepsi max': 'Pepsi Max', 'pepsi': 'Pepsi', 'fanta': 'Fanta', 'sprite': 'Sprite',
    'mezzo mix': 'Mezzo Mix', 'schwip schwap': 'Schwip Schwap', 'paulaner spezi': 'Paulaner Spezi', 'spezi': 'Spezi',
    'bionade': 'Bionade', 'fritz kola': 'Fritz-Kola', 'fritz-kola': 'Fritz-Kola', 'fritz limo': 'Fritz Limo',
    'club mate': 'Club-Mate', 'mio mio': 'Mio Mio', 'mio mio mate': 'Mio Mio Mate',
    'red bull': 'Red Bull', 'monster energy': 'Monster Energy', 'monster': 'Monster', 'rockstar': 'Rockstar', 'effect': 'Effect',
    'fuze tea': 'Fuze Tea', 'lipton': 'Lipton', 'arizona': 'AriZona',

    # Getränke: Wasser & Saft
    'gerolsteiner': 'Gerolsteiner', 'volvic': 'Volvic', 'vittel': 'Vittel', 'evian': 'Evian',
    'san pellegrino': 'San Pellegrino', 'adelholzener': 'Adelholzener', 'rhönsprudel': 'RhönSprudel',
    'apollinaris': 'Apollinaris', 'black forest': 'Black Forest',
    'hohes c': 'Hohes C', 'granini': 'Granini', 'valensina': 'Valensina', 'pfanner': 'Pfanner',
    'amecke': 'Amecke', 'innocent': 'Innocent', 'true fruits': 'True Fruits', 'rauch': 'Rauch',

    # Getränke: Bier & Wein
    'krombacher': 'Krombacher', 'bitburger': 'Bitburger', 'warsteiner': 'Warsteiner',
    'becks': "Beck's", "beck's": "Beck's", 'paulaner': 'Paulaner', 'erdinger': 'Erdinger',
    'franziskaner': 'Franziskaner', 'augustiner': 'Augustiner', 'tegernseer': 'Tegernseer',
    'rothaus': 'Rothaus', 'heineken': 'Heineken', 'corona': 'Corona', 'desperados': 'Desperados',
    'astra': 'Astra', 'jever': 'Jever', 'veltins': 'Veltins', 'hasseröder': 'Hasseröder',
    'oettinger': 'Oettinger', 'schöfferhofer': 'Schöfferhofer', 'guinness': 'Guinness', 'flensburger': 'Flensburger',

    # Heißgetränke & Pflanzendrinks
    'tchibo': 'Tchibo', 'jacobs': 'Jacobs', 'dallmayr': 'Dallmayr', 'lavazza': 'Lavazza',
    'segafredo': 'Segafredo', 'melitta': 'Melitta', 'nespresso': 'Nespresso', 'senseo': 'Senseo',
    'dolce gusto': 'Dolce Gusto', 'teekanne': 'Teekanne', 'messmer': 'Meßmer', 'meßmer': 'Meßmer',
    'yogi tea': 'Yogi Tea', 'kaba': 'Kaba', 'nesquik': 'Nesquik', 'ovomaltine': 'Ovomaltine',
    'oatly': 'Oatly', 'alpro': 'Alpro', 'bärenmarke': 'Bärenmarke', 'weihenstephan': 'Weihenstephan',
    'landliebe': 'Landliebe', 'müllermilch': 'Müllermilch',

    # Pizza, Tiefkühl, Fertiggerichte
    'gustavo gusto': 'Gustavo Gusto', 'gusto gustavo': 'Gustavo Gusto',
    'dr oetker': 'Dr. Oetker', 'dr. oetker': 'Dr. Oetker', 'doktor oetker': 'Dr. Oetker',
    'wagner': 'Wagner', 'original wagner': 'Original Wagner',
    'frosta': 'Frosta', 'iglo': 'Iglo', 'mccain': 'McCain', 'coppenrath & wiese': 'Coppenrath & Wiese',
    'coppenrath und wiese': 'Coppenrath & Wiese',
    'ben and jerrys': "Ben & Jerry's", 'ben und jerrys': "Ben & Jerry's", 'ben & jerrys': "Ben & Jerry's",
    'haagen dazs': 'Häagen-Dazs', 'häagen dazs': 'Häagen-Dazs',
    'magnum': 'Magnum', 'cornetto': 'Cornetto', 'langnese': 'Langnese',

    # Süßwaren & Snacks
    'ritter sport': 'Ritter Sport', 'milka': 'Milka', 'lindt': 'Lindt',
    'ferrero rocher': 'Ferrero Rocher', 'mon cheri': 'Mon Chéri', 'mon chéri': 'Mon Chéri',
    'kinder bueno': 'Kinder Bueno', 'kinder riegel': 'Kinder Riegel', 'kinder country': 'Kinder Country',
    'kinder pingui': 'Kinder Pingui', 'kinder maxi king': 'Kinder Maxi King', 'kinder schokolade': 'Kinder Schokolade',
    'kinder joy': 'Kinder Joy', 'raffaello': 'Raffaello', 'giotto': 'Giotto', 'giottos': 'Giotto',
    'nutella': 'Nutella', 'duplo': 'Duplo', 'hanuta': 'Hanuta', 'toffifee': 'Toffifee', 'knoppers': 'Knoppers',
    'haribo': 'Haribo', 'katjes': 'Katjes', 'trolli': 'Trolli', 'nimm 2': 'Nimm 2',
    'chio': 'Chio', 'funny frisch': 'Funny-Frisch', 'funny-frisch': 'Funny-Frisch', 'pringles': 'Pringles',
    'lorenz': 'Lorenz', 'ültje': 'Ültje', 'ueltje': 'Ültje',
    'leibniz': 'Leibniz', 'bahlsen': 'Bahlsen', 'prinzenrolle': 'Prinzenrolle', 'prinzen rolle': 'Prinzenrolle',
    'oreo': 'Oreo', 'kitkat': 'KitKat', 'kit kat': 'KitKat', 'twix': 'Twix', 'snickers': 'Snickers',
    'mars': 'Mars', 'bounty': 'Bounty', 'milky way': 'Milky Way', 'm&ms': 'M&Ms', 'm&m': 'M&Ms',
    'milch schnitte': 'Milchschnitte', 'milchschnitte': 'Milchschnitte',

    # Molkerei, Butter & Käse
    'philadelphia': 'Philadelphia', 'almette': 'Almette', 'miree': 'Miree', 'bresso': 'Bresso',
    'exquisa': 'Exquisa', 'brunch': 'Brunch', 'kerrygold': 'Kerrygold', 'rama': 'Rama',
    'becel': 'Becel', 'meggle': 'Meggle', 'lätta': 'Lätta', 'laetta': 'Lätta',
    'leerdammer': 'Leerdammer', 'babybel': 'Babybel', 'mini babybel': 'Mini Babybel',
    'kiri': 'Kiri', 'zott': 'Zott', 'zottarella': 'Zottarella', 'monte': 'Monte',
    'ehrmann': 'Ehrmann', 'grand dessert': 'Grand Dessert', 'danone': 'Danone',
    'activia': 'Activia', 'actimel': 'Actimel', 'fruchtzwerge': 'Fruchtzwerge', 'froop': 'Froop',

    # Pasta, Saucen, Feinkost, Konserven
    'barilla': 'Barilla', 'de cecco': 'De Cecco', 'buitoni': 'Buitoni', 'miracoli': 'Mirácoli', 'mirácoli': 'Mirácoli',
    'maggi': 'Maggi', 'knorr': 'Knorr', 'thomy': 'Thomy', 'heinz': 'Heinz', 'kraft': 'Kraft',
    'kühne': 'Kühne', 'hengstenberg': 'Hengstenberg', 'bonduelle': 'Bonduelle', 'erasco': 'Erasco',
    'birkel': 'Birkel', 'mutti': 'Mutti', 'oro di parma': 'Oro di Parma', 'saupiquet': 'Saupiquet', 'appel': 'Appel',

    # Drogerie & Haushalt
    'tempo': 'Tempo', 'zewa': 'Zewa', 'hakle': 'Hakle', 'ariel': 'Ariel', 'persil': 'Persil',
    'spee': 'Spee', 'lenor': 'Lenor', 'perwoll': 'Perwoll', 'frosch': 'Frosch', 'pril': 'Pril',
    'fairy': 'Fairy', 'somat': 'Somat', 'finish': 'Finish', 'calgon': 'Calgon',
    'meister proper': 'Meister Proper', 'bref': 'Bref', 'cillit bang': 'Cillit Bang', 'domestos': 'Domestos',
    'viss': 'Viss', 'sagrotan': 'Sagrotan', 'nivea': 'Nivea', 'dove': 'Dove', 'palmolive': 'Palmolive',
    'garnier': 'Garnier', 'head & shoulders': 'Head & Shoulders', 'head and shoulders': 'Head & Shoulders',
    'schauma': 'Schauma', 'colgate': 'Colgate', 'blend-a-med': 'Blend-a-med', 'blend a med': 'Blend-a-med',
    'sensodyne': 'Sensodyne', 'elmex': 'Elmex', 'aronal': 'Aronal', 'oral-b': 'Oral-B', 'oral b': 'Oral-B',
    'gillette': 'Gillette', 'wilkinson': 'Wilkinson', 'pampers': 'Pampers'
}

BRAND_PAIRS = {k for k in BRAND_MAP.keys() if ' ' in k}

# Eindeutige Monoprodukt-Marken (nur wenn KEIN Substantiv genannt wurde, um das perfekte Bring!-Icon zu erhalten)
UNAMBIGUOUS_BRAND_CATEGORIES = {
    # Bier
    'augustiner': ('Bier', 'Augustiner'),
    'krombacher': ('Bier', 'Krombacher'),
    'bitburger': ('Bier', 'Bitburger'),
    'warsteiner': ('Bier', 'Warsteiner'),
    'becks': ('Bier', "Beck's"),
    "beck's": ('Bier', "Beck's"),
    'erdinger': ('Bier', 'Erdinger'),
    'franziskaner': ('Bier', 'Franziskaner'),
    'tegernseer': ('Bier', 'Tegernseer'),
    'rothaus': ('Bier', 'Rothaus'),
    'heineken': ('Bier', 'Heineken'),
    'corona': ('Bier', 'Corona'),
    'desperados': ('Bier', 'Desperados'),
    'astra': ('Bier', 'Astra'),
    'jever': ('Bier', 'Jever'),
    'veltins': ('Bier', 'Veltins'),
    'hasseröder': ('Bier', 'Hasseröder'),
    'oettinger': ('Bier', 'Oettinger'),
    'schöfferhofer': ('Bier', 'Schöfferhofer'),
    'flensburger': ('Bier', 'Flensburger'),
    'guinness': ('Bier', 'Guinness'),

    # Wasser
    'gerolsteiner': ('Mineralwasser', 'Gerolsteiner'),
    'volvic': ('Wasser', 'Volvic'),
    'vittel': ('Wasser', 'Vittel'),
    'evian': ('Wasser', 'Evian'),
    'san pellegrino': ('Mineralwasser', 'San Pellegrino'),
    'adelholzener': ('Mineralwasser', 'Adelholzener'),
    'rhönsprudel': ('Mineralwasser', 'RhönSprudel'),
    'apollinaris': ('Mineralwasser', 'Apollinaris'),
    'black forest': ('Wasser', 'Black Forest'),

    # Softdrinks & Energy
    'coca cola': ('Cola', 'Coca-Cola'),
    'coca-cola': ('Cola', 'Coca-Cola'),
    'coke zero': ('Cola', 'Coke Zero'),
    'coca cola zero': ('Cola', 'Coca-Cola Zero'),
    'pepsi': ('Cola', 'Pepsi'),
    'pepsi max': ('Cola', 'Pepsi Max'),
    'fanta': ('Limonade', 'Fanta'),
    'sprite': ('Limonade', 'Sprite'),
    'mezzo mix': ('Spezi', 'Mezzo Mix'),
    'schwip schwap': ('Spezi', 'Schwip Schwap'),
    'paulaner spezi': ('Spezi', 'Paulaner Spezi'),
    'bionade': ('Limonade', 'Bionade'),
    'fritz kola': ('Cola', 'Fritz-Kola'),
    'fritz-kola': ('Cola', 'Fritz-Kola'),
    'fritz limo': ('Limonade', 'Fritz Limo'),
    'club mate': ('Eistee', 'Club-Mate'),
    'mio mio mate': ('Eistee', 'Mio Mio Mate'),
    'red bull': ('Energy Drink', 'Red Bull'),
    'monster energy': ('Energy Drink', 'Monster Energy'),
    'monster': ('Energy Drink', 'Monster'),
    'rockstar': ('Energy Drink', 'Rockstar'),
    'effect': ('Energy Drink', 'Effect'),

    # Saft
    'hohes c': ('Saft', 'Hohes C'),
    'granini': ('Saft', 'Granini'),
    'valensina': ('Saft', 'Valensina'),
    'amecke': ('Saft', 'Amecke'),
    'innocent': ('Smoothie', 'Innocent'),
    'true fruits': ('Smoothie', 'True Fruits'),

    # Kaffee & Tee
    'lavazza': ('Kaffee', 'Lavazza'),
    'dallmayr': ('Kaffee', 'Dallmayr'),
    'melitta': ('Kaffee', 'Melitta'),
    'tchibo': ('Kaffee', 'Tchibo'),
    'segafredo': ('Kaffee', 'Segafredo'),
    'nespresso': ('Kaffeekapseln', 'Nespresso'),
    'senseo': ('Kaffeepads', 'Senseo'),
    'dolce gusto': ('Kaffeekapseln', 'Dolce Gusto'),
    'teekanne': ('Tee', 'Teekanne'),
    'messmer': ('Tee', 'Meßmer'),
    'meßmer': ('Tee', 'Meßmer'),
    'yogi tea': ('Tee', 'Yogi Tea'),
    'oatly': ('Hafermilch', 'Oatly'),

    # Süßigkeiten & Snacks
    'ritter sport': ('Schokolade', 'Ritter Sport'),
    'milka': ('Schokolade', 'Milka'),
    'lindt': ('Schokolade', 'Lindt'),
    'ferrero rocher': ('Pralinen', 'Ferrero Rocher'),
    'mon cheri': ('Pralinen', 'Mon Chéri'),
    'mon chéri': ('Pralinen', 'Mon Chéri'),
    'kinder bueno': ('Schokoriegel', 'Kinder Bueno'),
    'kinder riegel': ('Schokoriegel', 'Kinder Riegel'),
    'kinder country': ('Schokoriegel', 'Kinder Country'),
    'kinder pingui': ('Milchschnitte', 'Kinder Pingui'),
    'kinder maxi king': ('Milchschnitte', 'Kinder Maxi King'),
    'kinder schokolade': ('Schokolade', 'Kinder Schokolade'),
    'raffaello': ('Pralinen', 'Raffaello'),
    'giotto': ('Pralinen', 'Giotto'),
    'nutella': ('Nutella', ''),
    'duplo': ('Schokoriegel', 'Duplo'),
    'hanuta': ('Waffeln', 'Hanuta'),
    'toffifee': ('Pralinen', 'Toffifee'),
    'knoppers': ('Waffeln', 'Knoppers'),
    'haribo': ('Gummibärchen', 'Haribo'),
    'katjes': ('Gummibärchen', 'Katjes'),
    'trolli': ('Gummibärchen', 'Trolli'),
    'nimm 2': ('Bonbons', 'Nimm 2'),
    'pringles': ('Chips', 'Pringles'),
    'funny frisch': ('Chips', 'Funny-Frisch'),
    'funny-frisch': ('Chips', 'Funny-Frisch'),
    'chio': ('Chips', 'Chio'),
    'prinzenrolle': ('Kekse', 'Prinzenrolle'),
    'oreo': ('Kekse', 'Oreo'),
    'kitkat': ('Schokoriegel', 'KitKat'),
    'twix': ('Schokoriegel', 'Twix'),
    'snickers': ('Schokoriegel', 'Snickers'),
    'mars': ('Schokoriegel', 'Mars'),
    'bounty': ('Schokoriegel', 'Bounty'),
    'm&ms': ('Schokolinsen', 'M&Ms'),

    # Drogerie & Hygiene
    'tempo': ('Taschentücher', 'Tempo'),
    'zewa': ('Küchenrollen', 'Zewa'),
    'hakle': ('Toilettenpapier', 'Hakle'),
    'pampers': ('Windeln', 'Pampers'),
    'persil': ('Waschmittel', 'Persil'),
    'ariel': ('Waschmittel', 'Ariel'),
    'spee': ('Waschmittel', 'Spee'),
    'perwoll': ('Waschmittel', 'Perwoll'),
    'lenor': ('Weichspüler', 'Lenor'),
    'pril': ('Spülmittel', 'Pril'),
    'fairy': ('Spülmittel', 'Fairy'),
    'somat': ('Spülmaschinentabs', 'Somat'),
    'finish': ('Spülmaschinentabs', 'Finish'),
    'calgon': ('Wasserenthärter', 'Calgon'),
    'meister proper': ('Allzweckreiniger', 'Meister Proper'),
    'sagrotan': ('Desinfektionsmittel', 'Sagrotan'),
    'head & shoulders': ('Shampoo', 'Head & Shoulders'),
    'schauma': ('Shampoo', 'Schauma'),
    'colgate': ('Zahnpasta', 'Colgate'),
    'blend-a-med': ('Zahnpasta', 'Blend-a-med'),
    'sensodyne': ('Zahnpasta', 'Sensodyne'),
    'elmex': ('Zahnpasta', 'Elmex'),
    'gillette': ('Rasierklingen', 'Gillette')
}

def extract_brand_item(query_name, existing_spec=''):
    """
    Trennt Markennamen dynamisch vom Lebensmittel-Substantiv ab, damit Bring! das passende Icon anzeigt:
    1. Explizites Nomen + Marke (z. B. 'Gustavo Gusto Pizza' -> Name: 'Pizza' 🍕, Spec: 'Gustavo Gusto')
    2. Eindeutige Monoprodukt-Marke ohne Nomen (z. B. 'Augustiner' -> Name: 'Bier' 🍺, Spec: 'Augustiner')
    3. Mehrdeutige Marke ohne Nomen (z. B. 'Dr. Oetker') -> Name: 'Dr. Oetker' (bleibt ohne Raten erhalten)
    """
    q_low = query_name.lower().strip()

    # 1. Explizites Nomen + Marke (z. B. 'Barilla Spaghetti', 'Mutti Tomatenmark', 'Dr. Oetker Backmischung')
    for brand_key in sorted(BRAND_MAP.keys(), key=len, reverse=True):
        brand_display = BRAND_MAP[brand_key]
        if q_low.startswith(brand_key):
            remainder = q_low[len(brand_key):].strip()
            if remainder and len(remainder) >= 2:
                cat_name = " ".join([w.capitalize() for w in remainder.split()])
                spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
                return cat_name, spec
        elif q_low.endswith(brand_key):
            noun_part = q_low[:-len(brand_key)].strip()
            if noun_part and len(noun_part) >= 2:
                cat_name = " ".join([w.capitalize() for w in noun_part.split()])
                spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
                return cat_name, spec

    # 2. Eindeutige Monoprodukt-Marke ohne Nomen -> Icon-Kategorie zuweisen!
    if q_low in UNAMBIGUOUS_BRAND_CATEGORIES:
        cat_name, brand_display = UNAMBIGUOUS_BRAND_CATEGORIES[q_low]
        spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
        return cat_name, spec

    # 3. Mehrdeutige Marke ohne Nomen -> Name sauber formatiert stehen lassen
    if q_low in BRAND_MAP:
        return BRAND_MAP[q_low], existing_spec

    return query_name, existing_spec

COMMON_STT_TYPOS = {
    'bankmischung': 'backmischung',
    'küche': 'kiste',
    'bunt': 'bund'
}

def is_brand_token(token):
    """
    Prüft, ob ein Wort eine Marke ist oder der Beginn eines mehrteiligen Markennamens.
    """
    tok = token.lower().strip()
    return any(k == tok or k.startswith(tok + ' ') for k in BRAND_MAP.keys()) or tok in UNAMBIGUOUS_BRAND_CATEGORIES or tok in ['cola', 'fanta', 'sprite', 'spezi', 'bier', 'wasser']

def is_brand_extension(words, i):
    """
    Erkennt mehrteilige Marken- und Produktkombinationen dynamisch:
    - 3-Wort Marke + Adjektiv + Nomen: 'oro di parma passierte tomaten'
    - 3-Wort Marke + Nomen: 'coppenrath und wiese apfelkuchen'
    - 2-Wort Marke + Adjektiv + Nomen: 'dr oetker vegane pizza'
    - 2-Wort Marke + Nomen: 'dr oetker backmischung', 'gustavo gusto pizza'
    - 1-Wort Marke + Adjektiv + Nomen: 'krombacher alkoholfreies bier'
    - 1-Wort Marke + Nomen: 'barilla spaghetti', 'mutti tomatenmark'
    - Standalone Produkte: 'coca cola zero', 'red bull', 'ritter sport'
    Verhindert das Zusammenziehen aufeinanderfolgender Marken (z. B. 'Persil' + 'Ritter Sport')
    und das Konsumieren von Mengenangaben als Nomen (z. B. 'Cola' + '1 Kiste').
    """
    w_low = words[i].lower().strip()

    # 1. 3-Wort Marke + Adjektiv + Nomen (5 Wörter) -> z. B. 'oro di parma passierte tomaten'
    if i + 4 < len(words):
        tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
        next_tok = words[i+4].lower().strip()
        if tri in BRAND_MAP and words[i+3].lower() in GROCERY_ADJECTIVES and not is_brand_token(words[i+4]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 5, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]} {words[i+4]}"

    # 2. 3-Wort Marke + Nomen (4 Wörter)
    if i + 3 < len(words):
        tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
        next_tok = words[i+3].lower().strip()
        if tri in BRAND_MAP and not is_brand_token(words[i+3]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 4, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"

    # 3. 2-Wort Marke + Adjektiv + Nomen (4 Wörter)
    if i + 3 < len(words):
        pair = f"{w_low} {words[i+1].lower()}"
        next_tok = words[i+3].lower().strip()
        if pair in BRAND_MAP and words[i+2].lower() in GROCERY_ADJECTIVES and not is_brand_token(words[i+3]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 4, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"

    # 4. 2-Wort Marke + Nomen (3 Wörter) -> z. B. 'gustavo gusto pizza', 'doktor oetker backmischung'
    if i + 2 < len(words):
        pair = f"{w_low} {words[i+1].lower()}"
        next_tok = words[i+2].lower().strip()
        if pair in BRAND_MAP and not is_brand_token(words[i+2]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

    # 5. 1-Wort Marke + Adjektiv + Nomen (3 Wörter) -> z. B. 'krombacher alkoholfreies bier'
    if i + 2 < len(words):
        next_tok = words[i+2].lower().strip()
        if w_low in BRAND_MAP and words[i+1].lower() in GROCERY_ADJECTIVES and not is_brand_token(words[i+2]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

    # 6. 1-Wort Marke + Nomen (2 Wörter) -> z. B. 'barilla spaghetti', 'mutti tomatenmark'
    if i + 1 < len(words):
        next_tok = words[i+1].lower().strip()
        if w_low in BRAND_MAP and not is_brand_token(words[i+1]) and not re.match(r'^\d', next_tok) and next_tok not in UNITS_LIST:
            return 2, f"{words[i]} {words[i+1]}"

    # 7. Standalone / Mehrwort-Marke alleinstehend (3 Wörter)
    if i + 2 < len(words):
        tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
        if tri in STANDALONE_PRODUCTS or tri in BRAND_MAP:
            return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

    # 8. Standalone / Mehrwort-Marke alleinstehend (2 Wörter) -> z. B. 'ritter sport', 'red bull', 'dr oetker'
    if i + 1 < len(words):
        pair = f"{w_low} {words[i+1].lower()}"
        if pair in STANDALONE_PRODUCTS or pair in BRAND_MAP:
            return 2, f"{words[i]} {words[i+1]}"

    return 0, None

def is_multiword_pair(w1, w2, catalog_names):
    """
    Prüft, ob zwei aufeinanderfolgende Wörter eine zusammenhängende Einheit bilden.
    """
    low1, low2 = w1.lower().strip(), w2.lower().strip()
    full_space = f"{low1} {low2}"
    full_compound = f"{low1}{low2}"

    # 1. Exakter Katalog-Match (mit oder ohne Leerzeichen)
    for cat in catalog_names:
        clow = cat.lower()
        if clow == full_space or clow == full_compound:
            return True

    # 2. Fremdwort-Treffer (z. B. 'Pollo fino', 'Creme Fraiche', 'Gustavo Gusto')
    if full_space in FOREIGN_TERMS or full_compound in FOREIGN_TERMS or full_space in BRAND_PAIRS or full_compound in BRAND_PAIRS:
        return True

    # 3. Bekanntes Basis-Kompositum (z. B. 'Wurstaufschnitt', 'Salatgurke')
    if full_compound in VALID_BASE_COMPOUNDS or full_space in VALID_BASE_COMPOUNDS:
        return True

    # 4. Numerische Modell-/Größenangabe (z. B. '8er Dübel', '6er Schrauben')
    if re.match(r'^\d+er$', low1):
        return True

    # 5. Adjektiv + Nomen (z. B. 'Saure Sahne', 'Griechischer Joghurt')
    if low1 in GROCERY_ADJECTIVES:
        return True

    # 6. Bestimmendes Präfix (z. B. 'Puten Brust', 'Hafer Milch', 'Vanille Zucker')
    if low1 in COMPOUND_PREFIXES:
        return True

    # 7. Unselbstständiges Suffix (z. B. 'Wurst Aufschnitt', 'Spülmaschinen Tabs')
    if low2 in DEPENDENT_SUFFIXES:
        return True

    return False

def split_compound_of_known_items(word, catalog_names):
    """
    Trennt Wörter, die von Alexas Speech-to-Text fälschlicherweise ohne Leerzeichen
    zusammengezogen wurden (z. B. 'schraubenbohrmaschine' -> 'Schrauben', 'Bohrmaschine').
    Schützt echte Katalog-Artikel wie 'Wurstaufschnitt'.
    """
    w_low = word.lower().strip()
    for cat in catalog_names:
        clow = cat.lower()
        if clow == w_low or clow.replace(" ", "") == w_low:
            return [word]
    if w_low in VALID_BASE_COMPOUNDS or w_low.replace(" ", "") in VALID_BASE_COMPOUNDS:
        return [word]
    if w_low in FOREIGN_TERMS or w_low.replace(" ", "") in FOREIGN_TERMS or w_low in BRAND_PAIRS or w_low.replace(" ", "") in BRAND_PAIRS:
        return [word]

    for cat1 in catalog_names:
        c1_low = cat1.lower()
        if len(c1_low) >= 3 and w_low.startswith(c1_low):
            remainder = w_low[len(c1_low):].strip()
            for cat2 in catalog_names:
                c2_low = cat2.lower()
                if remainder == c2_low:
                    return [cat1, cat2]
    return [word]

def smart_split_consecutive(text, catalog_names):
    """
    Zerlegt unverbundene Listen ('Milch Butter Brot') und fälschlich zusammengezogene
    Wörter ('schraubenbohrmaschine'), während mehrteilige Begriffe
    ('Saure Sahne', 'Puten Brust', '8er Dübel', 'Gustavo Gusto Pizza', 'Cola 1 Kiste') geschützt und zusammengehalten werden.
    """
    t = text.strip()
    words = t.split()
    if len(words) <= 1:
        return split_compound_of_known_items(t, catalog_names)

    low = t.lower()
    for cat in catalog_names:
        clow = cat.lower()
        if clow == low or clow == low.replace(" ", ""):
            return [t]
    if low in FOREIGN_TERMS or low.replace(" ", "") in FOREIGN_TERMS or low in BRAND_MAP or low in STANDALONE_PRODUCTS:
        return [t]

    results = []
    i = 0
    while i < len(words):
        w = words[i]
        w_low = w.lower()

        # Führende Mengenangabe (z. B. '2 erdbeeren', '1 kiste sprudel')
        if re.match(r'^\d+(?:[.,]\d+)?$', w_low):
            if i + 2 < len(words) and words[i+1].lower() in UNITS_LIST:
                rem_phrase = " ".join(words[i+2:])
                sub_parsed = smart_split_consecutive(rem_phrase, catalog_names)
                if sub_parsed:
                    results.append(f"{w} {words[i+1]} {sub_parsed[0]}")
                    results.extend(sub_parsed[1:])
                else:
                    results.append(f"{w} {words[i+1]}")
                break
            elif i + 1 < len(words):
                rem_phrase = " ".join(words[i+1:])
                sub_parsed = smart_split_consecutive(rem_phrase, catalog_names)
                if sub_parsed:
                    results.append(f"{w} {sub_parsed[0]}")
                    results.extend(sub_parsed[1:])
                else:
                    results.append(f"{w}")
                break

        # 1. Prüfe mehrteilige Marken-Kombinationen
        consumed, brand_phrase = is_brand_extension(words, i)
        if consumed > 0:
            rem = words[i+consumed:]
            if len(rem) >= 2 and re.match(r'^\d+(?:[.,]\d+)?$', rem[0].lower()) and rem[1].lower() in UNITS_LIST:
                results.append(f"{brand_phrase} {rem[0]} {rem[1]}")
                i += consumed + 2
                continue
            results.append(brand_phrase)
            i += consumed
            continue

        # 2. Prüfe 2-Wort-Paar
        if i + 1 < len(words):
            next_w = words[i + 1]
            if is_multiword_pair(w, next_w, catalog_names):
                results.append(f"{w} {next_w}")
                i += 2
                continue

        # 3. Prüfe nachgestellte Mengenangabe bei regulärem Nomen (z. B. 'cola' + '1 kiste')
        rem = words[i+1:]
        if len(rem) >= 2 and re.match(r'^\d+(?:[.,]\d+)?$', rem[0].lower()) and rem[1].lower() in UNITS_LIST:
            results.append(f"{w} {rem[0]} {rem[1]}")
            i += 3
            continue

        results.append(w)
        i += 1

    return results

def match_catalog_name(query_name, catalog_names):
    """
    Intelligenter Abgleich gegen den Bring!-Katalog mit automatischer Duden-Orthographie:
    1. Exakter Match (case-insensitive)
    2. Compound Match (z. B. 'Wurst Aufschnitt' -> 'Wurstaufschnitt')
    3. Linguistischer Wortstamm-Match (Singularisierung / Pluralabgleich bei Ein-Wort Queries)
    4. Duden-konforme Formatierung:
       - Fremdwörter -> Getrennt (z. B. 'Pollo Fino', 'Creme Fraiche')
       - Modell-/Größenangaben -> Getrennt (z. B. '8er Dübel', '6er Schrauben')
       - Adjektiv + Substantiv -> Getrennt (z. B. 'Saure Sahne', 'Alkoholfreies Bier')
       - Deutsches Nomen-Kompositum -> Zusammengeschrieben (z. B. 'Mandelmilch', 'Apfelsaft', 'Alufolie')
    """
    q_clean = query_name.strip()
    q_low = q_clean.lower()
    q_compound = q_low.replace(" ", "")
    q_stem = stem_german(q_low)

    # 1. Exakter Match
    for cat in catalog_names:
        if cat.lower() == q_low:
            return cat

    # 2. Compound Match
    for cat in catalog_names:
        if cat.lower().replace(" ", "") == q_compound:
            return cat

    # 3. Wortstamm Match (Einzahl / Mehrzahl Abgleich bei Einzelwörtern)
    if len(q_stem) >= 3 and " " not in q_low:
        for cat in catalog_names:
            c_stem = stem_german(cat)
            if c_stem == q_stem:
                return cat

    # 4. Fremdwörter -> Getrennt mit sauberer Großschreibung
    if q_low in FOREIGN_TERMS or q_compound in FOREIGN_TERMS:
        words = [w.capitalize() for w in q_clean.split()]
        return " ".join(words)

    words = q_clean.split()
    if len(words) == 2:
        w1_low = words[0].lower()
        # 5. Numerische Modell-/Größenangaben -> Getrennt (z. B. '8er Dübel')
        if re.match(r'^\d+er$', w1_low):
            return f"{words[0]} {words[1].capitalize()}"
        # 6. Adjektiv + Nomen -> Getrennt (z. B. 'Saure Sahne', 'Alkoholfreies Bier')
        if w1_low in GROCERY_ADJECTIVES:
            return f"{words[0].capitalize()} {words[1].capitalize()}"
        # 7. Deutsches Nomen-Kompositum -> Zusammengeschrieben (z. B. 'Mandelmilch', 'Wurstaufschnitt')
        return f"{words[0].capitalize()}{words[1].lower()}"

    # Standard Fallback: Saubere Großschreibung
    res_words = [w.capitalize() for w in words]
    return " ".join(res_words)


# ==================================================================================================
# 8. NLU HAUPT-PARSER & ORCHESTRIERUNG
# ==================================================================================================

def parse_items(raw_text, catalog_names):
    """
    Haupt-Parser: Zerlegt einen gesprochenen Satz in eine Liste von Bring!-Einkaufsartikeln.
    Rückgabe: Liste von Dictionaries [{'name': '...', 'specification': '...'}, ...]
    """
    if not raw_text or not isinstance(raw_text, str):
        return []

    norm = normalize_spoken_german(raw_text)
    cleaned = strip_command_phrases(norm)
    if not cleaned:
        return []

    # Phonetische STT-Tippfehler korrigieren
    for typo, repl in COMMON_STT_TYPOS.items():
        cleaned = re.sub(rf'\b{typo}\b', repl, cleaned, flags=re.IGNORECASE)

    # Prüfe, ob der gesamte Ausdruck direkt einem Katalogartikel entspricht (z. B. 'Erbsen und Möhren', 'Salz und Pfeffer')
    cleaned_low = cleaned.lower()
    for cat in catalog_names:
        clow = cat.lower()
        if clow == cleaned_low or clow.replace(" ", "") == cleaned_low.replace(" ", ""):
            return [{'name': cat, 'specification': ''}]

    # 1. Split an 'und', 'sowie', ','
    first_split = re.split(r'\s+(?:und|sowie|\+)\s+|,\s*', cleaned, flags=re.IGNORECASE)

    # 2. Split an Ziffern mit Einheiten
    units_pattern = '|'.join(sorted(UNITS_LIST, key=len, reverse=True))
    split_pattern = rf'(?<=[a-zA-ZäöüÄÖÜß])\s+(?=\d+(?:[.,]\d+)?\s+(?:(?:{units_pattern})\s+)[a-zA-ZäöüÄÖÜß]+|\d+(?:[.,]\d+)?\s+(?!(?:{units_pattern})\b)[a-zA-ZäöüÄÖÜß]+)'
    split_regex_smart = re.compile(split_pattern, re.IGNORECASE)

    chunks = []
    for fs in first_split:
        fs = fs.strip()
        if not fs:
            continue
        splits = split_regex_smart.split(fs)
        chunks.extend([s.strip() for s in splits if s.strip()])

    items = []
    for chunk in chunks:
        sub_items = smart_split_consecutive(chunk, catalog_names)
        for sub in sub_items:
            name, spec = extract_specification(sub)
            if not name:
                continue
            matched_name = match_catalog_name(name, catalog_names)
            final_name, final_spec = extract_brand_item(matched_name, spec)
            if is_valid_grocery_item(final_name, catalog_names):
                items.append({'name': final_name, 'specification': final_spec})

    return items


# ==================================================================================================
# 9. BRING! REST-API V2 CLIENT & AUTHENTIFIZIERUNG
# ==================================================================================================

def get_credentials():
    """
    Liest Bring!-Anmeldedaten sicher aus secrets.yaml.
    """
    if not os.path.exists(SECRETS_FILE):
        raise FileNotFoundError(f"secrets.yaml nicht gefunden: {SECRETS_FILE}")
    with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
        sec = yaml.safe_load(f)
    email = sec.get('bring_email')
    password = sec.get('bring_password')
    list_name = sec.get('bring_list_name', 'Einkaufsliste')
    if not email or not password:
        raise ValueError("bring_email oder bring_password in secrets.yaml fehlt!")
    return email, password, list_name

def authenticate():
    """
    Authentifiziert sich bei der Bring! v2 API und cacht den Token in .storage/bring_auth_cache.json.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                c = json.load(f)
                if c.get('access_token') and c.get('uuid'):
                    return c
        except Exception:
            pass

    email, password, _ = get_credentials()
    payload = urllib.parse.urlencode({'email': email, 'password': password}).encode('utf-8')
    req = urllib.request.Request(f"{API_BASE}/v2/bringauth", data=payload, headers={
        'X-BRING-API-KEY': API_KEY,
        'X-BRING-CLIENT': CLIENT,
        'X-BRING-APPLICATION': APPLICATION,
        'X-BRING-COUNTRY': COUNTRY,
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    auth_data = {
        'access_token': data.get('access_token'),
        'token_type': data.get('token_type', 'Bearer'),
        'uuid': data.get('uuid') or data.get('userUuid', ''),
        'publicUuid': data.get('publicUuid') or data.get('uuid', ''),
        'bringListUUID': data.get('bringListUUID', '')
    }

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(auth_data, f, ensure_ascii=False, indent=2)

    return auth_data

def get_target_list_uuid(auth, target_name):
    """
    Ermittelt die eindeutige UUID der Bring!-Zielliste.
    """
    if auth.get('bringListUUID') and (not target_name or target_name.lower() in ['einkaufsliste', 'einkauf']):
        return auth['bringListUUID']

    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'X-BRING-API-KEY': API_KEY,
        'X-BRING-CLIENT': CLIENT,
        'X-BRING-APPLICATION': APPLICATION,
        'X-BRING-COUNTRY': COUNTRY,
        'X-BRING-USER-UUID': auth['uuid'],
        'X-BRING-PUBLIC-USER-UUID': auth['publicUuid']
    }
    req = urllib.request.Request(f"{API_BASE}/bringusers/{auth['uuid']}/lists", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        lists = data.get('lists', [])
        for l in lists:
            if l.get('name', '').lower() == target_name.lower():
                return l.get('listUuid')
        if lists:
            return lists[0].get('listUuid')

    return auth.get('bringListUUID')

def get_cached_catalog(auth, list_uuid):
    """
    Lädt und cacht alle bekannten Bring!-Katalog- und Verlaufsartikel für die Liste.
    """
    if os.path.exists(CATALOG_CACHE_FILE):
        try:
            with open(CATALOG_CACHE_FILE, 'r', encoding='utf-8') as f:
                cat = json.load(f)
                if cat and len(cat) > 0:
                    return cat
        except Exception:
            pass

    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'X-BRING-API-KEY': API_KEY,
        'X-BRING-CLIENT': CLIENT,
        'X-BRING-APPLICATION': APPLICATION,
        'X-BRING-COUNTRY': COUNTRY,
        'X-BRING-USER-UUID': auth['uuid'],
        'X-BRING-PUBLIC-USER-UUID': auth['publicUuid']
    }
    try:
        url = f"{API_BASE}/v2/bringlists/{list_uuid}/details"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read().decode('utf-8'))
            names = [i.get('itemId') for i in items if i.get('itemId')]
            os.makedirs(os.path.dirname(CATALOG_CACHE_FILE), exist_ok=True)
            with open(CATALOG_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(names, f, ensure_ascii=False, indent=2)
            return names
    except Exception:
        return []

def fetch_active_bring_items():
    """
    Holt alle aktiven Einkaufsartikel von Bring! und speichert sie als JSON-Array in .bring_active.json.
    Dient als Datenquelle für den Home Assistant Sensor sensor.bring_active_items.
    Inklusive automatischer Token-Erneuerung bei 401 Unauthorized.
    """
    try:
        email, password, list_name = get_credentials()
        auth = authenticate()
        list_uuid = get_target_list_uuid(auth, list_name)

        headers = {
            'Authorization': f"{auth['token_type']} {auth['access_token']}",
            'X-BRING-API-KEY': API_KEY,
            'X-BRING-CLIENT': CLIENT,
            'X-BRING-APPLICATION': APPLICATION,
            'X-BRING-COUNTRY': COUNTRY,
            'X-BRING-USER-UUID': auth['uuid'],
            'X-BRING-PUBLIC-USER-UUID': auth['publicUuid']
        }

        url = f"{API_BASE}/v2/bringlists/{list_uuid}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
                auth = authenticate()
                headers['Authorization'] = f"{auth['token_type']} {auth['access_token']}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
            else:
                raise

        raw_purchase = data.get('purchase') or (data.get('items', {}).get('purchase') if isinstance(data.get('items'), dict) else []) or []
        items = []
        for item in raw_purchase:
            name = item.get('name') or item.get('itemId')
            spec = item.get('specification') or ''
            full = f"{name} ({spec})".strip() if spec else name.strip()
            items.append(full)

        os.makedirs(os.path.dirname(ACTIVE_ITEMS_FILE), exist_ok=True)
        with open(ACTIVE_ITEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        res = {'items': items, 'count': len(items)}
        print(json.dumps(res, ensure_ascii=False))
        return items
    except Exception as e:
        print(json.dumps({'items': [], 'count': 0, 'error': str(e)}))
        return []


# ==================================================================================================
# 10. SYNCHRONISATIONS-EXECUTION & MAIN-ENTRYPOINT
# ==================================================================================================

def execute_bring_sync(spoken_text):
    """
    Führt die vollständige Synchronisation eines erfassten Sprachbefehls zu Bring! aus.
    Inklusive automatischer Token-Erneuerung bei 401 Unauthorized und Timeout-Absicherung.
    """
    if not spoken_text or not spoken_text.strip():
        print("Kein Text übergeben.")
        return

    if not is_valid_shopping_command(spoken_text):
        print(f"[SKIP] Kein gültiger Einkaufslisten-Befehl: '{spoken_text}'")
        return

    op = detect_operation(spoken_text)
    email, password, list_name = get_credentials()
    auth = authenticate()
    list_uuid = get_target_list_uuid(auth, list_name)
    catalog_names = get_cached_catalog(auth, list_uuid)

    items = parse_items(spoken_text, catalog_names)
    if not items:
        print("[SKIP] Keine gültigen Einkaufsartikel extrahiert.")
        return

    changes = []
    for item in items:
        changes.append({
            'accuracy': '0.0',
            'altitude': '0.0',
            'latitude': '0.0',
            'longitude': '0.0',
            'itemId': item['name'],
            'spec': item['specification'],
            'operation': op
        })

    payload = json.dumps({'changes': changes, 'sender': ''}).encode('utf-8')
    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'X-BRING-API-KEY': API_KEY,
        'X-BRING-CLIENT': CLIENT,
        'X-BRING-APPLICATION': APPLICATION,
        'X-BRING-COUNTRY': COUNTRY,
        'X-BRING-USER-UUID': auth['uuid'],
        'X-BRING-PUBLIC-USER-UUID': auth['publicUuid'],
        'Content-Type': 'application/json'
    }

    url = f"{API_BASE}/v2/bringlists/{list_uuid}/items"
    req = urllib.request.Request(url, data=payload, headers=headers, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[OK] Bring Sync erfolgreich ({op}): {items}")
            fetch_active_bring_items()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
            auth = authenticate()
            headers['Authorization'] = f"{auth['token_type']} {auth['access_token']}"
            req = urllib.request.Request(url, data=payload, headers=headers, method='PUT')
            with urllib.request.urlopen(req, timeout=10) as resp2:
                print(f"[OK Retry] Bring Sync erfolgreich ({op}): {items}")
                fetch_active_bring_items()
        else:
            raise

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--fetch-active':
            fetch_active_bring_items()
        else:
            text = " ".join(sys.argv[1:])
            execute_bring_sync(text)
    else:
        print("Nutzung: python bring_sync.py '<gesprochener_text>' oder --fetch-active")
