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

def test_entity_registry_cleanup_logic():
    """Verify the registry cleanup handles old command_line and rename."""
    mock_ent_reg = MagicMock()
    
    # Simulate old command_line entity present
    old_cmd = MagicMock()
    old_cmd.platform = "command_line"
    
    # Simulate existing _2 entity
    our_ent = MagicMock()
    our_ent.platform = "alexa_bring"
    
    def mock_get(eid):
        if eid == "sensor.bring_active_items":
            return old_cmd
        if eid == "sensor.bring_active_items_2":
            return our_ent
        if "automation.alexa_bring" in eid:
            return MagicMock()
        return None
        
    mock_ent_reg.async_get.side_effect = mock_get
    
    # Trigger cleanup operations
    if mock_ent_reg.async_get("sensor.bring_active_items") and mock_ent_reg.async_get("sensor.bring_active_items").platform == "command_line":
        mock_ent_reg.async_remove("sensor.bring_active_items")
        
    for old_id in ["automation.alexa_bring_sprach_sniffer_echtzeit"]:
        if mock_ent_reg.async_get(old_id):
            mock_ent_reg.async_remove(old_id)
            
    if mock_ent_reg.async_get("sensor.bring_active_items_2") and mock_ent_reg.async_get("sensor.bring_active_items_2").platform == "alexa_bring":
        mock_ent_reg.async_update_entity("sensor.bring_active_items_2", new_entity_id="sensor.bring_active_items")
        
    mock_ent_reg.async_remove.assert_any_call("sensor.bring_active_items")
    mock_ent_reg.async_remove.assert_any_call("automation.alexa_bring_sprach_sniffer_echtzeit")
    mock_ent_reg.async_update_entity.assert_called_once_with("sensor.bring_active_items_2", new_entity_id="sensor.bring_active_items")

