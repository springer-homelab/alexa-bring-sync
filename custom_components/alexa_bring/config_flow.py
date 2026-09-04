"""Config flow for Alexa-Bring! Sync integration."""
import logging
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import DOMAIN, CONF_LIST_NAME, CONF_MEDIA_PLAYERS, CONF_TODO_LIST
from .bring_api import BringAPI

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_LIST_NAME, default="Einkaufsliste"): str,
    }
)

def get_devices_schema(options: dict = None) -> vol.Schema:
    """Return the schema for device selection."""
    if options is None:
        options = {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_MEDIA_PLAYERS,
                default=options.get(CONF_MEDIA_PLAYERS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)
            ),
            vol.Optional(
                CONF_TODO_LIST,
                default=options.get(CONF_TODO_LIST, "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="todo")
            ),
        }
    )

async def validate_input(hass: HomeAssistant, data: dict) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    cache_dir = hass.config.path(".storage")
    
    api = BringAPI(
        session=session,
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        list_name=data.get(CONF_LIST_NAME, "Einkaufsliste"),
        cache_dir=cache_dir
    )
    
    success = await api.authenticate()
    if not success:
        raise InvalidAuth
        
    list_uuid = await api.get_list_uuid()
    if not list_uuid:
        raise CannotConnect

    return {"title": data.get(CONF_LIST_NAME, "Bring! Sync")}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alexa-Bring! Sync."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self.user_data = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                self.user_data.update(user_input)
                self.title = info["title"]
                return await self.async_step_devices()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_devices(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the device selection step."""
        if user_input is not None:
            options = {
                CONF_MEDIA_PLAYERS: user_input.get(CONF_MEDIA_PLAYERS, []),
                CONF_TODO_LIST: user_input.get(CONF_TODO_LIST, "")
            }
            return self.async_create_entry(title=self.title, data=self.user_data, options=options)

        return self.async_show_form(
            step_id="devices", data_schema=get_devices_schema()
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=get_devices_schema(self.config_entry.options),
        )

class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
