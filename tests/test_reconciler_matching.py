"""Tests for smart item matching in todo reconciler."""
import pytest
from custom_components.alexa_bring.nlu_parser import is_item_match

def test_exact_matches():
    assert is_item_match("Milch", "Milch")
    assert is_item_match("brot", "Brot")
    assert is_item_match("Nutellakekse", "nutellakekse")

def test_compound_and_spacing_matches():
    # User spoken with space vs Bring compound single word
    assert is_item_match("Vollkorn Spaghetti", "Vollkornspaghetti")
    assert is_item_match("Vollkorn-Spaghetti", "Vollkornspaghetti")
    assert is_item_match("Hafer Kekse", "Haferkekse")
    assert is_item_match("Haferkekse", "Hafer Kekse")

def test_specification_parentheses_matches():
    # Bring has Name (Specification) vs Amazon flat utterance
    assert is_item_match("Vollkorn Spaghetti", "Spaghetti (Vollkorn)")
    assert is_item_match("Vollkornspaghetti", "Spaghetti (Vollkorn)")
    assert is_item_match("Gustavo Gusto Pizza", "Pizza (Gustavo Gusto)")
    assert is_item_match("Pizza (Gustavo Gusto)", "Gustavo Gusto Pizza")
    assert is_item_match("2 Packungen Butter", "Butter (2 Packungen)")
    assert is_item_match("Butter (2 Packungen)", "2 Packungen Butter")

def test_non_matches():
    # Similar prefixes or base items should NOT match
    assert not is_item_match("Milch", "Hafermilch")
    assert not is_item_match("Hafermilch", "Milch")
    assert not is_item_match("Toast", "Vollkorntoast")
    assert not is_item_match("Vollkorntoast", "Toast")
    assert not is_item_match("Spaghetti", "Vollkornspaghetti")
    assert not is_item_match("Vollkorn Spaghetti", "Spaghetti")
    assert not is_item_match("Vollkornbrot", "Vollkorn Spaghetti")
    assert not is_item_match("", "Milch")
    assert not is_item_match("Milch", "")

def test_reconcile_scenario_preserves_amazon_original():
    """Simulate reconciler loop to ensure Amazon original is not removed."""
    amazon_items = [
        {"summary": "Vollkorn Spaghetti"},
        {"summary": "Nutellakekse"},
    ]
    bring_items = [
        "Spaghetti (Vollkorn)",
        "Nutellakekse",
    ]
    
    items_to_remove = []
    items_to_add = bring_items.copy()
    
    for a_item in amazon_items:
        s = a_item.get("summary", "").strip()
        matched_bring = None
        for b_item in items_to_add:
            if is_item_match(s, b_item):
                matched_bring = b_item
                break
        if matched_bring:
            items_to_add.remove(matched_bring)
        else:
            items_to_remove.append(s)
            
    # Nothing should be removed from Amazon, nothing added!
    assert items_to_remove == []
    assert items_to_add == []
