"""Sensor platform for Alexa-Bring! Sync."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BringDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([BringActiveItemsSensor(coordinator)])

class BringActiveItemsSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Bring! active items sensor."""

    def __init__(self, coordinator: BringDataUpdateCoordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Bring Active Items"
        self._attr_unique_id = f"{DOMAIN}_active_items"
        self._attr_icon = "mdi:cart-outline"

    @property
    def native_value(self):
        """Return the state of the sensor (item count)."""
        if self.coordinator.data:
            return self.coordinator.data.get("count", 0)
        return 0

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        if self.coordinator.data:
            return {"items": self.coordinator.data.get("items", [])}
        return {"items": []}
