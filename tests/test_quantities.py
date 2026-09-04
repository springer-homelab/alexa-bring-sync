"""Comprehensive unit tests for quantity, number, and fraction parsing."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def catalog():
    return [
        "Milch", "Butter", "Brot", "Bananen", "Äpfel", "Eier", "Mehl",
        "Zucker", "Kaffee", "Hackfleisch", "Kartoffeln", "Gurke", "Bier"
    ]

def test_single_digits_and_tens(nlu, catalog):
    p1 = nlu.parse_items("zwei Bananen", catalog)
    assert p1[0]["name"] == "Bananen"
    assert p1[0]["specification"] == "2"

    p2 = nlu.parse_items("zehn Eier", catalog)
    assert p2[0]["name"] == "Eier"
    assert p2[0]["specification"] == "10"

    p3 = nlu.parse_items("fünfzehn Äpfel", catalog)
    assert p3[0]["name"] == "Äpfel"
    assert p3[0]["specification"] == "15"

    p4 = nlu.parse_items("dreiundzwanzig Eier", catalog)
    assert p4[0]["name"] == "Eier"
    assert p4[0]["specification"] == "23"

def test_decimals_and_punctuation(nlu, catalog):
    p1 = nlu.parse_items("1,5l Milch", catalog)
    assert p1[0]["name"] == "Milch"
    assert p1[0]["specification"] == "1.5l"

    p2 = nlu.parse_items("0.5 kg Mehl", catalog)
    assert p2[0]["name"] == "Mehl"
    assert p2[0]["specification"] == "0.5kg"

    p3 = nlu.parse_items("2.5 Liter Milch", catalog)
    assert p3[0]["name"] == "Milch"
    assert p3[0]["specification"] == "2.5l"

def test_spoken_fractions(nlu, catalog):
    p1 = nlu.parse_items("anderthalb Liter Milch", catalog)
    assert p1[0]["name"] == "Milch"
    assert p1[0]["specification"] == "1.5l"

    p2 = nlu.parse_items("eineinhalb Kilo Mehl", catalog)
    assert p2[0]["name"] == "Mehl"
    assert p2[0]["specification"] == "1.5kg"

    p3 = nlu.parse_items("zwei einhalb Liter Milch", catalog)
    assert p3[0]["name"] == "Milch"
    assert p3[0]["specification"] == "2.5l"

    p4 = nlu.parse_items("dreieinhalb Kilo Kartoffeln", catalog)
    assert p4[0]["name"] == "Kartoffeln"
    assert p4[0]["specification"] == "3.5kg"

    p5 = nlu.parse_items("drei einhalb Kilo Kartoffeln", catalog)
    assert p5[0]["name"] == "Kartoffeln"
    assert p5[0]["specification"] == "3.5kg"

def test_quarter_and_half_fractions(nlu, catalog):
    p1 = nlu.parse_items("dreiviertel Liter Milch", catalog)
    assert p1[0]["name"] == "Milch"
    assert p1[0]["specification"] == "0.75l"

    p2 = nlu.parse_items("ein halbes Kilo Mehl", catalog)
    assert p2[0]["name"] == "Mehl"
    assert p2[0]["specification"] == "0.5kg"

    p3 = nlu.parse_items("eine halbe Gurke", catalog)
    assert p3[0]["name"] == "Gurke"
    assert p3[0]["specification"] == "0.5"

    p4 = nlu.parse_items("ein viertel Kilo Butter", catalog)
    assert p4[0]["name"] == "Butter"
    assert p4[0]["specification"] == "0.25kg"

def test_colloquial_units(nlu, catalog):
    p1 = nlu.parse_items("ein Dutzend Eier", catalog)
    assert p1[0]["name"] == "Eier"
    assert p1[0]["specification"] == "12"

    p2 = nlu.parse_items("ein halbes Dutzend Eier", catalog)
    assert p2[0]["name"] == "Eier"
    assert p2[0]["specification"] == "6"

    p3 = nlu.parse_items("ein Pfund Hackfleisch", catalog)
    assert p3[0]["name"] == "Hackfleisch"
    assert p3[0]["specification"] == "500g"

    p4 = nlu.parse_items("ein halbes Pfund Butter", catalog)
    assert p4[0]["name"] == "Butter"
    assert p4[0]["specification"] == "250g"

def test_trailing_numbers_and_units(nlu, catalog):
    p1 = nlu.parse_items("Milch 2 Flaschen", catalog)
    assert p1[0]["name"] == "Milch"
    assert p1[0]["specification"] == "2 Flaschen"

    p2 = nlu.parse_items("Brot 1", catalog)
    assert p2[0]["name"] == "Brot"
    assert p2[0]["specification"] == "1"

    p3 = nlu.parse_items("Bier 1 Kasten", catalog)
    assert p3[0]["name"] == "Bier"
    assert p3[0]["specification"] == "1 Kasten"

def test_von_dem_phrasing(nlu, catalog):
    p1 = nlu.parse_items("2 Packungen von der Butter", catalog)
    assert p1[0]["name"] == "Butter"
    assert p1[0]["specification"] == "2 Packungen"

    p2 = nlu.parse_items("3 Stück von den Bananen", catalog)
    assert p2[0]["name"] == "Bananen"
    assert p2[0]["specification"] == "3 Stück"

def test_unit_formatting_abbreviations(nlu):
    assert nlu.format_specification("500 gramm") == "500g"
    assert nlu.format_specification("2 kilogramm") == "2kg"
    assert nlu.format_specification("1 kilo") == "1kg"
    assert nlu.format_specification("1.5 liter") == "1.5l"
    assert nlu.format_specification("250 milliliter") == "250ml"
    assert nlu.format_specification("2 meter") == "2m"
    assert nlu.format_specification("3 packungen") == "3 Packungen"
    assert nlu.format_specification("4 flaschen") == "4 Flaschen"
    assert nlu.format_specification("2 dosen") == "2 Dosen"
    assert nlu.format_specification("1 gläser") == "1 Gläser"
