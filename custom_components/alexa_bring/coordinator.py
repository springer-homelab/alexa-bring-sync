"""DataUpdateCoordinator for Alexa-Bring! Sync."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .bring_api import BringAPI
from .nlu_parser import NLUParsingEngine

_LOGGER = logging.getLogger(__name__)

class BringDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Bring! data."""

    def __init__(self, hass: HomeAssistant, api: BringAPI, nlu_engine: NLUParsingEngine) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=2),
        )
        self.api = api
        self.nlu_engine = nlu_engine
        self.last_synced: str | None = None
        self.last_action: str = "initialized"
        self.last_spoken_text: str = ""

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API and apply beautification."""
        try:
            catalog = await self.api.get_catalog()
            raw_items = await self.api.get_active_items()
            details_map = await self.api.get_item_details_map()
            catalog_sections = await self.api.get_catalog_sections()

            # Auto-assign icons & categories to custom items missing details
            for item in raw_items:
                item_name = item.get('name') or item.get('itemId') or ''
                if not item_name:
                    continue

                low_name = item_name.strip().lower()
                # If item is not in catalog and has no detail yet, assign one
                if item_name not in catalog and low_name not in details_map:
                    icon, section = self.nlu_engine.resolve_icon_and_section(item_name, catalog_sections)
                    if icon:
                        _LOGGER.info("Auto-assigning Bring! detail to '%s': icon='%s', section='%s'", item_name, icon, section)
                        await self.api.save_item_detail(item_name, icon, section)

            formatted_items: list[str] = []
            for item in raw_items:
                name = item.get('name') or item.get('itemId')
                spec = item.get('specification') or ''
                full = f"{name} ({spec})".strip() if spec else name.strip()
                formatted_items.append(full)

            self.last_synced = datetime.now(timezone.utc).isoformat()

            return {
                "items": formatted_items,
                "count": len(formatted_items),
                "catalog": catalog,
                "last_synced": self.last_synced,
                "last_action": self.last_action,
                "last_spoken_text": self.last_spoken_text,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
