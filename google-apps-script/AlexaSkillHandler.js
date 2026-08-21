/**
 * @file AlexaSkillHandler.js
 * @description Verarbeitet Alexa Skill Requests (JSON), Intent-Mapping und generiert Alexa-konforme Responses.
 */

const AlexaSkillHandler = {
  /**
   * Haupteinstiegspunkt für Alexa Skill JSON Requests.
   * @param {Object} alexaRequest - Der vom Alexa Skill Service übermittelte Request-Body
   * @returns {Object} Alexa Response JSON
   */
  handleRequest: function (alexaRequest) {
    try {
      // 1. Sicherheitsüberprüfung (Skill Application ID prüfen falls konfiguriert)
      this.verifySkillId(alexaRequest);

      const requestType = alexaRequest.request ? alexaRequest.request.type : '';

      switch (requestType) {
        case 'LaunchRequest':
          return this.handleLaunch();

        case 'IntentRequest':
          return this.handleIntent(alexaRequest.request.intent);

        case 'SessionEndedRequest':
          return this.buildResponse('Bis bald!', true);

        default:
          return this.buildResponse('Entschuldigung, diesen Befehl kenne ich leider nicht.', true);
      }
    } catch (err) {
      Logger.log(`❌ Fehler im AlexaSkillHandler: ${err.message}`);
      return this.buildResponse(`Es ist ein Fehler aufgetreten: ${err.message}`, true);
    }
  },

  /**
   * Prüft die Skill ID, um unbefugte Webhook-Aufrufe zu blockieren.
   * @param {Object} alexaRequest
   */
  verifySkillId: function (alexaRequest) {
    const config = Config.get();
    if (!config.alexaSkillId) return; // Wenn nicht konfiguriert, überspringen

    const incomingSkillId = (alexaRequest.session && alexaRequest.session.application)
      ? alexaRequest.session.application.applicationId
      : (alexaRequest.context && alexaRequest.context.System && alexaRequest.context.System.application)
        ? alexaRequest.context.System.application.applicationId
        : '';

    if (incomingSkillId !== config.alexaSkillId) {
      throw new Error(`Ungültige Alexa Skill ID: ${incomingSkillId}`);
    }
  },

  /**
   * Behandelt den Start des Skills ohne direkten Befehl ("Alexa, öffne Einkaufszettel").
   */
  handleLaunch: function () {
    const text = 'Willkommen bei deinem Einkaufszettel! Du kannst sagen: Setze Bananen auf die Liste, oder frage: Was steht auf der Liste?';
    return this.buildResponse(text, false, 'Was möchtest du auf die Liste setzen?');
  },

  /**
   * Verteilt Intent-Anfragen auf die entsprechenden Handler.
   * @param {Object} intent
   */
  handleIntent: function (intent) {
    const intentName = intent ? intent.name : '';

    switch (intentName) {
      case 'AddItemsIntent':
        return this.handleAddItems(intent);

      case 'GetListIntent':
        return this.handleGetList();

      case 'CompleteItemIntent':
        return this.handleCompleteItem(intent);

      case 'AMAZON.HelpIntent':
        return this.buildResponse('Du kannst Artikel hinzufügen, indem du sagst: Setze Milch und Bananen auf die Liste. Oder frage: Was steht auf der Liste?', false);

      case 'AMAZON.CancelIntent':
      case 'AMAZON.StopIntent':
        return this.buildResponse('Alles klar, bis zum nächsten Mal!', true);

      case 'AMAZON.FallbackIntent':
      default:
        return this.buildResponse('Das habe ich leider nicht verstanden. Sag zum Beispiel: Setze 2 Kilo Äpfel auf die Liste.', false);
    }
  },

  /**
   * Intent: Artikel zur Bring! Liste hinzufügen.
   * @param {Object} intent
   */
  handleAddItems: function (intent) {
    const slot = (intent.slots && (intent.slots.Items || intent.slots.Item || intent.slots.RawText))
      ? (intent.slots.Items || intent.slots.Item || intent.slots.RawText).value
      : '';

    if (!slot) {
      return this.buildResponse('Was genau möchtest du auf die Einkaufsliste setzen?', false);
    }

    // Artikel über den ItemParser zerlegen und Mengenangaben extrahieren
    const parsedItems = ItemParser.parse(slot);

    if (parsedItems.length === 0) {
      return this.buildResponse('Ich konnte leider keinen Artikel in deinem Satz erkennen.', true);
    }

    // Zur Bring! Liste hinzufügen
    const results = BringApi.addItems(parsedItems);
    const addedNames = results.filter(r => r.success).map(r => {
      return r.specification ? `${r.specification} ${r.name}` : r.name;
    });

    if (addedNames.length === 0) {
      return this.buildResponse('Die Artikel konnten leider nicht zu Bring hinzugefügt werden.', true);
    }

    const formattedNames = this.formatItemList(addedNames);
    const speech = `Ich habe ${formattedNames} auf deine Einkaufsliste gesetzt.`;
    return this.buildResponse(speech, true);
  },

  /**
   * Intent: Aktuelle Bring! Liste abfragen und vorlesen.
   */
  handleGetList: function () {
    const listData = BringApi.getListItems();
    const items = listData.purchase || [];

    if (items.length === 0) {
      return this.buildResponse('Deine Einkaufsliste ist aktuell leer.', true);
    }

    const itemNames = items.map(i => {
      return i.specification ? `${i.specification} ${i.name}` : i.name;
    });

    const formattedNames = this.formatItemList(itemNames);
    const speech = `Auf deiner Einkaufsliste stehen ${items.length} ${items.length === 1 ? 'Artikel' : 'Artikel'}: ${formattedNames}.`;
    return this.buildResponse(speech, true);
  },

  /**
   * Intent: Artikel abhaken / als gekauft markieren.
   * @param {Object} intent
   */
  handleCompleteItem: function (intent) {
    const slot = (intent.slots && (intent.slots.Item || intent.slots.Items))
      ? (intent.slots.Item || intent.slots.Items).value
      : '';

    if (!slot) {
      return this.buildResponse('Welchen Artikel möchtest du abhaken?', false);
    }

    const parsed = ItemParser.parseSingleItem(slot);
    const itemName = parsed ? parsed.name : slot.trim();

    const success = BringApi.completeItem(itemName);

    if (success) {
      return this.buildResponse(`Ich habe ${itemName} auf deiner Einkaufsliste abgehakt.`, true);
    } else {
      return this.buildResponse(`Konnte ${itemName} nicht abhaken.`, true);
    }
  },

  /**
   * Formatiert eine Liste von Artikeln natürlich mit Kommas und "und" (z.B. "Bananen, Milch und Äpfel").
   * @param {string[]} list
   * @returns {string}
   */
  formatItemList: function (list) {
    if (!list || list.length === 0) return '';
    if (list.length === 1) return list[0];
    if (list.length === 2) return `${list[0]} und ${list[1]}`;
    return `${list.slice(0, -1).join(', ')} und ${list[list.length - 1]}`;
  },

  /**
   * Erzeugt das standardisierte Alexa Response JSON Objekt.
   * @param {string} text - Vorzulesender Text
   * @param {boolean} shouldEndSession - Ob die Alexa Session beendet werden soll
   * @param {string} [repromptText] - Text für Nachfrage, falls Session offen bleibt
   * @returns {Object}
   */
  buildResponse: function (text, shouldEndSession, repromptText) {
    const response = {
      version: '1.0',
      response: {
        outputSpeech: {
          type: 'PlainText',
          text: text
        },
        shouldEndSession: shouldEndSession === true
      }
    };

    if (repromptText && !shouldEndSession) {
      response.response.reprompt = {
        outputSpeech: {
          type: 'PlainText',
          text: repromptText
        }
      };
    }

    return response;
  }
};
