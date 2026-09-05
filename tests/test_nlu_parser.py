"""Unit tests for NLUParsingEngine and operation detection."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine, detect_operation

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def catalog():
    return [
        "Milch", "Butter", "Käse", "Brot", "Toast", "Pizza", "Kekse", "Bananen",
        "Tomaten", "Mehl", "Zucker", "Kaffee", "Mineralwasser", "Cola", "Wurst",
        "Hafermilch", "Semmeln", "Topfen", "Karfiol", "Faschiertes", "Kräuter"
    ]

@pytest.fixture
def catalog_sections():
    return {
        "kekse": ["Kekse", "Snacks & Süsswaren"],
        "wurst": ["Wurst", "Fleisch & Fisch"],
        "milch": ["Milch", "Milch & Käse"],
        "toast": ["Toast", "Brot & Gebäck"],
        "pizza": ["Pizza", "Fertig- & Tiefkühlprodukte"],
        "kräuter": ["Kräuter", "Obst & Gemüse"],
    }

def test_operation_detection():
    # Removal / Check-off operations
    assert detect_operation("bitte Haferkekse abhaken") == "TO_RECENTLY"
    assert detect_operation("Milch gekauft") == "TO_RECENTLY"
    assert detect_operation("Brot ist erledigt") == "TO_RECENTLY"
    assert detect_operation("Kekse löschen") == "TO_RECENTLY"
    assert detect_operation("Butter von der Liste entfernen") == "TO_RECENTLY"
    assert detect_operation("Schinken streichen") == "TO_RECENTLY"
    assert detect_operation("Hak Haferkekse ab") == "TO_RECENTLY"

    # Add operations
    assert detect_operation("2 Bananen und 1 Brot") == "TO_PURCHASE"
    assert detect_operation("Setze Milch auf die Einkaufsliste") == "TO_PURCHASE"

def test_quantity_and_units(nlu, catalog):
    items = nlu.parse_items("2 Packungen Haferkekse und 3 Flaschen Milch", catalog)
    assert len(items) == 2
    assert items[0]["name"] == "Haferkekse"
    assert items[0]["specification"] == "2 Packungen"
    assert items[1]["name"] == "Milch"
    assert items[1]["specification"] == "3 Flaschen"

def test_specification_extraction_for_catalog_items(nlu, catalog):
    # Brand + Catalog Item (preserved collision-free)
    p1 = nlu.parse_items("Gustavo Gusto Pizza", catalog)
    assert len(p1) == 1
    assert p1[0]["name"] == "Gustavo Gusto Pizza"
    assert p1[0]["specification"] == ""

    # Catalog Item + Brand
    p2 = nlu.parse_items("Pizza Gustavo Gusto", catalog)
    assert len(p2) == 1
    assert p2[0]["name"] == "Pizza Gustavo Gusto"
    assert p2[0]["specification"] == ""

    # Grain style + Grain noun
    p3 = nlu.parse_items("Vollkorntoast", catalog)
    assert len(p3) == 1
    assert p3[0]["name"] == "Vollkorntoast"
    assert p3[0]["specification"] == ""

    p4 = nlu.parse_items("Dinkelbrot", catalog)
    assert len(p4) == 1
    assert p4[0]["name"] == "Dinkelbrot"
    assert p4[0]["specification"] == ""

def test_collision_free_coexistence(nlu, catalog):
    # Vollkornspaghetti and regular Spaghetti spoken together or consecutive
    items = nlu.parse_items("Vollkornspaghetti und Spaghetti", catalog)
    assert len(items) == 2
    names = [it["name"] for it in items]
    assert "Vollkornspaghetti" in names
    assert "Spaghetti" in names

    # With quantities
    items_q = nlu.parse_items("2 Packungen Vollkornspaghetti und 1 Packung Spaghetti", catalog)
    assert len(items_q) == 2
    by_name = {it["name"]: it["specification"] for it in items_q}
    assert by_name["Vollkornspaghetti"] == "2 Packungen"
    assert by_name["Spaghetti"] == "1 Packung"


def test_native_icon_and_section_resolution(nlu, catalog_sections):
    # Nutellakekse -> Kekse (Snacks & Süsswaren)
    icon, sec = nlu.resolve_icon_and_section("Nutellakekse", catalog_sections)
    assert icon == "Kekse"
    assert sec == "Snacks & Süsswaren"

    # Haferkekse -> Kekse (Snacks & Süsswaren)
    icon, sec = nlu.resolve_icon_and_section("Haferkekse", catalog_sections)
    assert icon == "Kekse"
    assert sec == "Snacks & Süsswaren"

    # Dosenwurst -> Wurst (Fleisch & Fisch)
    icon, sec = nlu.resolve_icon_and_section("Dosenwurst", catalog_sections)
    assert icon == "Wurst"
    assert sec == "Fleisch & Fisch"

def test_regional_vocabulary_and_synonyms(nlu, catalog):
    # Austrian / Swiss words
    items = nlu.parse_items("Semmeln und Topfen", catalog)
    names = [it["name"] for it in items]
    assert "Semmeln" in names or "Brötchen" in names
    assert "Topfen" in names or "Quark" in names

def test_smart_split_consecutive(nlu, catalog):
    items = nlu.parse_items("2 Bananen, Hafermilch und Nutellakekse", catalog)
    assert len(items) == 3
    names = [it["name"] for it in items]
    assert "Bananen" in names
    assert "Hafermilch" in names
    assert "Nutellakekse" in names
