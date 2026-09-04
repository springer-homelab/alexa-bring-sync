"""Unit tests for BringActiveItemsSensor and Coordinator attributes."""
from unittest.mock import MagicMock
from custom_components.alexa_bring.sensor import BringActiveItemsSensor

def test_sensor_state_and_attributes():
    coordinator = MagicMock()
    coordinator.data = {
        "items": ["Haferkekse (1 Packung)", "Pizza (Gustavo Gusto)"],
        "count": 2,
        "last_synced": "2026-09-04T23:30:00+00:00",
        "last_action": "voice_command",
        "last_spoken_text": "Setze Haferkekse auf die Liste",
    }

    sensor = BringActiveItemsSensor(coordinator)
    assert sensor.native_value == 2
    attrs = sensor.extra_state_attributes
    assert attrs["total_items"] == 2
    assert attrs["last_synced"] == "2026-09-04T23:30:00+00:00"
    assert attrs["last_action"] == "voice_command"
    assert attrs["last_spoken_text"] == "Setze Haferkekse auf die Liste"
    assert len(attrs["items"]) == 2

def test_sensor_empty_state():
    coordinator = MagicMock()
    coordinator.data = None

    sensor = BringActiveItemsSensor(coordinator)
    assert sensor.native_value == 0
    attrs = sensor.extra_state_attributes
    assert attrs["total_items"] == 0
    assert attrs["last_synced"] is None
    assert attrs["last_action"] == "idle"
    assert attrs["items"] == []
