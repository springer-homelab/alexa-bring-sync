import os
import sys
from unittest.mock import MagicMock

# Ensure repository root is on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Base class mocks for Entity & CoordinatorEntity to avoid metaclass conflict
class MockEntity:
    def __init__(self, *args, **kwargs):
        pass

class MockSensorEntity(MockEntity):
    pass

class MockCoordinatorEntity(MockEntity):
    def __init__(self, coordinator, *args, **kwargs):
        self.coordinator = coordinator

# Mock voluptuous if not installed in lightweight environments
if "voluptuous" not in sys.modules:
    sys.modules["voluptuous"] = MagicMock()

# Mock Home Assistant modules so unit tests can run standalone without heavy HA core dependencies
ha_mock_modules = [
    "homeassistant",
    "homeassistant.core",
    "homeassistant.const",
    "homeassistant.config_entries",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.event",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.entity_platform",
    "homeassistant.components",
    "homeassistant.components.sensor",
]

for mod in ha_mock_modules:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
