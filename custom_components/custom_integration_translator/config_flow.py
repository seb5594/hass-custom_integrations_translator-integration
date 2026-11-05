"""Set up the provider, opt into a sidebar entry, or guide deactivation."""

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import DEEPL, DOMAIN, NAME
from .discovery import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL


class TranslatorFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_integration_discovery(self, discovery_info):
        """Offer setup when the running DeepL integration finds our files."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": NAME}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        """Keep the discovery card until the user chooses to configure or ignore it."""
        errors = {}
        if user_input is not None:
            if any(
                entry.state is config_entries.ConfigEntryState.LOADED
                for entry in self.hass.config_entries.async_entries(DEEPL)
            ):
                return await self.async_step_user()
            errors["base"] = "deepl_required"
        return self.async_show_form(
            step_id="discovery_confirm", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        entries = {
            entry.entry_id: entry.title
            for entry in self.hass.config_entries.async_entries(DEEPL)
            if entry.state is config_entries.ConfigEntryState.LOADED
        }
        if not entries:
            return self.async_abort(reason="deepl_required")
        if user_input is not None and user_input.get("deepl_entry") in entries:
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("deepl_entry", default=next(iter(entries))): vol.In(
                        entries
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TranslatorOptions()


class TranslatorOptions(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init", menu_options=["preferences", "deactivate"]
        )

    async def async_step_preferences(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        entry = self.config_entry
        try:
            languages = list(await entry.runtime_data.provider.languages())
        except HomeAssistantError:
            return self.async_abort(reason="provider_unavailable")
        options = ["system", *languages]
        current = entry.options.get("language") or "system"
        return self.async_show_form(
            step_id="preferences",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "language", default=current if current in options else "system"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    ),
                    vol.Required(
                        "sidebar", default=entry.options.get("sidebar", False)
                    ): bool,
                    vol.Optional(
                        "protected_words",
                        default=entry.options.get("protected_words", ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=168,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                }
            ),
        )

    async def async_step_deactivate(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("undo"):
                try:
                    await self.config_entry.runtime_data.restore_all()
                except (ValueError, OSError) as err:
                    return self.async_show_form(
                        step_id="deactivate",
                        errors={"base": "restore_failed"},
                        description_placeholders={"detail": str(err)},
                        data_schema=vol.Schema(
                            {vol.Required("undo", default=False): bool}
                        ),
                    )
            # Schedule after this flow finishes; native unload preserves the files.
            self.config_entry.runtime_data.guided_disable = True
            self.hass.async_create_task(
                self.hass.config_entries.async_set_disabled_by(
                    self.config_entry.entry_id, config_entries.ConfigEntryDisabler.USER
                )
            )
            return self.async_abort(reason="deactivated")
        return self.async_show_form(
            step_id="deactivate",
            errors=errors,
            description_placeholders={"detail": ""},
            data_schema=vol.Schema({vol.Required("undo", default=False): bool}),
        )
