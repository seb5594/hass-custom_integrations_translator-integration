"""Set up the provider, opt into a sidebar entry, or guide deactivation."""

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import DEEPL, DOMAIN, NAME


class TranslatorFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
