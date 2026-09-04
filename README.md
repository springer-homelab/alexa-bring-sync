# 🛒 Alexa to Bring! Sync (Home Assistant Integration)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-brightgreen.svg?logo=home-assistant)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Bring! API](https://img.shields.io/badge/Bring!-v2%20API-orange.svg)](https://www.getbring.com/)

> **Die native Home Assistant Custom Integration für nahtlose Sprachsynchronisation zwischen Amazon Echo (Alexa) und deiner Bring! Einkaufsliste.**  
> Keine YAML-Konfiguration, keine manuellen Python-Skripte mehr – 100 % Konfiguration über die Benutzeroberfläche (UI) inklusive HACS-Unterstützung und automatischer Lebensmittel-Erkennung (NLU).

---

## 🌟 Highlights & Funktionen

* 🗣️ **Nativer Alexa-Sprachbefehl:**  
  *„Alexa, setze 2 Bananen, Hafermilch und Nutellakekse auf die Einkaufsliste“*
* 🧠 **Fortschrittliche NLU (Natural Language Understanding):**
  * **Mengenerkennung:** Erkennt Zahlen, Brüche und Einheiten (*„ein halbes Kilo Mehl“*, *„2 Packungen Butter“*) und trennt sie sauber in Mengenspezifikationen ab.
  * **Native Symbol- & Warengruppenzuweisung:** Weist Artikeln wie *„Nutellakekse“* oder *„Dosenwurst“* vollautomatisch das passende Bring!-Katalogicon (z.B. Keks 🍪 oder Wurst 🥫) und die richtige Warengruppe zu, ohne den echten Namen zu verändern.
  * **100 % Kollisionsfrei:** Beliebig viele Sorten derselben Kategorie (z.B. *„Nutellakekse“* UND *„Haferkekse“*) stehen gleichzeitig und friedlich nebeneinander auf der Liste, ohne sich gegenseitig zu überschreiben.
  * **Intelligente Spezifikationen:** Erkennt Marken und Sorten bei Basiskatalog-Artikeln (*„Gustavo Gusto Pizza“* ➔ **Pizza** mit Spezifikation *Gustavo Gusto*, *„Vollkorntoast“* ➔ **Toast** mit Spezifikation *Vollkorn*).
  * **Markenerkennung & Normalisierung:** Erkennt Marken (*„Paulaner Spezi“*, *„Coca Cola Zero“*, *„Alpro“*, *„Gösser“*) und ordnet sie sofort dem passenden Symbol zu.
  * **Deutscher Lemmatizer & Dialekt-Support:** Pluralformen, österreichische/schweizerische Dialektwörter (*„Semmeln“*, *„Topfen“*, *„Schlagobers“*, *„Faschiertes“*, *„Karfiol“*) werden nahtlos verstanden.
* 🔄 **Amazon Todo 1-Way Mirror:**  
  Hält die interne Amazon Alexa Todo-Liste synchron mit Bring!, sodass beide Listen immer denselben Stand zeigen.
* 📦 **Auto-Kategorisierung im Hintergrund:**  
  Auch wenn du unterwegs Einträge per Hand in der Bring!-App tippst, erkennt die Integration diese und weist im Hintergrund automatisch das passende Bring!-Icon und die Warengruppe zu.
* 🌐 **Over-The-Air (OTA) Lexikon-Updates:**  
  Das Lebensmittel- und Markenlexikon wird im Hintergrund automatisch alle 24 Stunden von GitHub aktualisiert – ganz ohne Neustart oder HACS-Update.
* 🖥️ **100 % UI-Konfiguration (Config Flow & Options Flow):**  
  Bring!-Zugangsdaten, Echo-Geräte (Multi-Select) und die Amazon-Liste werden bequem im Menü ausgewählt und können jederzeit über „Konfigurieren“ angepasst werden.

---

## 📋 Voraussetzungen

1. **Home Assistant** (mind. 2024.1)
2. **[HACS](https://hacs.xyz/)** (Home Assistant Community Store)
3. **[Alexa Media Player](https://github.com/alandtse/alexa_media_player)** (via HACS) – zum Erkennen der Spracheingaben auf deinen Amazon Echos.
4. **[Alexa To-do Lists](https://github.com/lonlazer/ha-alexa-todo-lists)** (via HACS, optional) – falls die interne Amazon Alexa Todo-Liste synchron gehalten werden soll.
5. Ein aktives **Bring! Konto** (E-Mail & Passwort).

---

## 🚀 Installation via HACS

1. Öffne **HACS** in Home Assistant.
2. Klicke oben rechts auf das Drei-Punkte-Menü (`...`) und wähle **Benutzerdefinierte Repositories** (*Custom repositories*).
3. Füge folgende Repository-URL ein:
   * **Repository:** `https://github.com/springer-homelab/alexa-bring-sync`
   * **Typ:** `Integration`
4. Klicke auf **Hinzufügen**.
5. Suche nach **Alexa to Bring! Sync** und klicke auf **Herunterladen**.
6. Starte Home Assistant neu.

---

## ⚙️ Einrichtung

1. Gehe in Home Assistant auf **Einstellungen ➔ Geräte & Dienste ➔ Integration hinzufügen**.
2. Suche nach **Alexa to Bring! Sync**.
3. **Schritt 1 (Bring! Zugangsdaten):**  
   Gib deine Bring! E-Mail-Adresse, dein Passwort und den gewünschten Listen-Namen ein (Standard: `Einkaufsliste`).
4. **Schritt 2 (Geräte auswählen):**  
   * **Echo Geräte:** Wähle alle Amazon Echo-Lautsprecher aus, die abgehört werden sollen (Mehrfachauswahl möglich).
   * **Amazon Todo Liste:** Wähle deine Alexa Todo-Liste für die automatische Synchronisation aus.
5. Fertig! 🎉

> **Tipp:** Du kannst die ausgewählten Echo-Lautsprecher und die Todo-Liste jederzeit unter *Einstellungen ➔ Geräte & Dienste ➔ Alexa to Bring! Sync ➔ Konfigurieren* ändern.

---

## 🏗️ Architektur

```mermaid
flowchart TD
    A["🗣️ Spracheingabe an Echo: 'Alexa, setze Milch auf die Einkaufsliste'"] --> B["Amazon Alexa Cloud"]
    B --> C["HACS: Alexa Media Player"]
    C -->|last_called_summary Event| D["alexa_bring Custom Integration"]
    
    subgraph AlexaBring ["alexa_bring Integration"]
        D --> E["NLUParsingEngine (Morphologie, Grammatik, Marken)"]
        E --> F["OTA Vocab Cache (GitHub Sync)"]
        E --> G["BringAPI (Async aiohttp v2)"]
    end
    
    G -->|Batch Change| H["🛒 Bring! Cloud API"]
    G -->|Update Coordinator| I["sensor.bring_active_items"]
    I -->|Reconcile| J["Amazon Todo Liste (1-Way Mirror)"]
```

---

## 📁 Repository-Struktur

```text
alexa-bring-sync/
├── custom_components/
│   └── alexa_bring/
│       ├── __init__.py           # Setup, native Event-Listener & Reconciler
│       ├── bring_api.py          # Asynchroner Bring! REST API v2 Client
│       ├── config_flow.py        # UI Setup & Options Flow (Geräteauswahl)
│       ├── const.py              # Konstanten & Domain-Definitionen
│       ├── coordinator.py        # Background Polling & Auto-Beautifier
│       ├── manifest.json         # Home Assistant Integrations-Metadaten
│       ├── nlu_parser.py         # Intelligente Sprachanalyse & Lemmatizer
│       ├── sensor.py             # Sensor für aktive Bring!-Einträge
│       ├── strings.json          # Textbausteine für das Setup
│       └── translations/         # Übersetzungen (Deutsch & Englisch)
├── bring_vocab.json              # Lebensmittel-, Marken- & Synonym-Lexikon
├── hacs.json                     # HACS Metadaten
├── LICENSE                       # MIT Lizenz
└── README.md                     # Dokumentation
```

---

## 📄 Lizenz

Dieses Projekt ist unter der [MIT-Lizenz](LICENSE) lizenziert.
