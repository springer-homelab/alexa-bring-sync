"""Unit tests for Alexa voice question filtering, shopping intent detection, and command stripping."""
import pytest
from custom_components.alexa_bring.nlu_parser import NLUParsingEngine, is_voice_question, has_shopping_intent

@pytest.fixture
def nlu():
    return NLUParsingEngine()

def test_is_voice_question():
    # Spoken questions that should be ignored by the sniffer
    assert is_voice_question("ist noch milch da?") is True
    assert is_voice_question("was steht auf der einkaufsliste?") is True
    assert is_voice_question("wie viele bananen haben wir?") is True
    assert is_voice_question("wo finde ich butter?") is True
    assert is_voice_question("wann kommt die lieferung?") is True
    assert is_voice_question("hast du milch aufgeschrieben?") is True
    assert is_voice_question("kannst du bitte brot aufschreiben?") is True
    assert is_voice_question("lies die einkaufsliste vor") is True
    assert is_voice_question("zeige mir die liste") is True
    assert is_voice_question("öffne bring") is True
    assert is_voice_question("starte die einkaufsliste") is True
    assert is_voice_question("spiel musik") is True
    assert is_voice_question("hast du eier auf der liste?") is True

    # Real shopping statements that must NOT be flagged as questions
    assert is_voice_question("setz milch auf die einkaufsliste") is False
    assert is_voice_question("pack butter auf den zettel") is False
    assert is_voice_question("2 bananen") is False
    assert is_voice_question("wir brauchen noch kaffee") is False

def test_has_shopping_intent():
    # Valid shopping intents
    assert has_shopping_intent("setz milch auf die einkaufsliste") is True
    assert has_shopping_intent("pack butter auf den zettel") is True
    assert has_shopping_intent("schreib eier auf die bring liste") is True
    assert has_shopping_intent("nimm käse von der liste") is True
    assert has_shopping_intent("haferkekse abhaken") is True
    assert has_shopping_intent("brot ist erledigt") is True
    assert has_shopping_intent("wir brauchen noch kaffee") is True
    assert has_shopping_intent("kauf bitte äpfel") is True
    assert has_shopping_intent("lösche schinken von der liste") is True

    # Non-shopping phrases
    assert has_shopping_intent("schalte das licht im wohnzimmer an") is False
    assert has_shopping_intent("wie wird das wetter morgen") is False
    assert has_shopping_intent("stelle einen timer auf 5 minuten") is False

def test_strip_command_phrases(nlu):
    assert nlu.strip_command_phrases("alexa setze bitte 2 brote auf die einkaufsliste") == "2 brote"
    assert nlu.strip_command_phrases("alexa mach 3 milch draus") == "3 milch"
    assert nlu.strip_command_phrases("ändere die menge von butter auf 2 packungen") == "2 packungen butter"
    assert nlu.strip_command_phrases("bitte streich schinken von unserer liste") == "schinken"
    assert nlu.strip_command_phrases("wir brauchen noch 5 eier") == "5 eier"
    assert nlu.strip_command_phrases("alexa kauf bitte kaffee") == "kaffee"
