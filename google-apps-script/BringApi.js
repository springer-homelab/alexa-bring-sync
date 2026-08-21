/**
 * @file BringApi.js
 * @description Vollständiger Client für die moderne Bring! REST API v2 in Google Apps Script.
 * Verwendet die exakten Header und Endpunkte der offiziellen Bring Android/iOS App.
 */

const BringApi = {
  BASE_URL: 'https://api.getbring.com/rest',

  // Exakte Client-Header aus der Bring! Mobile-App
  API_KEY: 'cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp',
  CLIENT: 'android',
  APPLICATION: 'bring',
  COUNTRY: 'DE',

  /**
   * Führt einen Login bei Bring! durch oder holt die gecachten Auth-Daten.
   * @returns {{accessToken: string, tokenType: string, uuid: string, publicUuid: string, bringListUUID: string}}
   */
  authenticate: function () {
    const cache = CacheService.getScriptCache();
    const cachedToken = cache.get('BRING_ACCESS_TOKEN');
    const cachedTokenType = cache.get('BRING_TOKEN_TYPE') || 'Bearer';
    const cachedUuid = cache.get('BRING_UUID');
    const cachedPublicUuid = cache.get('BRING_PUBLIC_UUID');
    const cachedListUuid = cache.get('BRING_LIST_UUID');

    if (cachedToken && cachedUuid && cachedToken !== 'undefined' && cachedUuid !== 'undefined') {
      return {
        accessToken: cachedToken,
        tokenType: cachedTokenType,
        uuid: cachedUuid,
        publicUuid: cachedPublicUuid || cachedUuid,
        bringListUUID: cachedListUuid || ''
      };
    }

    const config = Config.get();
    Config.validate();

    const payload = {
      email: config.bringEmail,
      password: config.bringPassword
    };

    const options = {
      method: 'post',
      contentType: 'application/x-www-form-urlencoded',
      headers: {
        'X-BRING-API-KEY': this.API_KEY,
        'X-BRING-CLIENT': this.CLIENT,
        'X-BRING-APPLICATION': this.APPLICATION,
        'X-BRING-COUNTRY': this.COUNTRY
      },
      payload: payload,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(`${this.BASE_URL}/v2/bringauth`, options);
    const code = response.getResponseCode();
    const body = response.getContentText();

    if (code !== 200) {
      Logger.log(`❌ Bring! Auth Fehler (HTTP ${code}): ${body}`);
      throw new Error(`Bring! Login fehlgeschlagen (HTTP ${code}). Bitte E-Mail und Passwort prüfen!`);
    }

    const data = JSON.parse(body);
    const accessToken = data.access_token;
    const tokenType = data.token_type || 'Bearer';
    const uuid = data.uuid || data.userUuid || '';
    const publicUuid = data.publicUuid || uuid;
    const bringListUUID = data.bringListUUID || '';

    // In ScriptCache cachen (TTL 21000s = ~5.8h)
    cache.put('BRING_ACCESS_TOKEN', accessToken, 21000);
    cache.put('BRING_TOKEN_TYPE', tokenType, 21000);
    cache.put('BRING_UUID', uuid, 21000);
    cache.put('BRING_PUBLIC_UUID', publicUuid, 21000);
    if (bringListUUID) cache.put('BRING_LIST_UUID', bringListUUID, 21000);

    return { accessToken, tokenType, uuid, publicUuid, bringListUUID };
  },

  /**
   * Erzeugt die vollständigen Standard-Header für alle Bring! API Anfragen.
   * @param {{accessToken: string, tokenType: string, uuid: string, publicUuid: string}} auth
   * @returns {Object}
   */
  getHeaders: function (auth) {
    return {
      'Authorization': `${auth.tokenType} ${auth.accessToken}`,
      'X-BRING-API-KEY': this.API_KEY,
      'X-BRING-CLIENT': this.CLIENT,
      'X-BRING-APPLICATION': this.APPLICATION,
      'X-BRING-COUNTRY': this.COUNTRY,
      'X-BRING-USER-UUID': auth.uuid,
      'X-BRING-PUBLIC-USER-UUID': auth.publicUuid
    };
  },

  /**
   * Ruft alle Einkaufslisten des Benutzers ab.
   * @param {boolean} [retry=true]
   * @returns {Array<{listUuid: string, name: string}>}
   */
  getLists: function (retry) {
    if (retry === undefined) retry = true;
    const auth = this.authenticate();
    const headers = this.getHeaders(auth);

    const options = {
      method: 'get',
      headers: headers,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(`${this.BASE_URL}/bringusers/${auth.uuid}/lists`, options);
    const code = response.getResponseCode();

    if (code === 401 && retry) {
      Logger.log('⚠️ Token abgelaufen (HTTP 401). Erneuere Token...');
      this.clearTokenCache();
      return this.getLists(false);
    }

    if (code !== 200) {
      throw new Error(`Listen konnten nicht geladen werden (HTTP ${code}): ${response.getContentText()}`);
    }

    const data = JSON.parse(response.getContentText());
    return data.lists || [];
  },

  /**
   * Ermittelt die Ziel-Listen-UUID anhand von Name, Standard-UUID oder Auth-Response.
   * @returns {string} listUuid
   */
  getTargetListUuid: function () {
    const config = Config.get();

    // 1. Feste UUID aus den Script-Properties
    if (config.bringListUuid) {
      return config.bringListUuid;
    }

    const auth = this.authenticate();

    // 2. Falls ein spezifischer Listenname gesucht wird, versuchen diesen zu finden
    if (config.bringListName && config.bringListName.toLowerCase() !== 'einkaufsliste' && config.bringListName.toLowerCase() !== 'einkauf') {
      try {
        const lists = this.getLists();
        if (lists && lists.length > 0) {
          const match = lists.find(l => l.name.toLowerCase() === config.bringListName.toLowerCase());
          if (match) {
            return match.listUuid;
          }
        }
      } catch (err) {
        Logger.log(`⚠️ Konnte Liste "${config.bringListName}" nicht über getLists laden: ${err.message}`);
      }
    }

    // 3. Direkte Standard-Listen-UUID aus dem Login-Response (superschnell & 100% zuverlässig)
    if (auth.bringListUUID) {
      return auth.bringListUUID;
    }

    // 4. Fallback auf getLists
    try {
      const lists = this.getLists();
      if (lists && lists.length > 0) {
        return lists[0].listUuid;
      }
    } catch (e) {
      Logger.log(`⚠️ Fehler bei getLists Fallback: ${e.message}`);
    }

    throw new Error('Keine Bring! Ziel-Listen-UUID gefunden.');
  },

  /**
   * Ruft alle aktuellen Artikel einer Liste ab.
   * @param {string} [listUuid]
   * @param {boolean} [retry=true]
   * @returns {{purchase: Array<{name: string, specification: string}>, recently: Array<{name: string, specification: string}>}}
   */
  getListItems: function (listUuid, retry) {
    if (retry === undefined) retry = true;
    const targetUuid = listUuid || this.getTargetListUuid();
    const auth = this.authenticate();
    const headers = this.getHeaders(auth);

    const options = {
      method: 'get',
      headers: headers,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(`${this.BASE_URL}/v2/bringlists/${targetUuid}`, options);
    const code = response.getResponseCode();

    if (code === 401 && retry) {
      this.clearTokenCache();
      return this.getListItems(targetUuid, false);
    }

    if (code !== 200) {
      throw new Error(`Artikel konnten nicht abgerufen werden (HTTP ${code}): ${response.getContentText()}`);
    }

    const data = JSON.parse(response.getContentText());
    const items = data.items || data;

    const purchase = (items.purchase || []).map(i => ({
      name: i.name || i.itemId,
      specification: i.specification || i.spec || ''
    }));

    const recently = (items.recently || []).map(i => ({
      name: i.name || i.itemId,
      specification: i.specification || i.spec || ''
    }));

    return { purchase, recently };
  },

  /**
   * Fügt einen oder mehrere Artikel zur Bring! Liste hinzu (Batch Update API v2).
   * @param {Array<{name: string, specification: string}>|{name: string, specification: string}} items
   * @param {string} [listUuid]
   * @returns {Array<{name: string, specification: string, success: boolean}>}
   */
  addItems: function (items, listUuid) {
    return this.batchUpdate(items, 'TO_PURCHASE', listUuid);
  },

  /**
   * Hakt einen Artikel auf der Bring! Liste ab (verschiebt ihn in "recently").
   * @param {string} itemName
   * @param {string} [listUuid]
   * @returns {boolean}
   */
  completeItem: function (itemName, listUuid) {
    const results = this.batchUpdate([{ name: itemName, specification: '' }], 'TO_RECENTLY', listUuid);
    return results.length > 0 && results[0].success;
  },

  /**
   * Löscht einen Artikel komplett von der Bring! Liste.
   * @param {string} itemName
   * @param {string} [listUuid]
   * @returns {boolean}
   */
  removeItem: function (itemName, listUuid) {
    const results = this.batchUpdate([{ name: itemName, specification: '' }], 'REMOVE', listUuid);
    return results.length > 0 && results[0].success;
  },

  /**
   * Findet den am besten passenden Artikelnamen auf der aktuellen Liste (unterstützt Einzahl/Mehrzahl, Umlaut-Variationen und Wortstämme).
   * @param {string} queryName
   * @param {Array<{name: string}>} existingItems
   * @returns {string}
   */
  findMatchingItemName: function (queryName, existingItems) {
    if (!queryName || !existingItems || existingItems.length === 0) return queryName;
    const q = queryName.toLowerCase().trim();

    // 1. Exakter Match
    let match = existingItems.find(i => i.name.toLowerCase() === q);
    if (match) return match.name;

    // 2. Substring Match (z. B. "Pollo" findet "Pollo fino")
    match = existingItems.find(i => i.name.toLowerCase().includes(q) || q.includes(i.name.toLowerCase()));
    if (match) return match.name;

    // 3. Einzahl / Mehrzahl Wortstamm-Match (z. B. "Apfel" <-> "Äpfel", "Banane" <-> "Bananen", "Ei" <-> "Eier")
    const stem = function (word) {
      return word.toLowerCase()
        .replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u')
        .replace(/(?:en|n|er|e|s)$/, '');
    };

    const qStem = stem(q);
    if (qStem.length >= 3) {
      match = existingItems.find(i => {
        const itemStem = stem(i.name);
        return itemStem === qStem || itemStem.startsWith(qStem) || qStem.startsWith(itemStem);
      });
      if (match) return match.name;
    }

    return queryName;
  },

  /**
   * Lädt und cacht alle bekannten Katalog-Artikel der Liste für Icon- und Namensnormalisierung.
   * @param {string} [listUuid]
   * @returns {Array<{name: string}>}
   */
  getListDetails: function (listUuid) {
    const targetUuid = listUuid || this.getTargetListUuid();
    const cache = CacheService.getScriptCache();
    const cached = cache.get('BRING_CATALOG_' + targetUuid);
    if (cached) {
      try { return JSON.parse(cached); } catch (e) {}
    }

    const auth = this.authenticate();
    const headers = this.getHeaders(auth);
    const options = { method: 'get', headers: headers, muteHttpExceptions: true };
    const response = UrlFetchApp.fetch(`${this.BASE_URL}/v2/bringlists/${targetUuid}/details`, options);
    if (response.getResponseCode() === 200) {
      try {
        const details = JSON.parse(response.getContentText());
        const names = details.map(d => ({ name: d.itemId })).filter(d => d.name);
        cache.put('BRING_CATALOG_' + targetUuid, JSON.stringify(names), 21000);
        return names;
      } catch (err) {}
    }
    return [];
  },

  /**
   * Führt ein Batch-Update auf der Bring! Liste aus.
   * @param {Array<{name: string, specification: string}>} items
   * @param {'TO_PURCHASE'|'TO_RECENTLY'|'REMOVE'} operation
   * @param {string} [listUuid]
   * @returns {Array<{name: string, specification: string, success: boolean}>}
   */
  batchUpdate: function (items, operation, listUuid) {
    const targetUuid = listUuid || this.getTargetListUuid();
    const auth = this.authenticate();
    const headers = this.getHeaders(auth);
    headers['Content-Type'] = 'application/json';

    const itemList = Array.isArray(items) ? items : [items];
    let existingItems = [];
    let catalogItems = [];

    // Beim Löschen oder Abhaken: Vorhandene Artikel abrufen für intelligentes Namens-Matching
    if (operation === 'REMOVE' || operation === 'TO_RECENTLY') {
      try {
        const listData = this.getListItems(targetUuid);
        existingItems = listData.purchase || [];
      } catch (e) {
        Logger.log('⚠️ Konnte Artikel für Namensabgleich nicht vorab laden: ' + e.message);
      }
    } else if (operation === 'TO_PURCHASE') {
      try {
        catalogItems = this.getListDetails(targetUuid);
      } catch (e) {
        Logger.log('⚠️ Konnte Details nicht laden: ' + e.message);
      }
    }

    const changes = itemList.filter(i => i && i.name).map(i => {
      let resolvedName = i.name;
      if (operation === 'REMOVE' || operation === 'TO_RECENTLY') {
        resolvedName = this.findMatchingItemName(i.name, existingItems);
      } else if (operation === 'TO_PURCHASE' && catalogItems.length > 0) {
        resolvedName = this.findMatchingItemName(i.name, catalogItems);
      }

      return {
        accuracy: '0.0',
        altitude: '0.0',
        latitude: '0.0',
        longitude: '0.0',
        itemId: resolvedName,
        spec: i.specification || '',
        operation: operation
      };
    });

    if (changes.length === 0) return [];

    const jsonPayload = JSON.stringify({
      changes: changes,
      sender: ''
    });

    const options = {
      method: 'put',
      headers: headers,
      payload: jsonPayload,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(`${this.BASE_URL}/v2/bringlists/${targetUuid}/items`, options);
    const code = response.getResponseCode();

    const success = (code === 200 || code === 204);
    if (!success) {
      Logger.log(`⚠️ Batch-Update Fehler (HTTP ${code}): ${response.getContentText()}`);
    }

    return itemList.map(i => ({
      name: i.name,
      specification: i.specification || '',
      success: success
    }));
  },

  /**
   * Löscht den Token-Cache bei abgelaufener Session.
   */
  clearTokenCache: function () {
    const cache = CacheService.getScriptCache();
    cache.remove('BRING_ACCESS_TOKEN');
    cache.remove('BRING_TOKEN_TYPE');
    cache.remove('BRING_UUID');
    cache.remove('BRING_PUBLIC_UUID');
    cache.remove('BRING_LIST_UUID');
  }
};
