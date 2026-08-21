/**
 * @file Config.js
 * @description Verwaltung von Konfigurations- und Zugangsdaten über ScriptProperties.
 */

const Config = {
  /**
   * Liest alle gespeicherten Konfigurationswerte aus den ScriptProperties.
   * @returns {Object} Konfigurationsobjekt
   */
  get: function () {
    const props = PropertiesService.getScriptProperties();
    return {
      bringEmail: props.getProperty('BRING_EMAIL') || '',
      bringPassword: props.getProperty('BRING_PASSWORD') || '',
      bringListName: props.getProperty('BRING_LIST_NAME') || '',
      bringListUuid: props.getProperty('BRING_LIST_UUID') || '',
      alexaSkillId: props.getProperty('ALEXA_SKILL_ID') || '',
      apiSecretKey: props.getProperty('API_SECRET_KEY') || ''
    };
  },

  /**
   * Setzt oder aktualisiert die Konfiguration in den ScriptProperties.
   * @param {Object} options
   * @param {string} options.email - Bring! Account E-Mail
   * @param {string} options.password - Bring! Account Passwort
   * @param {string} [options.listName] - Name der Bring! Liste (z.B. "Einkauf"), optional
   * @param {string} [options.listUuid] - UUID der Bring! Liste, optional
   * @param {string} [options.alexaSkillId] - Alexa Skill Application ID (amzn1.ask.skill.xxx), optional
   * @param {string} [options.apiSecretKey] - Geheimer Schlüssel für Home Assistant Webhooks, optional
   */
  set: function (options) {
    const props = PropertiesService.getScriptProperties();
    const updates = {};

    if (options.email !== undefined) updates['BRING_EMAIL'] = options.email.trim();
    if (options.password !== undefined) updates['BRING_PASSWORD'] = options.password;
    if (options.listName !== undefined) updates['BRING_LIST_NAME'] = options.listName.trim();
    if (options.listUuid !== undefined) updates['BRING_LIST_UUID'] = options.listUuid.trim();
    if (options.alexaSkillId !== undefined) updates['ALEXA_SKILL_ID'] = options.alexaSkillId.trim();
    if (options.apiSecretKey !== undefined) updates['API_SECRET_KEY'] = options.apiSecretKey.trim();

    props.setProperties(updates);
    Logger.log('✅ Konfiguration erfolgreich in den ScriptProperties gespeichert.');
  },

  /**
   * Prüft, ob alle zwingend erforderlichen Einstellungen gesetzt sind.
   */
  validate: function () {
    const config = this.get();
    if (!config.bringEmail || !config.bringPassword) {
      throw new Error(
        '❌ Fehlende Zugangsdaten!\n' +
        'Bitte hinterlege BRING_EMAIL und BRING_PASSWORD in den Google Apps Script Projekteinstellungen:\n' +
        '👉 Klicke links auf das Zahnrad (Projekteinstellungen) ➔ ganz unten "Skripteigenschaften" ➔ Eigenschaft hinzufügen.'
      );
    }
    return true;
  },

  /**
   * Gibt den aktuellen Status der Eigenschaften aus (ohne das Passwort im Klartext zu loggen).
   */
  logStatus: function () {
    const config = this.get();
    Logger.log('=== AKTUELLER STATUS DER SKRIPTEIGENSCHAFTEN ===');
    Logger.log(`BRING_EMAIL:      ${config.bringEmail ? config.bringEmail : '⚠️ NICHT GESETZT'}`);
    Logger.log(`BRING_PASSWORD:   ${config.bringPassword ? '******** (Gesetzt)' : '⚠️ NICHT GESETZT'}`);
    Logger.log(`BRING_LIST_NAME:  ${config.bringListName ? config.bringListName : '(Standardliste wird verwendet)'}`);
    Logger.log(`BRING_LIST_UUID:  ${config.bringListUuid ? config.bringListUuid : '(Automatisch ermittelt)'}`);
    Logger.log(`ALEXA_SKILL_ID:   ${config.alexaSkillId ? config.alexaSkillId : '(Keine Einschränkung / Offen)'}`);
    Logger.log(`API_SECRET_KEY:   ${config.apiSecretKey ? '******** (Aktiviert)' : '(Keine Einschränkung)'}`);
    Logger.log('================================================');
  }
};

/**
 * Funktion zum Überprüfen der gesetzten Skripteigenschaften im Protokoll.
 * Ausführen über das Dropdown: checkPropertiesStatus
 */
function checkPropertiesStatus() {
  Config.logStatus();
}

/**
 * Optionale Hilfsfunktion, falls du die Properties per Skript statt über das UI setzen möchtest.
 */
function setScriptProperty(key, value) {
  if (!key || !value) {
    Logger.log('Bitte key und value angeben, z.B. setScriptProperty("BRING_EMAIL", "deine@email.de")');
    return;
  }
  PropertiesService.getScriptProperties().setProperty(key, value);
  Logger.log(`✅ Skripteigenschaft "${key}" wurde erfolgreich gespeichert.`);
}

