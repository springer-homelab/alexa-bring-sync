"""DataUpdateCoordinator for Alexa-Bring! Sync."""
import logging
from datetime import timedelta
import aiohttp
import json
import os

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .bring_api import BringAPI
from .nlu_parser import NLUParsingEngine

_LOGGER = logging.getLogger(__name__)

class BringDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Bring! data."""

    def __init__(self, hass: HomeAssistant, api: BringAPI, nlu_engine: NLUParsingEngine):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=2),
        )
        self.api = api
        self.nlu_engine = nlu_engine

    async def _async_update_data(self):
        """Fetch data from API and apply beautification."""
        try:
            catalog = await self.api.get_catalog()
            raw_items = await self.api.get_active_items()
            
            # Auto-Beautify manually added items
            beautified_changes = []
            active_base_names = {
                (item.get('name') or item.get('itemId') or '').strip().lower()
                for item in raw_items
            }

            for item in raw_items:
                item_id = item.get('itemId') or item.get('name') or ''
                item_spec = item.get('specification') or ''
                if not item_id or item_id in catalog:
                    continue

                new_name, new_spec = self.nlu_engine.extract_brand_item(item_id, item_spec)
                # Prevent collision: if new_name is ALREADY on the active list (e.g. "Kekse" with another spec),
                # do NOT collapse into new_name as that would overwrite the existing item in Bring!
                if (
                    new_name != item_id
                    and new_name.strip().lower() not in active_base_names
                    and self.nlu_engine.is_valid_grocery_item(new_name, catalog)
                ):
                    beautified_changes.append({
                        'accuracy': '0.0', 'altitude': '0.0', 'latitude': '0.0', 'longitude': '0.0',
                        'itemId': item_id, 'spec': item_spec, 'operation': 'TO_RECENTLY'
                    })
                    beautified_changes.append({
                        'accuracy': '0.0', 'altitude': '0.0', 'latitude': '0.0', 'longitude': '0.0',
                        'itemId': new_name, 'spec': new_spec, 'operation': 'TO_PURCHASE'
                    })
                    active_base_names.discard(item_id.strip().lower())
                    active_base_names.add(new_name.strip().lower())
                    item['itemId'] = new_name
                    item['name'] = new_name
                    item['specification'] = new_spec

            if beautified_changes:
                _LOGGER.info("Beautifying %s items on Bring!", len(beautified_changes) // 2)
                await self.api.execute_batch_changes(beautified_changes)

            formatted_items = []
            for item in raw_items:
                name = item.get('name') or item.get('itemId')
                spec = item.get('specification') or ''
                full = f"{name} ({spec})".strip() if spec else name.strip()
                formatted_items.append(full)
                
            return {
                "items": formatted_items,
                "count": len(formatted_items),
                "catalog": catalog
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
