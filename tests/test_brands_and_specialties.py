"""Unit tests for brands, standalone products, grain styles, and adjectives."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine

@pytest.fixture
def nlu():
    return NLUParsingEngine()

@pytest.fixture
def catalog():
    return [
        "Pizza", "Mineralwasser", "Butter", "Spaghetti", "Nudeln",
        "Toast", "Brot", "Käse", "Mozzarella", "Parmesan", "Dosentomaten"
    ]

@pytest.fixture
def catalog_sections():
    return {
        "cola": ["Cola", "Getränke"],
        "spezi": ["Spezi", "Getränke"],
        "energy drink": ["Energy Drink", "Getränke"],
        "bier": ["Bier", "Getränke"],
        "waschmittel": ["Waschmittel", "Haushalt"],
        "taschentücher": ["Taschentücher", "Pflege & Gesundheit"],
        "zahnpasta": ["Zahnpasta", "Pflege & Gesundheit"],
        "pizza": ["Pizza", "Fertig- & Tiefkühlprodukte"],
        "toast": ["Toast", "Brot & Gebäck"],
        "käse": ["Käse", "Milch & Käse"]
    }

def test_standalone_products_exact_preservation(nlu, catalog):
    standalones = [
        "Coca-Cola Zero", "Paulaner Spezi", "Red Bull", "Monster Energy",
        "Club-Mate", "Kinder Bueno", "Ritter Sport", "Mini Babybel"
    ]
    for prod in standalones:
        p = nlu.parse_items(prod, catalog)
        assert len(p) == 1, f"Failed parsing standalone product '{prod}'"
        assert p[0]["name"].lower().replace("-", " ") == prod.lower().replace("-", " ")

def test_brand_and_product_collision_free_preservation(nlu, catalog):
    # Gustavo Gusto Pizza -> Gustavo Gusto Pizza (collision-free, icon resolved downstream)
    p1 = nlu.parse_items("Gustavo Gusto Pizza", catalog)
    assert p1[0]["name"] == "Gustavo Gusto Pizza"
    assert p1[0]["specification"] == ""

    # Pizza Gustavo Gusto -> Pizza Gustavo Gusto
    p2 = nlu.parse_items("Pizza Gustavo Gusto", catalog)
    assert p2[0]["name"] == "Pizza Gustavo Gusto"
    assert p2[0]["specification"] == ""

    # Gerolsteiner Mineralwasser -> Gerolsteiner Mineralwasser
    p3 = nlu.parse_items("Gerolsteiner Mineralwasser", catalog)
    assert p3[0]["name"] == "Gerolsteiner Mineralwasser"
    assert p3[0]["specification"] == ""

    # Kerrygold Butter -> Kerrygold Butter
    p4 = nlu.parse_items("Kerrygold Butter", catalog)
    assert p4[0]["name"] == "Kerrygold Butter"
    assert p4[0]["specification"] == ""

    # Barilla Spaghetti -> Barilla Spaghetti
    p5 = nlu.parse_items("Barilla Spaghetti", catalog)
    assert p5[0]["name"] == "Barilla Spaghetti"
    assert p5[0]["specification"] == ""

def test_unambiguous_brand_icon_and_section(nlu, catalog_sections):
    # Coca-Cola Zero -> Cola (Getränke)
    icon, sec = nlu.resolve_icon_and_section("Coca-Cola Zero", catalog_sections)
    assert icon == "Cola"
    assert sec == "Getränke"

    # Paulaner Spezi -> Spezi (Getränke)
    icon, sec = nlu.resolve_icon_and_section("Paulaner Spezi", catalog_sections)
    assert icon == "Spezi"
    assert sec == "Getränke"

    # Red Bull -> Energy Drink (Getränke)
    icon, sec = nlu.resolve_icon_and_section("Red Bull", catalog_sections)
    assert icon == "Energy Drink"
    assert sec == "Getränke"

    # Augustiner -> Bier (Getränke)
    icon, sec = nlu.resolve_icon_and_section("Augustiner", catalog_sections)
    assert icon == "Bier"
    assert sec == "Getränke"

    # Persil -> Waschmittel (Haushalt)
    icon, sec = nlu.resolve_icon_and_section("Persil", catalog_sections)
    assert icon == "Waschmittel"
    assert sec == "Haushalt"

def test_grain_styles_and_diets(nlu, catalog):
    # Vollkorntoast -> Vollkorntoast
    p1 = nlu.parse_items("Vollkorntoast", catalog)
    assert p1[0]["name"] == "Vollkorntoast"
    assert p1[0]["specification"] == ""

    # Toast Vollkorn -> Vollkorntoast
    p2 = nlu.parse_items("Toast Vollkorn", catalog)
    assert p2[0]["name"] == "Vollkorntoast"
    assert p2[0]["specification"] == ""

    # Dinkelbrot -> Dinkelbrot
    p3 = nlu.parse_items("Dinkelbrot", catalog)
    assert p3[0]["name"] == "Dinkelbrot"
    assert p3[0]["specification"] == ""

    # Glutenfreie Nudeln -> Glutenfreie Nudeln
    p4 = nlu.parse_items("glutenfreie Nudeln", catalog)
    assert p4[0]["name"] == "Glutenfreie Nudeln"
    assert p4[0]["specification"] == ""

def test_german_grammar_and_adjectives(nlu, catalog):
    # Geriebener Käse -> Käse (gerieben)
    p1 = nlu.parse_items("geriebener Käse", catalog)
    assert p1[0]["name"] == "Käse"
    assert "gerieben" in p1[0]["specification"]

    # Geriebener Gouda -> Käse (Gouda gerieben)
    p2 = nlu.parse_items("geriebener Gouda", catalog)
    assert p2[0]["name"] == "Käse"
    assert "Gouda gerieben" in p2[0]["specification"]

    # Geriebener Mozzarella -> Mozzarella (gerieben)
    p3 = nlu.parse_items("geriebener Mozzarella", catalog)
    assert p3[0]["name"] == "Mozzarella"
    assert "gerieben" in p3[0]["specification"]

    # Gehackte Tomaten -> Dosentomaten
    p4 = nlu.parse_items("gehackte Tomaten", catalog)
    assert p4[0]["name"] == "Dosentomaten"

    # Passierte Tomaten -> Dosentomaten
    p5 = nlu.parse_items("passierte Tomaten", catalog)
    assert p5[0]["name"] == "Dosentomaten"
