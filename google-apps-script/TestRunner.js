/**
 * @file TestRunner.js
 * @description Integrierte Test-Suite für Google Apps Script.
 * Ermöglicht das Testen aller Funktionen direkt im Editor ohne echten Echo oder Webhook.
 */

const TestRunner = {
  /**
   * Test 1: Bring! Verbindung und Listenabruf testen.
   */
  testBringConnection: function () {
    Logger.log('--- TEST 1: Bring! API Verbindung ---');
    try {
      BringApi.clearTokenCache();
      const auth = BringApi.authenticate();
      Logger.log(`✅ Login erfolgreich!`);
      Logger.log(`   - User UUID: ${auth.uuid}`);
      Logger.log(`   - Public UUID: ${auth.publicUuid}`);
      Logger.log(`   - Standard-Liste UUID: ${auth.bringListUUID || 'wird ermittelt'}`);

      const lists = BringApi.getLists();
      Logger.log(`📋 Gefundene Listen (${lists.length}):`);
      lists.forEach(l => Logger.log(`   - ${l.name} (UUID: ${l.listUuid})`));

      const targetUuid = BringApi.getTargetListUuid();
      Logger.log(`🎯 Gewählte Ziel-Liste UUID: ${targetUuid}`);

      const items = BringApi.getListItems(targetUuid);
      Logger.log(`🛒 Aktuelle Artikel (${items.purchase.length}):`);
      items.purchase.forEach(i => Logger.log(`   - ${i.specification ? i.specification + ' ' : ''}${i.name}`));

      Logger.log('✅ TEST 1 erfolgreich abgeschlossen!');
    } catch (e) {
      Logger.log(`❌ TEST 1 FEHLGESCHLAGEN: ${e.message}`);
    }
  },

  /**
   * Test 2: Spracherkennung und Multi-Item Parsing testen.
   */
  testItemParser: function () {
    Logger.log('--- TEST 2: ItemParser Logik-Test ---');

    const testCases = [
      'setze Bananen auf die Einkaufsliste',
      'pack 2 Kilo Äpfel, 500g Hackfleisch und 3 Flaschen Cola auf den Einkaufszettel',
      'Milch, Butter sowie 6 Eier',
      'eine Packung Kaffee und zwei Kästen Mineralwasser',
      'wir brauchen noch Brot und Käse',
      'Tomaten'
    ];

    testCases.forEach((text, idx) => {
      Logger.log(`\nTestfall ${idx + 1}: "${text}"`);
      const parsed = ItemParser.parse(text);
      parsed.forEach(p => {
        Logger.log(`  ➔ Artikel: "${p.name}" | Menge/Spezifikation: "${p.specification}"`);
      });
    });

    Logger.log('\n✅ TEST 2 erfolgreich abgeschlossen!');
  },

  /**
   * Test 3: Simulierter Alexa AddItemsIntent Request.
   */
  testSimulatedAlexaAddItems: function () {
    Logger.log('--- TEST 3: Simulierter Alexa AddItemsIntent ---');

    const fakeAlexaRequest = {
      version: '1.0',
      session: {
        new: true,
        application: { applicationId: Config.get().alexaSkillId || 'amzn1.ask.skill.fake' }
      },
      request: {
        type: 'IntentRequest',
        intent: {
          name: 'AddItemsIntent',
          slots: {
            Items: {
              name: 'Items',
              value: 'Bananen und 2 Kilo Äpfel'
            }
          }
        }
      }
    };

    const response = AlexaSkillHandler.handleRequest(fakeAlexaRequest);
    Logger.log(`Alexa Antwort:\n${JSON.stringify(response, null, 2)}`);
    Logger.log('✅ TEST 3 erfolgreich abgeschlossen!');
  },

  /**
   * Test 4: Simulierter Home Assistant Webhook Request.
   */
  testSimulatedHomeAssistantWebhook: function () {
    Logger.log('--- TEST 4: Simulierter Home Assistant Webhook ---');

    const fakeEvent = {
      postData: {
        contents: JSON.stringify({
          text: 'setze 500g Erdbeeren und Schlagsahne auf die Einkaufsliste',
          key: Config.get().apiSecretKey
        })
      }
    };

    const response = doPost(fakeEvent);
    Logger.log(`Webhook Antwort:\n${response.getContent()}`);
    Logger.log('✅ TEST 4 erfolgreich abgeschlossen!');
  }
};

// Schnellzugriff-Funktionen für das Ausführen-Dropdown im Script Editor
function runTestBringConnection() {
  TestRunner.testBringConnection();
}

function runTestItemParser() {
  TestRunner.testItemParser();
}

function runTestSimulatedAlexa() {
  TestRunner.testSimulatedAlexaAddItems();
}

function runTestSimulatedWebhook() {
  TestRunner.testSimulatedHomeAssistantWebhook();
}
