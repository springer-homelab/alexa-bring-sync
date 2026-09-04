"""Unit tests for multi-item spoken utterances, punctuation, and deduplication."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def catalog():
    return ["Bananen", "Brot", "Äpfel", "Milch", "Butter", "Käse", "Eier", "Mehl", "Zucker"]

def test_conjunctions_and_commas(nlu, catalog):
    items = nlu.parse_items("2 Bananen, 1 Brot und 3 Äpfel", catalog)
    assert len(items) == 3
    names = [it["name"] for it in items]
    assert "Bananen" in names and "Brot" in names and "Äpfel" in names
    item_map = {it["name"]: it["specification"] for it in items}
    assert item_map["Bananen"] == "2"
    assert item_map["Brot"] == "1"
    assert item_map["Äpfel"] == "3"

def test_simple_comma_separated_list(nlu, catalog):
    items = nlu.parse_items("Milch, Butter, Käse, Eier", catalog)
    assert len(items) == 4
    names = [it["name"] for it in items]
    assert names == ["Milch", "Butter", "Käse", "Eier"]

def test_consecutive_quantities_without_conjunctions(nlu, catalog):
    # '2 Bananen 3 Äpfel'
    items = nlu.parse_items("2 Bananen 3 Äpfel", catalog)
    assert len(items) == 2
    item_map = {it["name"]: it["specification"] for it in items}
    assert item_map["Bananen"] == "2"
    assert item_map["Äpfel"] == "3"

    # '1kg Mehl 500g Zucker'
    items2 = nlu.parse_items("1kg Mehl 500g Zucker", catalog)
    assert len(items2) == 2
    item_map2 = {it["name"]: it["specification"] for it in items2}
    assert item_map2["Mehl"] == "1kg"
    assert item_map2["Zucker"] == "500g"

def test_deduplication_and_specification_merging(nlu, catalog):
    # Duplicate item with specification should retain the specification
    items = nlu.parse_items("Milch und 2 Flaschen Milch", catalog)
    assert len(items) == 1
    assert items[0]["name"] == "Milch"
    assert items[0]["specification"] == "2 Flaschen"
