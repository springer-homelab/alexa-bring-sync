"""Unit tests for regional DACH dialects (Austria/Switzerland) and Drogerie/Haushalt."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def german_catalog():
    return ["Quark", "Sahne", "Brötchen", "Blumenkohl", "Hackfleisch", "Tomaten", "Kartoffeln", "Aprikosen", "Pilze", "Toilettenpapier", "Geschirrtabs"]

@pytest.fixture
def austrian_catalog():
    return ["Topfen", "Schlagobers", "Semmeln", "Karfiol", "Faschiertes", "Paradeiser", "Erdäpfel", "Marillen", "Schwammerl"]

def test_austrian_synonyms_to_standard_german(nlu, german_catalog):
    # When catalog is Standard German, Austrian terms map to canonical catalog entries
    assert nlu.parse_items("Topfen", german_catalog)[0]["name"] == "Quark"
    assert nlu.parse_items("Schlagobers", german_catalog)[0]["name"] == "Sahne"
    assert nlu.parse_items("Semmeln", german_catalog)[0]["name"] == "Brötchen"
    assert nlu.parse_items("Karfiol", german_catalog)[0]["name"] == "Blumenkohl"
    assert nlu.parse_items("Faschiertes", german_catalog)[0]["name"] == "Hackfleisch"
    assert nlu.parse_items("Paradeiser", german_catalog)[0]["name"] == "Tomaten"
    assert nlu.parse_items("Erdäpfel", german_catalog)[0]["name"] == "Kartoffeln"
    assert nlu.parse_items("Marillen", german_catalog)[0]["name"] == "Aprikosen"
    assert nlu.parse_items("Schwammerl", german_catalog)[0]["name"] == "Pilze"

def test_austrian_localized_catalog_preservation(nlu, austrian_catalog):
    # When catalog contains Austrian regional terms natively, they MUST NOT be altered
    assert nlu.parse_items("Topfen", austrian_catalog)[0]["name"] == "Topfen"
    assert nlu.parse_items("Semmeln", austrian_catalog)[0]["name"] == "Semmeln"
    assert nlu.parse_items("Karfiol", austrian_catalog)[0]["name"] == "Karfiol"

def test_drogerie_and_household(nlu, german_catalog):
    # Klopapier -> Toilettenpapier
    p1 = nlu.parse_items("Klopapier", german_catalog)
    assert p1[0]["name"] == "Toilettenpapier"

    # Spülmaschinentabs -> Geschirrtabs
    p2 = nlu.parse_items("Spülmaschinentabs", german_catalog)
    assert p2[0]["name"] == "Geschirrtabs"

def test_drogerie_icon_and_section_resolution(nlu):
    icon, sec = nlu.resolve_icon_and_section("Klopapier")
    assert icon == "Toilettenpapier"
    assert sec == "Haushalt"

    icon, sec = nlu.resolve_icon_and_section("Spülmaschinentabs")
    assert icon == "Geschirrtabs"
    assert sec == "Haushalt"
