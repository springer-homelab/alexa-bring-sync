"""Unit tests for operation detection (add, remove, check-off, separated verbs)."""
import pytest
from custom_components.alexa_bring.nlu_parser import detect_operation

def test_add_operations():
    # Explicit add commands
    assert detect_operation("Setze Milch auf die Einkaufsliste") == "TO_PURCHASE"
    assert detect_operation("Pack Butter auf den Einkaufszettel") == "TO_PURCHASE"
    assert detect_operation("Schreib 2 Bananen auf die Liste") == "TO_PURCHASE"
    assert detect_operation("Wir brauchen noch Kaffee") == "TO_PURCHASE"
    assert detect_operation("Kauf bitte Brot") == "TO_PURCHASE"
    assert detect_operation("Füge Haferkekse hinzu") == "TO_PURCHASE"
    
    # Implicit additions
    assert detect_operation("2 Bananen und 1 Brot") == "TO_PURCHASE"
    assert detect_operation("Milch, Käse und Eier") == "TO_PURCHASE"

def test_removal_operations():
    assert detect_operation("Milch löschen") == "TO_RECENTLY"
    assert detect_operation("Butter von der Liste entfernen") == "TO_RECENTLY"
    assert detect_operation("Schinken streichen") == "TO_RECENTLY"
    assert detect_operation("Nimm Käse von der Einkaufsliste runter") == "TO_RECENTLY"
    assert detect_operation("Lösche 2 Bananen") == "TO_RECENTLY"
    assert detect_operation("Entferne Brot") == "TO_RECENTLY"

def test_checkoff_operations():
    assert detect_operation("Bitte Haferkekse abhaken") == "TO_RECENTLY"
    assert detect_operation("Milch gekauft") == "TO_RECENTLY"
    assert detect_operation("Brot ist erledigt") == "TO_RECENTLY"
    assert detect_operation("Butter abgehakt") == "TO_RECENTLY"

def test_separated_german_prefix_verbs():
    # 'ab' or 'weg' separated from verb
    assert detect_operation("Hak Haferkekse ab") == "TO_RECENTLY"
    assert detect_operation("Hake Milch ab") == "TO_RECENTLY"
    assert detect_operation("Hak bitte Brot ab") == "TO_RECENTLY"

def test_resolve_removal_target():
    from custom_components.alexa_bring.nlu_parser import NLUParsingEngine
    nlu = NLUParsingEngine()
    active_items = ["Gustavo Gusto Pizza", "Nutellakekse", "Dosenwurst", "Vollkornspaghetti"]

    # Exact
    assert nlu.resolve_removal_target("Nutellakekse", active_items) == "Nutellakekse"

    # Brand shorthand / omission
    assert nlu.resolve_removal_target("Gustavo Gusto", active_items) == "Gustavo Gusto Pizza"
    assert nlu.resolve_removal_target("Gustavo", active_items) == "Gustavo Gusto Pizza"
    assert nlu.resolve_removal_target("Gustavo Gusto Pizza", active_items) == "Gustavo Gusto Pizza"

    # Single category noun on list
    assert nlu.resolve_removal_target("Pizza", active_items) == "Gustavo Gusto Pizza"

    # Non-matching item stays unchanged
    assert nlu.resolve_removal_target("Milch", active_items) == "Milch"
