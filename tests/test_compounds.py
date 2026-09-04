"""Unit tests for compound words, non-destructive custom items, and STT splitting."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def catalog():
    return [
        "Milch", "Butter", "Käse", "Brot", "Kekse", "Wurst",
        "Kartoffelsalat", "Nudelsalat", "Apfelsaft", "Orangensaft",
        "Olivenöl", "Frischkäse", "Tomatenmark", "Hackfleisch",
        "Kochschinken", "Bratwurst", "Backpulver", "Puderzucker"
    ]

@pytest.fixture
def catalog_sections():
    return {
        "kekse": ["Kekse", "Snacks & Süsswaren"],
        "wurst": ["Wurst", "Fleisch & Fisch"],
        "milch": ["Milch", "Milch & Käse"],
        "quark": ["Quark", "Milch & Käse"],
        "brot": ["Brot", "Brot & Gebäck"]
    }

def test_custom_compounds_non_destructive_naming(nlu, catalog):
    # Non-destructive: custom items MUST retain their full name
    p1 = nlu.parse_items("Nutellakekse", catalog)
    assert len(p1) == 1
    assert p1[0]["name"] == "Nutellakekse"

    p2 = nlu.parse_items("Haferkekse", catalog)
    assert len(p2) == 1
    assert p2[0]["name"] == "Haferkekse"

    p3 = nlu.parse_items("Dosenwurst", catalog)
    assert len(p3) == 1
    assert p3[0]["name"] == "Dosenwurst"

def test_custom_compounds_native_icon_resolution(nlu, catalog_sections):
    # Nutellakekse gets Kekse icon & Snacks section
    icon, sec = nlu.resolve_icon_and_section("Nutellakekse", catalog_sections)
    assert icon == "Kekse"
    assert sec == "Snacks & Süsswaren"

    # Haferkekse gets Kekse icon
    icon, sec = nlu.resolve_icon_and_section("Haferkekse", catalog_sections)
    assert icon == "Kekse"
    assert sec == "Snacks & Süsswaren"

    # Dosenwurst gets Wurst icon & Fleisch & Fisch section
    icon, sec = nlu.resolve_icon_and_section("Dosenwurst", catalog_sections)
    assert icon == "Wurst"
    assert sec == "Fleisch & Fisch"

def test_glued_stt_compounds(nlu, catalog):
    # BrotButter -> Brot, Butter
    items = nlu.smart_split_consecutive("BrotButter", catalog)
    assert "Brot" in items and "Butter" in items

    # MilchKäse -> Milch, Käse
    items2 = nlu.smart_split_consecutive("MilchKäse", catalog)
    assert "Milch" in items2 and "Käse" in items2

def test_protected_compounds_never_split(nlu, catalog):
    protected = [
        "Kartoffelsalat", "Nudelsalat", "Apfelsaft", "Orangensaft",
        "Olivenöl", "Frischkäse", "Tomatenmark", "Hackfleisch",
        "Kochschinken", "Bratwurst", "Backpulver", "Puderzucker"
    ]
    for item in protected:
        parsed = nlu.parse_items(item, catalog)
        assert len(parsed) == 1, f"Protected compound '{item}' was wrongly split!"
        assert parsed[0]["name"].lower().replace("ö", "o").replace("ä", "a") == item.lower().replace("ö", "o").replace("ä", "a")
