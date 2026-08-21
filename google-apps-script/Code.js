/**
 * @file Code.js
 * @description Haupteinstiegspunkt für Google Apps Script Web App (doGet / doPost).
 * Verarbeitet Alexa Custom Skill Requests sowie Home Assistant und mobile Webhooks.
 */

/**
 * Verarbeitet alle eingehenden POST-Anfragen (Alexa Skill, Home Assistant, iOS Kurzbefehle).
 * @param {Object} e - Google Apps Script Event-Objekt
 * @returns {TextOutput} JSON Response
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        success: false,
        error: 'Kein Request-Body empfangen.'
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const payload = JSON.parse(e.postData.contents);

    // 1. Fall: Eingehender Request vom Amazon Alexa Skill
    if (payload.version && (payload.request || payload.session)) {
      const alexaResponse = AlexaSkillHandler.handleRequest(payload);
      return ContentService.createTextOutput(JSON.stringify(alexaResponse))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 2. Fall: Eingehender Webhook von Home Assistant, Siri oder Smartphone
    return handleGenericWebhook(payload, e.parameter);

  } catch (err) {
    Logger.log(`❌ Kritischer Fehler in doPost: ${err.message}\n${err.stack}`);
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: err.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Behandelt generische Webhook-Aufrufe (z. B. aus Home Assistant Automatisierungen).
 * @param {Object} payload - JSON Body { text: "...", key: "...", items: [...] }
 * @param {Object} queryParams - URL Parameter ?key=...
 * @returns {TextOutput}
 */
function handleGenericWebhook(payload, queryParams) {
  const config = Config.get();

  // Optionale API-Key-Prüfung für Home Assistant
  const providedKey = (payload && payload.key) || (queryParams && queryParams.key) || '';
  if (config.apiSecretKey && providedKey !== config.apiSecretKey) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: 'Ungültiger oder fehlender API-Schlüssel.'
    })).setMimeType(ContentService.MimeType.JSON);
  }

  const rawText = (payload && (payload.text || payload.raw || payload.message || payload.summary)) || '';
  const action = (payload && payload.action) || ItemParser.detectAction(rawText);

  // 1. Fall: Liste abfragen ("Was steht auf der Einkaufsliste?")
  if (action === 'GET') {
    const listData = BringApi.getListItems();
    const purchase = listData.purchase || [];
    let speech = '';
    if (purchase.length === 0) {
      speech = 'Deine Bring Einkaufsliste ist aktuell leer.';
    } else {
      const itemsFormatted = purchase.map(i => i.specification ? `${i.specification} ${i.name}` : i.name).join(', ');
      speech = `Auf deiner Bring Einkaufsliste stehen ${purchase.length} Artikel: ${itemsFormatted}.`;
    }

    return ContentService.createTextOutput(JSON.stringify({
      success: true,
      action: 'GET',
      count: purchase.length,
      speech: speech,
      items: purchase
    })).setMimeType(ContentService.MimeType.JSON);
  }

  let itemsToAdd = [];

  if (Array.isArray(payload.items)) {
    itemsToAdd = payload.items.map(i => typeof i === 'string' ? ItemParser.parseSingleItem(i) : i);
  } else if (rawText) {
    itemsToAdd = ItemParser.parse(rawText);
  }

  if (itemsToAdd.length === 0) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      message: 'Keine Artikel im Text erkannt.'
    })).setMimeType(ContentService.MimeType.JSON);
  }

  let results = [];

  if (action === 'REMOVE') {
    results = BringApi.batchUpdate(itemsToAdd, 'REMOVE');
  } else if (action === 'COMPLETE') {
    results = BringApi.batchUpdate(itemsToAdd, 'TO_RECENTLY');
  } else {
    results = BringApi.addItems(itemsToAdd);
  }

  const successful = results.filter(r => r.success);

  return ContentService.createTextOutput(JSON.stringify({
    success: successful.length > 0,
    action: action,
    count: successful.length,
    items: results
  })).setMimeType(ContentService.MimeType.JSON);
}

/**
 * Healthcheck und Statusseite im Browser (GET Request).
 * @param {Object} e
 * @returns {HtmlOutput}
 */
function doGet(e) {
  const config = Config.get();
  const hasAuth = !!(config.bringEmail && config.bringPassword);

  let statusText = 'Bereit zur Synchronisation';
  let statusColor = '#10b981';

  if (!hasAuth) {
    statusText = 'Zugangsdaten noch nicht hinterlegt (Setup erforderlich)';
    statusColor = '#ef4444';
  }

  const html = `
    <!DOCTYPE html>
    <html lang="de">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Alexa ➔ Bring! Sync Server</title>
      <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }
        .card { max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
        .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: bold; background: ${statusColor}; color: white; font-size: 0.875rem; }
        h1 { margin-top: 0.5rem; font-size: 1.5rem; }
        p { color: #94a3b8; line-height: 1.5; }
        .info-box { background: #334155; padding: 1rem; border-radius: 8px; margin-top: 1rem; font-family: monospace; font-size: 0.9rem; }
      </style>
    </head>
    <body>
      <div class="card">
        <span class="badge">${statusText}</span>
        <h1>🛒 Alexa ➔ Bring! Sync Hub</h1>
        <p>Dieser Google Apps Script Endpunkt empfängt Sprachbefehle und Webhooks und synchronisiert sie in Echtzeit mit deiner Bring! Einkaufsliste.</p>
        <div class="info-box">
          Status: ${hasAuth ? '✅ Bring! Account konfiguriert' : '⚠️ Bitte setupCredentials() ausführen'}<br>
          Zielliste: ${config.bringListName ? config.bringListName : 'Standardliste'}<br>
          Alexa Skill ID: ${config.alexaSkillId ? 'Aktiviert' : 'Nicht hinterlegt (offen)'}
        </div>
      </div>
    </body>
    </html>
  `;

  return HtmlService.createHtmlOutput(html)
    .setTitle('Alexa ➔ Bring! Sync Hub')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
