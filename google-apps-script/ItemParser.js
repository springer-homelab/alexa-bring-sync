/**
 * @file ItemParser.js
 * @description Intelligenter Parser für Spracheingaben und Alexa Voice Transkriptionen.
 * Zerlegt Sätze in einzelne Artikel und extrahiert Mengenangaben für Bring!.
 */

const ItemParser = {
  /**
   * Bereinigt Sprachbefehle (z. B. "setze Bananen auf die Einkaufsliste") und extrahiert die reinen Artikel.
   * @param {string} rawText - Vollständiger gesprochener Text
   * @returns {Array<{name: string, specification: string}>} Liste von Artikeln mit Mengen
   */
  parse: function (rawText) {
    if (!rawText || typeof rawText !== 'string') {
      return [];
    }

    // Reine Fragen und Listenabfragen niemals als Artikel parsen
    const action = this.detectAction(rawText);
    if (action === 'GET') {
      return [];
    }

    let cleaned = this.stripCommandPhrases(rawText);
    if (!cleaned) {
      return [];
    }

    // Zerlege den Text anhand von Satzzeichen und Bindewörtern
    const rawItems = this.splitItems(cleaned);

    const result = [];
    for (let itemText of rawItems) {
      const parsed = this.parseSingleItem(itemText);
      if (parsed && parsed.name) {
        result.push(parsed);
      }
    }

    return result;
  },

  /**
   * Erkennt die beabsichtigte Aktion aus dem gesprochenen Satz.
   * @param {string} rawText
   * @returns {'ADD'|'COMPLETE'|'REMOVE'|'GET'}
   */
  detectAction: function (rawText) {
    if (!rawText) return 'ADD';
    const lower = rawText.toLowerCase().trim();

    if (lower.includes('was steht') || lower.includes('was ist auf') || lower.includes('lies') || lower.includes('was habe ich') || lower.includes('welche artikel') || lower.includes('vorlesen')) {
      return 'GET';
    }

    if (lower.startsWith('lösch') || lower.startsWith('entfern') || lower.includes('von der einkaufsliste') || lower.includes('von der liste') || (lower.includes('nimm') && lower.includes('runter'))) {
      return 'REMOVE';
    }

    if (lower.includes('abgehakt') || lower.includes('erledigt') || lower.includes('gekauft') || lower.startsWith('hake') || lower.startsWith('streiche')) {
      return 'COMPLETE';
    }

    return 'ADD';
  },

  /**
   * Entfernt gängige deutsche Sprachbefehl-Phrasen und Füllwörter.
   * @param {string} text
   * @returns {string}
   */
  stripCommandPhrases: function (text) {
    let t = text.trim();

    // Typische Alexa / Sprachassistenten Befehlsstrukturen am Anfang oder Ende entfernen
    const patterns = [
      // Lösch- / Entfern-Befehle
      /^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+?)\s+(?:von|aus|von\s+der|von\s+den|von\s+unserer|von\s+meiner)\s+(?:der|meiner|unserer|den|die)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)$/i,
      /^(?:alexa,?\s*)?(?:bitte\s*)?(?:nimm|tu)\s+(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s*runter$/i,
      /^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?)\s+(.+)$/i,

      // Hinzufüge-Befehle (inkl. 'für' als häufiger STT-Fehler für 'füg'/'füge')
      /^(?:alexa,?\s*)?(?:bitte\s*)?(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu|pack)\s+(.+?)\s+(?:auf|zu|zur|in|an|der)\s+(?:die|meine|unsere|den|der|das)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf)?$/i,
      /^(?:alexa,?\s*)?(?:bitte\s*)?(?:wir\s+brauchen\s+noch|kauf\s+bitte|kauf(?:en)?|besorg(?:e)?)\s+(.+)$/i,
      /^(?:alexa,?\s*)?(?:sag|sage|frage|öffne)\s+(?:meinem?\s+)?(?:einkaufszettel|einkaufsliste|bring|liste)(?::|\s+)?\s*(.+)$/i,
      /^(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu)\s+(.+?)(?:\s+(?:auf|zu|zur|in|der)\s+(?:die|den|meine|unsere|der|das)\s+(?:einkaufsliste|liste|zettel))?$/i
    ];

    for (let pattern of patterns) {
      const match = t.match(pattern);
      if (match && match[1]) {
        t = match[1];
        break;
      }
    }

    // Füllwörter und verbleibende Listenwörter am Anfang oder Ende bereinigen
    t = t.replace(/^(?:noch|bitte|mal|eben|schnell)\s+/i, '');
    t = t.replace(/\s+(?:auf|zu|zur|in|an|der|den|die|das|meine|unsere)?\s*(?:die|meine|unsere|den|der|das)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf|\s*ab)?$/i, '');
    t = t.replace(/\s+(?:zur|zu|auf|an|für|hinzu|drauf|runter|weg|bitte|danke|noch)$/i, '');

    return t.trim();
  },

  /**
   * Teilt einen kombinierten String an Bindewörtern und Kommas auf (schützt Dezimalkommas wie 1,5 kg).
   * @param {string} text
   * @returns {string[]}
   */
  splitItems: function (text) {
    // Dezimalkommas schützen (z. B. "1,5 kg" -> "1__DEC__5 kg")
    let normalized = text.replace(/(\d+),(\d+)/g, '$1__DEC__$2');

    // Ersetze Bindewörter durch ein einheitliches Trennzeichen
    normalized = normalized
      .replace(/\s+und\s+zwar\s+/gi, ' ')
      .replace(/\s+(?:und\s+auch|sowie|plus|und|\+)\s+/gi, ' , ')
      .replace(/;\s*/g, ' , ')
      .replace(/\n+/g, ' , ');

    return normalized
      .split(',')
      .map(item => item.replace(/__DEC__/g, ',').trim())
      .filter(item => item.length > 0);
  },

  /**
   * Vollständiger deutscher Zahlen- und Bruch-Normalisierer (0 bis 9999 + Brüche + zusammengesetzte Zahlwörter).
   * @param {string} str
   * @returns {string}
   */
  normalizeNumberWords: function (str) {
    let s = str.trim();

    // 1. Brüche und gemischte Brüche
    const fractionMap = [
      [/anderthalb|eineinhalb/gi, '1,5'],
      [/zweieinhalb/gi, '2,5'],
      [/dreieinhalb/gi, '3,5'],
      [/viereinhalb/gi, '4,5'],
      [/fünfeinhalb/gi, '5,5'],
      [/dreiviertel|drei\s*viertel/gi, '0,75'],
      [/(?:ein\s+)?halbes|ein\s*halb|halbe(?:n|r|s)?/gi, '0,5'],
      [/(?:ein\s+)?viertel/gi, '0,25']
    ];

    for (let [pattern, val] of fractionMap) {
      s = s.replace(pattern, `${val} `);
    }

    // 2. Hunderter & Tausender
    const hundredsMap = [
      [/eintausend|ein\s*tausend|tausend/gi, '1000 '],
      [/neun\s*hundert|neunhundert/gi, '900 '],
      [/acht\s*hundert|achthundert/gi, '800 '],
      [/sieben\s*hundert|siebenhundert/gi, '700 '],
      [/sechs\s*hundert|sechshundert/gi, '600 '],
      [/fünf\s*hundert|fünfhundert/gi, '500 '],
      [/vier\s*hundert|vierhundert/gi, '400 '],
      [/drei\s*hundert|dreihundert/gi, '300 '],
      [/zwei\s*hundert|zweihundert/gi, '200 '],
      [/ein\s*hundert|einhundert|hundert/gi, '100 ']
    ];

    for (let [pattern, val] of hundredsMap) {
      s = s.replace(pattern, val);
    }

    // 3. Zweistellige zusammengesetzte Zahlen (z. B. "zweiundzwanzig" -> 22, "fünfunddreißig" -> 35, "neunundneunzig" -> 99)
    const ones = { 'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9 };
    const tens = { 'zwanzig': 20, 'dreißig': 30, 'vierzig': 40, 'fünfzig': 50, 'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90 };

    for (let [oneK, oneV] of Object.entries(ones)) {
      for (let [tenK, tenV] of Object.entries(tens)) {
        const compound = `${oneK}und${tenK}`;
        const total = oneV + tenV;
        const re = new RegExp(`\\b${compound}\\b`, 'gi');
        s = s.replace(re, `${total} `);
      }
    }

    // 4. Einzelne Zahlwörter (1-20, 30, 40... 90) als Wortgrenzen
    const singleWords = [
      [/\b(zwanzig)\b/gi, '20 '], [/\b(dreißig)\b/gi, '30 '], [/\b(vierzig)\b/gi, '40 '],
      [/\b(fünfzig)\b/gi, '50 '], [/\b(sechzig)\b/gi, '60 '], [/\b(siebzig)\b/gi, '70 '],
      [/\b(achtzig)\b/gi, '80 '], [/\b(neunzig)\b/gi, '90 '],
      [/\b(dreizehn)\b/gi, '13 '], [/\b(vierzehn)\b/gi, '14 '], [/\b(fünfzehn)\b/gi, '15 '],
      [/\b(sechzehn)\b/gi, '16 '], [/\b(siebzehn)\b/gi, '17 '], [/\b(achtzehn)\b/gi, '18 '],
      [/\b(neunzehn)\b/gi, '19 '], [/\b(zwölf)\b/gi, '12 '], [/\b(elf)\b/gi, '11 '], [/\b(zehn)\b/gi, '10 '],
      [/\b(neun)\b/gi, '9 '], [/\b(acht)\b/gi, '8 '], [/\b(sieben)\b/gi, '7 '], [/\b(sechs)\b/gi, '6 '],
      [/\b(fünf)\b/gi, '5 '], [/\b(vier)\b/gi, '4 '], [/\b(drei)\b/gi, '3 '], [/\b(zwei)\b/gi, '2 '],
      [/\b(eins|eine|einen|einem|einer|ein)\b/gi, '1 ']
    ];

    for (let [pattern, val] of singleWords) {
      s = s.replace(pattern, val);
    }

    // 5. Addition von Hunderter + Zehner/Einer (z.B. "200 50" -> "250", "100 25" -> "125")
    s = s.replace(/\b(\d{1,4}00)\s+(\d{1,2})\b/g, (match, p1, p2) => String(parseInt(p1, 10) + parseInt(p2, 10)));

    return s.replace(/\s+/g, ' ').trim();
  },

  /**
   * Extrahiert Artikelname und Mengenangabe/Spezifikation aus einem einzelnen Textfragment.
   * @param {string} itemStr
   * @returns {{name: string, specification: string}}
   */
  parseSingleItem: function (itemStr) {
    let str = itemStr.trim();
    if (!str) return null;

    // Zahlwörter vorab zu Ziffern normalisieren
    str = this.normalizeNumberWords(str);

    // Alle Einheiten inkl. Packungen, Rollen, Kästen, Gläser, Zehen, Becher, Tuben etc.
    const unitsPattern = 'kg|kilo|kilogramm|g|gramm|l|liter|ml|milliliter|cl|dl|packung(?:en)?|pkg|pack(?:s)?|stk|stück|flasche(?:n)?|dose(?:n)?|bund|beutel|gläser|glas|scheibe(?:n)?|kasten|kästen|kiste(?:n)?|tüte(?:n)?|becher|zehe(?:n)?|knolle(?:n)?|tafel(?:n)?|tube(?:n)?|stange(?:n)?|zweig(?:e)?|rolle(?:n)?|karton(?:s)?|portion(?:en)?';

    // Fall 1: Ziffer + Einheit (z. B. "250 Gramm Butter", "1,5 kg Kartoffeln", "2 Rollen Küchenpapier", "0,5 l Milch")
    const unitRegex = new RegExp(`^(\\d+(?:[.,]\\d+)?\\s*(?:${unitsPattern}))\\s+(?:von\\s+)?(.+)$`, 'i');
    let match = str.match(unitRegex);

    if (match) {
      return {
        name: this.capitalize(match[2].trim()),
        specification: match[1].trim()
      };
    }

    // Fall 2: Reine Zahlen am Anfang (z. B. "22 Bananen", "35 Äpfel", "6 Eier")
    const plainNumberRegex = /^(\d+(?:[.,]\\d+)?)\s+([a-zA-ZäöüÄÖÜß].+)$/;
    match = str.match(plainNumberRegex);

    if (match) {
      return {
        name: this.normalizeCatalogName(match[2].trim()),
        specification: match[1].trim()
      };
    }

    // Fall 3: Kein Mengenangaben-Muster gefunden -> Reiner Artikelname
    return {
      name: this.normalizeCatalogName(str),
      specification: ''
    };
  },

  /**
   * Normalisiert Artikelnamen auf Bring! Katalogschlüssel für automatische Icons.
   * @param {string} str
   * @returns {string}
   */
  normalizeCatalogName: function (str) {
    if (!str) return '';
    let name = this.capitalize(str.trim());
    const catalogMap = {
      'Pfirsiche': 'Pfirsich',
      'Aprikosen': 'Aprikose'
    };
    return catalogMap[name] || name;
  },

  /**
   * Großschreibung des ersten Buchstabens
   * @param {string} str
   * @returns {string}
   */
  capitalize: function (str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
};

if (typeof module !== 'undefined') {
  module.exports = ItemParser;
}
