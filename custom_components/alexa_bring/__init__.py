"""The Alexa-Bring! Sync integration."""
from __future__ import annotations

import logging
import time
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform, EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, CONF_LIST_NAME, SERVICE_SYNC_TEXT, ATTR_SPOKEN_TEXT, CONF_MEDIA_PLAYERS, CONF_TODO_LIST
from .bring_api import BringAPI
from .nlu_parser import NLUParsingEngine, detect_operation, is_voice_question, has_shopping_intent
from .coordinator import BringDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]

SERVICE_SYNC_SCHEMA = vol.Schema({
    vol.Required(ATTR_SPOKEN_TEXT): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alexa-Bring! Sync from a config entry."""
    session = async_get_clientsession(hass)
    cache_dir = hass.config.path(".storage")
    
    api = BringAPI(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        list_name=entry.data.get(CONF_LIST_NAME, "Einkaufsliste"),
        cache_dir=cache_dir
    )
    
    if not await api.authenticate():
        _LOGGER.error("Failed to authenticate with Bring!")
        return False
        
    nlu_engine = NLUParsingEngine()
    
    # Trigger OTA Vocab Download in background
    hass.async_create_task(nlu_engine.async_update_vocab(session, cache_dir))

    coordinator = BringDataUpdateCoordinator(hass, api, nlu_engine)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "nlu_engine": nlu_engine,
        "coordinator": coordinator,
        "listeners": []
    }

    # Clean up obsolete/orphaned legacy entities from previous YAML setup
    try:
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)

        # 1. Purge obsolete command_line sensor
        old_cmd = ent_reg.async_get("sensor.bring_active_items")
        if old_cmd and old_cmd.platform == "command_line":
            _LOGGER.info("Purging orphaned command_line sensor.bring_active_items")
            ent_reg.async_remove("sensor.bring_active_items")

        # 2. Purge obsolete legacy YAML automations & input_texts
        for old_id in [
            "automation.alexa_bring_sprach_sniffer_echtzeit",
            "automation.bring_alexa_amazon_liste_nach_einkauf_leeren",
            "automation.bring_amazon_listen_spiegelung_echtzeit",
            "automation.bring_alexa_gerauschlose_listen_synchronisation_http",
            "automation.bring_amazon_1_way_mirror_reconciler",
            "input_text.bring_synced_items",
            "input_text.bring_last_processed_command",
            "input_text.bring_last_called_timestamp",
        ]:
            if ent_reg.async_get(old_id):
                _LOGGER.info("Purging orphaned legacy entity %s", old_id)
                ent_reg.async_remove(old_id)

        # 3. Rename alexa_bring sensor_2 back to clean sensor.bring_active_items
        our_ent = ent_reg.async_get("sensor.bring_active_items_2")
        if our_ent and our_ent.platform == DOMAIN:
            _LOGGER.info("Renaming sensor.bring_active_items_2 -> sensor.bring_active_items")
            ent_reg.async_update_entity("sensor.bring_active_items_2", new_entity_id="sensor.bring_active_items")
    except Exception as err:
        _LOGGER.warning("Entity registry migration notice: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_sync_spoken_text(call: ServiceCall):
        """Handle the service call."""
        text = call.data.get(ATTR_SPOKEN_TEXT, "")
        if not text:
            return
            
        coordinator.last_spoken_text = text
        coordinator.last_action = "sync_spoken_text"
        op = detect_operation(text)
        catalog = await api.get_catalog()
        parsed_items = nlu_engine.parse_items(text, catalog)
        
        if not parsed_items:
            _LOGGER.info("No valid items parsed from: %s", text)
            return
            
        changes = []
        for item in parsed_items:
            changes.append({
                'accuracy': '0.0', 'altitude': '0.0', 'latitude': '0.0', 'longitude': '0.0',
                'itemId': item['name'], 'spec': item['specification'], 'operation': op
            })
            
        if changes:
            success = await api.execute_batch_changes(changes)
            if success:
                _LOGGER.info("Successfully synced to Bring!: %s", changes)
                if op == 'TO_PURCHASE':
                    catalog_sections = await api.get_catalog_sections()
                    details_map = await api.get_item_details_map()
                    for item in parsed_items:
                        item_name = item['name']
                        low_name = item_name.strip().lower()
                        if item_name not in catalog and low_name not in details_map:
                            icon, section = nlu_engine.resolve_icon_and_section(item_name, catalog_sections)
                            if icon and icon.lower() != low_name:
                                hass.async_create_task(api.save_item_detail(item_name, icon, section))
                await coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to sync items to Bring!")

    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_TEXT, handle_sync_spoken_text, schema=SERVICE_SYNC_SCHEMA
    )

    # --- NATIVE AUTOMATION LOGIC ---
    media_players = entry.options.get(CONF_MEDIA_PLAYERS, [])
    todo_list = entry.options.get(CONF_TODO_LIST)

    # 1. Alexa Voice Sniffer
    if media_players:
        last_processed = {"summary": "", "time": 0.0}

        async def alexa_state_changed_listener(event: Event):
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            
            if not new_state or not old_state:
                return
                
            cur_ts = new_state.attributes.get("last_called_timestamp")
            last_ts = old_state.attributes.get("last_called_timestamp")
            
            if cur_ts and cur_ts != last_ts:
                raw = str(new_state.attributes.get("last_called_summary", "")).lower().strip()
                if not raw:
                    return
                
                if not is_voice_question(raw) and has_shopping_intent(raw):
                    summary = new_state.attributes.get("last_called_summary", "").replace('"', '').replace("'", "")
                    now = time.time()
                    if summary.lower() == last_processed["summary"] and (now - last_processed["time"]) < 3.0:
                        return
                    last_processed["summary"] = summary.lower()
                    last_processed["time"] = now

                    _LOGGER.info("Intercepted Alexa shopping intent: %s", summary)
                    coordinator.last_spoken_text = summary
                    coordinator.last_action = "voice_command"
                    # Trigger sync
                    hass.async_create_task(
                        hass.services.async_call(DOMAIN, SERVICE_SYNC_TEXT, {ATTR_SPOKEN_TEXT: summary})
                    )

        listener = async_track_state_change_event(hass, media_players, alexa_state_changed_listener)
        hass.data[DOMAIN][entry.entry_id]["listeners"].append(listener)

    # 2. Todo Reconciler
    if todo_list:
        async def reconcile_amazon_todo():
            """Reconcile Bring! items with Amazon Todo."""
            if not coordinator.data:
                return
            bring_names = coordinator.data.get("items", []).copy()
            
            try:
                # Fetch Amazon items
                response = await hass.services.async_call(
                    "todo", "get_items", 
                    {"entity_id": todo_list, "status": "needs_action"},
                    blocking=True,
                    return_response=True
                )
                
                if response and todo_list in response:
                    amazon_items = response[todo_list].get("items", [])
                    
                    items_to_remove = []
                    items_to_add = bring_names.copy()
                    
                    for a_item in amazon_items:
                        s = a_item.get("summary", "").strip()
                        if s in items_to_add:
                            items_to_add.remove(s)
                        else:
                            items_to_remove.append(s)
                            
                    for item in items_to_remove:
                        await hass.services.async_call("todo", "remove_item", {"entity_id": todo_list, "item": item})
                        
                    for item in items_to_add:
                        await hass.services.async_call("todo", "add_item", {"entity_id": todo_list, "item": item})
                        
                    if items_to_remove or items_to_add:
                        _LOGGER.info("Reconciled Amazon list %s: Removed %s, Added %s", todo_list, len(items_to_remove), len(items_to_add))
            except Exception as e:
                _LOGGER.error("Error reconciling Amazon Todo list: %s", str(e))

        def on_coordinator_update():
            hass.async_create_task(reconcile_amazon_todo())

        remove_coord_listener = coordinator.async_add_listener(on_coordinator_update)
        hass.data[DOMAIN][entry.entry_id]["listeners"].append(remove_coord_listener)

    # Listen for options updates (device/list changes in UI)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        # Remove listeners
        for listener in data.get("listeners", []):
            listener()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SYNC_TEXT)
    return unload_ok
