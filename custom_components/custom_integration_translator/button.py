"""Config entry shortcut to the translation workspace."""

from homeassistant.components.button import ButtonEntity

try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from . import open_workspace
from .const import DOMAIN, NAME


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OpenWorkspace(entry)])


class OpenWorkspace(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "open_workspace"
    _attr_icon = "mdi:translate"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_open"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            configuration_url="homeassistant://custom-integration-translator",
        )

    async def async_press(self):
        open_workspace(self.hass, self._context)
