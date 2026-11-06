"""A quiet overview updated by existing discovery events, without extra polling."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .button import DeviceInfo
from .const import DOMAIN, NAME
from .discovery import CONF_OVERVIEW_SENSOR


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.options.get(CONF_OVERVIEW_SENSOR, False):
        async_add_entities([TranslationOverview(hass.data[DOMAIN], entry)])


class TranslationOverview(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "missing_integrations"
    _attr_icon = "mdi:translate-off"
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime, entry):
        self.runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_missing_integrations"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            configuration_url="homeassistant://custom-integration-translator",
        )

    @property
    def available(self):
        return self.runtime.active and self.runtime.overview is not None

    @property
    def native_value(self):
        return self.runtime.overview["integrations"] if self.available else None

    @property
    def extra_state_attributes(self):
        return self.runtime.overview

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        @callback
        def updated():
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_overview", updated)
        )
