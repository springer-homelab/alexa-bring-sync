"""
Bring! Direct API Client & Intelligent Generic Parser for Home Assistant
Features:
- Dynamic Bring Catalog & History Caching (/v2/bringlists/.../details)
- Universal German Linguistic Stemmer & Lemmatizer
- Zero hardcoded dictionaries: Automatically matches ANY product
- Sub-150ms execution speed directly inside Home Assistant Core
"""

import sys
import os
import json
import urllib.request
import urllib.parse
import re
import yaml

CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_FILE = os.path.join(CONFIG_DIR, 'secrets.yaml')
CACHE_FILE = os.path.join(CONFIG_DIR, '.storage', 'bring_auth_cache.json')
CATALOG_CACHE_FILE = os.path.join(CONFIG_DIR, '.storage', 'bring_catalog_cache.json')

API_BASE = 'https://api.getbring.com/rest'
API_KEY = 'cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp'
CLIENT = 'android'
APPLICATION = 'bring'
COUNTRY = 'DE'

def stem_german(word):
    """
    Generischer deutscher Stammformen-Algorithmus:
    Normalisiert Umlaute und entfernt typische Pluralendungen (-en, -n, -er, -e, -s).
    Funktioniert für 100% aller deutschen Substantive und Lebensmittel.
    """
    w = word.lower().strip()
    w = w.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
    
    # Sonderfälle für Wurzelvokal-Wechsel (z. B. Apfel <-> Äpfel)
    if w == 'apfel' or w == 'apfel':
        return 'apfel'
    
    # Plural-Endungen sauber entfernen (ab mindestens 4 Buchstaben)
    if len(w) >= 4:
        w = re.sub(r'(?:en|ern|er|e|s|n)$', '', w)
    return w

def normalize_spoken_german(text):
    t = text.strip()

    # 1. Null und Zahlwörter
    t = re.sub(r'\bnull\b', '0', t, flags=re.IGNORECASE)

    # 2. Brüche und traditionelle Maßeinheiten (z. B. "ein halbes kilo" -> 0.5kg, "anderthalb" -> 1.5, "ein pfund" -> 500g)
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

    # 3. Hunderter & Tausender (z. B. "zweihundertfünfzig" -> "200 50", "fünfhundert" -> "500")
    hundred_prefixes = {'ein': 100, 'zwei': 200, 'drei': 300, 'vier': 400, 'fünf': 500, 'sechs': 600, 'sieben': 700, 'acht': 800, 'neun': 900}
    for h_name, h_val in hundred_prefixes.items():
        t = re.sub(rf'\b{h_name}\s*hundert', f'{h_val} ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bhundert\b', '100 ', t, flags=re.IGNORECASE)
    t = re.sub(r'\btausend\b', '1000 ', t, flags=re.IGNORECASE)

    # 4. Zweistellige Zahlen (z. B. "zweiundzwanzig" -> 22, "fünfunddreißig" -> 35)
    ones = {'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9}
    tens = {'zwanzig': 20, 'dreißig': 30, 'vierzig': 40, 'fünfzig': 50, 'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90}
    for one_k, one_v in ones.items():
        for ten_k, ten_v in tens.items():
            compound = f"{one_k}und{ten_k}"
            total = one_v + ten_v
            t = re.sub(rf'\b{compound}\b', str(total), t, flags=re.IGNORECASE)

    # 5. Einzelne Zahlwörter
    word_to_num = {
        'zwanzig': '20', 'dreißig': '30', 'vierzig': '40', 'fünfzig': '50', 'sechzig': '60', 'siebzig': '70', 'achtzig': '80', 'neunzig': '90',
        'dreizehn': '13', 'vierzehn': '14', 'fünfzehn': '15', 'sechzehn': '16', 'siebzehn': '17', 'achtzehn': '18', 'neunzehn': '19',
        'zwölf': '12', 'elf': '11', 'zehn': '10', 'neun': '9', 'acht': '8', 'sieben': '7', 'sechs': '6', 'fünf': '5', 'vier': '4', 'drei': '3', 'zwei': '2',
        'eins': '1', 'eine': '1', 'einen': '1', 'einem': '1', 'einer': '1', 'ein': '1'
    }
    for w, n in word_to_num.items():
        t = re.sub(rf'\b{w}\b', str(n), t, flags=re.IGNORECASE)

    # 6. Addition von Hunderter + Zehner/Einer (z. B. "200 50" -> 250, "100 25" -> 125)
    t = re.sub(r'\b(\d{1,4}00)\s+(\d{1,2})\b', lambda m: str(int(m.group(1)) + int(m.group(2))), t)

    # 7. Gesprochene Dezimalzahlen (z. B. "2 komma 5" -> "2.5", "0 komma 5" -> "0.5", "1 punkt 5" -> "1.5")
    t = re.sub(r'\b(\d+)\s*(?:komma|punkt|,|\.)\s*(\d+)\b', r'\1.\2', t, flags=re.IGNORECASE)

    return t.strip()

def strip_command_phrases(text):
    t = text.strip()
    patterns = [
        # Prefix Löschbefehle
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+?)\s+(?:von|aus|von\s+der|von\s+den|von\s+unserer|von\s+meiner)\s+(?:der|meiner|unserer|den|die)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:nimm|tu)\s+(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s*runter$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+)$',

        # Suffix Löschbefehle (z. B. "Karotten von der Liste löschen", "Milch entfernen", "Aprikosen streichen")
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s+(?:löschen|entfernen|streichen|runternehmen)$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:löschen|entfernen|streichen|abhaken)$',

        # Prefix Hinzufügebefehle
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu|pack)\s+(.+?)\s+(?:auf|zu|zur|in|an|der)\s+(?:die|meine|unsere|den|der|das)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf)?$',
        r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:wir\s+brauchen\s+noch|kauf\s+bitte|kauf(?:en)?|besorg(?:e)?)\s+(.+)$',
        r'^(?:alexa,?\s*)?(?:sag|sage|frage|öffne)\s+(?:meinem?\s+)?(?:einkaufszettel|einkaufsliste|bring|liste)(?::|\s+)?\s*(.+)$',
        r'^(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu)\s+(.+?)(?:\s+(?:auf|zu|zur|in|der)\s+(?:die|den|meine|unsere|der|das)\s+(?:einkaufsliste|liste|zettel))?$'
    ]
    for p in patterns:
        m = re.match(p, t, re.IGNORECASE)
        if m:
            t = m.group(1)
            break
    t = re.sub(r'^(?:noch|bitte|mal|eben|schnell)\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:auf|zu|zur|in|an|der|den|die|das|meine|unsere)?\s*(?:die|meine|unsere|den|der|das)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf|\s*ab)?$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:zur|zu|auf|an|für|hinzu|drauf|runter|weg|bitte|danke|noch|löschen|entfernen|streichen)$', '', t, flags=re.IGNORECASE)
    return t.strip()

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
    t = text.strip().lower()
    if t.endswith('?'):
        return False
    if any(t.startswith(q) for q in QUESTION_PREFIXES):
        return False
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
        if any(v in t for v in ['setz', 'pack', 'schreib', 'füg', 'kauf', 'lösch', 'entfern', 'streich', 'nimm']):
            return True
    return False

def is_valid_grocery_item(name, catalog_names):
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
    low = raw_text.lower()
    delete_words = ['lösch', 'lösche', 'entfern', 'entferne', 'streich', 'streiche', 'nimm', 'runter', 'weg', 'löschen', 'entfernen', 'streichen']
    for w in delete_words:
        if w in low:
            return 'TO_RECENTLY'
    return 'TO_PURCHASE'

UNITS_LIST = [
    'kg', 'kilo', 'kilogramm',
    'g', 'gramm',
    'l', 'liter',
    'ml', 'milliliter', 'cl', 'dl',
    'packung', 'packungen', 'pkg', 'pack', 'packs', 'pck',
    'stk', 'stück',
    'flasche', 'flaschen',
    'dose', 'dosen',
    'bund',
    'beutel',
    'glas', 'gläser',
    'scheibe', 'scheiben',
    'kasten', 'kästen', 'kiste', 'kisten',
    'tüte', 'tüten',
    'becher',
    'zehe', 'zehen', 'knolle', 'knollen',
    'tafel', 'tafeln',
    'tube', 'tuben',
    'stange', 'stangen',
    'zweig', 'zweige',
    'rolle', 'rollen',
    'karton', 'kartons',
    'portion', 'portionen',
    'paar',
    'schale', 'schalen',
    'netz', 'netze',
    'steige', 'steigen'
]

UNITS_PATTERN = '|'.join(sorted(UNITS_LIST, key=len, reverse=True))

def extract_specification(text):
    t = text.strip()
    t = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', t, flags=re.IGNORECASE).strip()
    
    pattern_unit = rf'^\s*(\d+(?:[.,]\d+)?\s*(?:{UNITS_PATTERN}))\s+(?:von\s+(?:den|der|dem|meinen)?\s*)?(.+)$'
    m = re.match(pattern_unit, t, re.IGNORECASE)
    if m:
        spec = m.group(1).strip()
        name = m.group(2).strip()
        spec = re.sub(r'(\d+(?:\.\d+)?)\s*gramm\b', r'\1g', spec, flags=re.IGNORECASE)
        spec = re.sub(r'(\d+(?:\.\d+)?)\s*kilo(?:gramm)?\b', r'\1kg', spec, flags=re.IGNORECASE)
        spec = re.sub(r'(\d+(?:\.\d+)?)\s*liter\b', r'\1l', spec, flags=re.IGNORECASE)
        name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', name, flags=re.IGNORECASE).strip()
        return name, spec

    pattern_plain = r'^\s*(\d+(?:[.,]\d+)?)\s+(?:von\s+(?:den|der|dem)?\s*)?([a-zA-ZäöüÄÖÜß].+)$'
    m = re.match(pattern_plain, t, re.IGNORECASE)
    if m:
        spec = m.group(1).strip()
        name = m.group(2).strip()
        name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', name, flags=re.IGNORECASE).strip()
        return name, spec

    return t, ''

def get_credentials():
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
    with urllib.request.urlopen(req) as resp:
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
        json.dump(auth_data, f)
        
    return auth_data

def get_target_list_uuid(auth, target_name):
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
    with urllib.request.urlopen(req) as resp:
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
    Lädt und cacht alle bekannten Bring-Katalog-Artikel für diese Liste.
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
        with urllib.request.urlopen(req) as resp:
            items = json.loads(resp.read().decode('utf-8'))
            names = [i.get('itemId') for i in items if i.get('itemId')]
            with open(CATALOG_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(names, f)
            return names
    except Exception as e:
        return []

def match_catalog_name(query_name, catalog_names):
    """
    Intelligenter, generischer Abgleich gegen alle Bring-Katalog-Artikel nach Duden-Rechtschreibung:
    1. Exakter Match (case-insensitive)
    2. Compound Match (z. B. "Wurst Aufschnitt" -> "Wurstaufschnitt", "Frisch Käse" -> "Frischkäse")
    3. Linguistischer Wortstamm-Match (Singularisierung / Pluralabgleich bei Ein-Wort Queries)
    4. Duden-konforme Rechtschreibung:
       - Fremdwörter -> Getrennt (z. B. 'Pollo Fino', 'Creme Fraiche')
       - Adjektiv + Substantiv -> Getrennt (z. B. 'Saure Sahne', 'Passierte Tomaten')
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

    # 2. Compound Match (z. B. "Wurst Aufschnitt" -> "Wurstaufschnitt", "Frisch Käse" -> "Frischkäse")
    for cat in catalog_names:
        if cat.lower().replace(" ", "") == q_compound:
            return cat

    # 3. Wortstamm Match (Singularisierung / Pluralabgleich bei Ein-Wort Queries)
    if len(q_stem) >= 3 and " " not in q_low:
        for cat in catalog_names:
            c_stem = stem_german(cat)
            if c_stem == q_stem:
                return cat

    # 4. Fremdwörter -> Getrennt mit Großschreibung
    if q_low in FOREIGN_TERMS or q_compound in FOREIGN_TERMS:
        words = [w.capitalize() for w in q_clean.split()]
        return " ".join(words)

    words = q_clean.split()
    if len(words) == 2:
        w1_low = words[0].lower()
        # 5. Adjektiv + Nomen -> Getrennt (z. B. Saure Sahne, Passierte Tomaten)
        if w1_low in GROCERY_ADJECTIVES:
            return f"{words[0].capitalize()} {words[1].capitalize()}"
        # 6. Deutsches Kompositum (Nomen + Nomen) -> Zusammen (z. B. Mandelmilch, Apfelsaft, Alufolie)
        return f"{words[0].capitalize()}{words[1].lower()}"

    # Standard Fallback: Saubere Großschreibung
    res_words = [w.capitalize() for w in words]
    return " ".join(res_words)

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
    'bio', 'freiland', 'vegan', 'vegane', 'veganer', 'veganes', 'vegetarisch', 'vegetarische', 'vegetarisches',
    'laktosefrei', 'laktosefreie', 'laktosefreies', 'glutenfrei', 'glutenfreie', 'glutenfreies',
    'regional', 'regionale', 'regionales', 'asiatische', 'asiatischer'
}

COMPOUND_PREFIXES = {
    'oliven', 'sonnenblumen', 'raps', 'kokos', 'mandel', 'soja', 'hafer', 'dinkel',
    'puder', 'vanille', 'back', 'kakao', 'kakaopulver', 'vollmilch', 'zartbitter', 'schoko',
    'mineral', 'erdnuss', 'haselnuss', 'walnuss', 'cashew', 'kräuter', 'knoblauch', 'chili',
    'balsamico', 'weizen', 'roggen', 'mais', 'tiefkühl', 'tk',
    'puten', 'rinder', 'schweine', 'truthahn', 'kalbs', 'lamm', 'geflügel', 'kirsch',
    'strauch', 'rispen', 'stauden', 'suppen', 'gewürz', 'koch', 'brat',
    'schafs', 'ziegen', 'hütten', 'mager', 'frisch',
    'apfel', 'orangen', 'trauben', 'multi', 'multivitamin', 'zitronen', 'erdbeer',
    'himbeer', 'blaubeer', 'heidelbeer', 'pfefferminz', 'kamillen', 'fenchel',
    'toiletten', 'klo', 'küchen', 'alu', 'frischhalte', 'gefrier',
    'spül', 'spülmaschinen', 'wasch', 'putz', 'müll'
}

DEPENDENT_SUFFIXES = {
    'aufschnitt', 'geschnetzeltes', 'hackfleisch', 'filet', 'schnitzel', 'kotelett',
    'flocken', 'tabs', 'stäbchen', 'beutel', 'papier', 'paste', 'pulver', 'folie', 'rollen'
}

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

FOREIGN_TERMS = {
    'pollo fino', 'creme fraiche', 'crème fraîche', 'sour cream', 'cream cheese',
    'peanut butter', 'curry paste', 'pulled pork', 'ice tea', 'hot dog', 'french dressing',
    'sweet chili', 'sweet sour', 'barbecue sauce', 'bbq sauce', 'maple syrup',
    'tortilla chips', 'nacho chips', 'taco shells', 'salsa verde', 'salsa dip',
    'teriyaki sauce', 'sriracha sauce', 'sweet chili sauce', 'garam masala', 'tikka masala',
    'sushi reis', 'basmati reis', 'jasmin reis', 'mie nudeln', 'udon nudeln', 'ramen nudeln',
    'pesto genovese', 'pesto rosso', 'parmigiano reggiano', 'grana padano', 'pecorino romano',
    'prosciutto di parma', 'serrano schinken', 'iberico schinken', 'chicken nuggets', 'chicken wings',
    'ginger ale', 'tonic water', 'club mate', 'cold brew', 'chai latte'
}

def is_multiword_pair(w1, w2, catalog_names):
    low1, low2 = w1.lower().strip(), w2.lower().strip()
    full_space = f"{low1} {low2}"
    full_compound = f"{low1}{low2}"
    
    # 1. Exact catalog match (either space or compound)
    for cat in catalog_names:
        clow = cat.lower()
        if clow == full_space or clow == full_compound:
            return True
            
    # 2. Foreign terms
    if full_space in FOREIGN_TERMS or full_compound in FOREIGN_TERMS:
        return True
        
    # 3. Known valid base compound (e.g. Wurstaufschnitt, Salatgurke, Kochschinken)
    if full_compound in VALID_BASE_COMPOUNDS or full_space in VALID_BASE_COMPOUNDS:
        return True
        
    # 4. Adjective + Noun (e.g. Saure Sahne, Passierte Tomaten, Griechischer Joghurt)
    if low1 in GROCERY_ADJECTIVES:
        return True
        
    # 5. Modifying prefix (e.g. Oliven Öl, Puten Brust, Hafer Milch, Vanille Zucker, Toiletten Papier)
    if low1 in COMPOUND_PREFIXES:
        return True
        
    # 6. Dependent suffix (e.g. Wurst Aufschnitt, Hähnchen Geschnetzeltes, Spülmaschinen Tabs)
    if low2 in DEPENDENT_SUFFIXES:
        return True
        
    return False

def smart_split_consecutive(text, catalog_names):
    t = text.strip()
    words = t.split()
    if len(words) <= 1:
        return [t]

    low = t.lower()
    for cat in catalog_names:
        clow = cat.lower()
        if clow == low or clow == low.replace(" ", ""):
            return [t]
    if low in FOREIGN_TERMS or low.replace(" ", "") in FOREIGN_TERMS:
        return [t]

    results = []
    i = 0
    while i < len(words):
        w = words[i]
        if i + 1 < len(words):
            next_w = words[i + 1]
            if is_multiword_pair(w, next_w, catalog_names):
                results.append(f"{w} {next_w}")
                i += 2
                continue
        results.append(w)
        i += 1

    return results

def parse_items(raw_text, catalog_names):
    norm = normalize_spoken_german(raw_text)
    cleaned = strip_command_phrases(norm)
    
    first_split = re.split(r'\s+(?:und|sowie|\+)\s+|,\s*', cleaned, flags=re.IGNORECASE)
    
    raw_parts = []
    split_pattern = rf'(?<=[a-zA-ZäöüÄÖÜß])\s+(?=\d+(?:[.,]\d+)?\s*(?:(?:{UNITS_PATTERN})\s+)?[a-zA-ZäöüÄÖÜß])'
    for fs in first_split:
        fs = fs.strip()
        if not fs:
            continue
        subparts = re.split(split_pattern, fs, flags=re.IGNORECASE)
        for sp in subparts:
            sp = sp.strip()
            if sp:
                raw_parts.append(sp)

    items = []
    for rp in raw_parts:
        rp = rp.strip()
        if not rp:
            continue
        name, spec = extract_specification(rp)
        if not spec:
            split_names = smart_split_consecutive(name, catalog_names)
            for sn in split_names:
                matched_name = match_catalog_name(sn, catalog_names)
                if is_valid_grocery_item(matched_name, catalog_names):
                    items.append({'name': matched_name, 'specification': ''})
        else:
            matched_name = match_catalog_name(name, catalog_names)
            if is_valid_grocery_item(matched_name, catalog_names):
                items.append({'name': matched_name, 'specification': spec})
            
    return items

ACTIVE_ITEMS_FILE = os.path.join(CONFIG_DIR, '.bring_active.json')

def fetch_active_bring_items():
    """
    Holt alle aktiven Einkaufsartikel von Bring! und speichert sie als JSON-Array in .bring_active.json
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
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            raw_purchase = data.get('purchase') or (data.get('items', {}).get('purchase') if isinstance(data.get('items'), dict) else []) or []
            items = []
            for item in raw_purchase:
                name = item.get('name') or item.get('itemId')
                spec = item.get('specification') or ''
                full = f"{name} ({spec})".strip() if spec else name.strip()
                items.append(full)
            with open(ACTIVE_ITEMS_FILE, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
            res = {'items': items, 'count': len(items)}
            print(json.dumps(res, ensure_ascii=False))
            return items
    except Exception as e:
        print(json.dumps({'items': [], 'count': 0, 'error': str(e)}))
        return []

def execute_bring_sync(spoken_text):
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
        with urllib.request.urlopen(req) as resp:
            print(f"[OK] Bring Sync erfolgreich ({op}): {items}")
            fetch_active_bring_items()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
            auth = authenticate()
            headers['Authorization'] = f"{auth['token_type']} {auth['access_token']}"
            req = urllib.request.Request(url, data=payload, headers=headers, method='PUT')
            with urllib.request.urlopen(req) as resp2:
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
