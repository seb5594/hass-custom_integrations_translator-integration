"""Set up the provider, opt into a sidebar entry, or guide deactivation."""

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .compat import vol
from .const import DOMAIN, NAME
from .provider import PROVIDER_TYPES
from .providers import (
    ACCOUNT_FIELDS,
    CONF_DEFAULT_PROVIDER,
    CONF_LEGACY_DEEPL,
    CONF_PROVIDER_FALLBACK,
    CONF_PROVIDERS,
    PROVIDER_URLS,
    available_accounts,
    configured_accounts,
)
from .discovery import (
    CONF_OVERVIEW_SENSOR,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    NOTICE_OPTIONS,
    TRIGGER_OPTIONS,
)


def provider_names():
    return {provider_type.domain: provider_type.name for provider_type in PROVIDER_TYPES}


def provider_fields(accounts, current, existing_default=None, fallback=None):
    """Form fields to choose an account per service, the preferred service and the takeover."""
    fields = {}
    for domain, titles in accounts.items():
        chosen = current.get(domain)
        fields[
            vol.Required(
                ACCOUNT_FIELDS[domain],
                default=chosen if chosen in titles else next(iter(titles)),
            )
        ] = vol.In(titles)
    if len(accounts) > 1:
        names = {domain: provider_names()[domain] for domain in accounts}
        first = existing_default if existing_default in names else next(iter(names))
        fields[vol.Required(CONF_DEFAULT_PROVIDER, default=first)] = vol.In(names)
        if fallback is not None:
            fields[vol.Required(CONF_PROVIDER_FALLBACK, default=fallback)] = bool
    return fields


def chosen_accounts(accounts, user_input):
    """The accounts picked in the form, or None if one of them is not valid."""
    chosen = {domain: user_input.get(ACCOUNT_FIELDS[domain]) for domain in accounts}
    if all(entry_id in accounts[domain] for domain, entry_id in chosen.items()):
        return chosen
    return None


class TranslatorFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_integration_discovery(self, discovery_info):
        """Offer setup when a running translation service finds our files."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": NAME}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        """Keep the discovery card until the user chooses to configure or ignore it."""
        errors = {}
        if user_input is not None:
            if available_accounts(self.hass):
                return await self.async_step_user()
            errors["base"] = "provider_required"
        return self.async_show_form(
            step_id="discovery_confirm", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        accounts = available_accounts(self.hass)
        if not accounts:
            return self.async_abort(
                reason="provider_required",
                description_placeholders={
                    "providers": " · ".join(
                        f"[{provider_type.name} Translator]({PROVIDER_URLS[provider_type.domain]})"
                        for provider_type in PROVIDER_TYPES
                    )
                },
            )
        if user_input is not None and (chosen := chosen_accounts(accounts, user_input)):
            options = {
                "notify_missing": False,
                "repair_missing": False,
                CONF_OVERVIEW_SENSOR: True,
            }
            if user_input.get(CONF_DEFAULT_PROVIDER) in chosen:
                options[CONF_DEFAULT_PROVIDER] = user_input[CONF_DEFAULT_PROVIDER]
            return self.async_create_entry(
                title=NAME, data={CONF_PROVIDERS: chosen}, options=options
            )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(provider_fields(accounts, {}))
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TranslatorOptions()


class TranslatorOptions(config_entries.OptionsFlow):
    @property
    def entry(self):
        return self.hass.config_entries.async_get_entry(self.handler)

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "preferences",
                "providers",
                "automation",
                "notifications",
                "deactivate",
            ],
        )

    async def async_step_preferences(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.entry.options, **user_input}
            )
        entry = self.entry
        try:
            languages = sorted(await self.hass.data[DOMAIN].supported_languages())
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

    async def async_step_providers(self, user_input=None):
        """Choose the account of each translation service and which one is preferred."""
        entry = self.entry
        accounts = available_accounts(self.hass)
        if not accounts:
            return self.async_abort(reason="provider_unavailable")
        if user_input is not None and (chosen := chosen_accounts(accounts, user_input)):
            data = {key: value for key, value in entry.data.items() if key != CONF_LEGACY_DEEPL}
            self.hass.config_entries.async_update_entry(
                entry, data={**data, CONF_PROVIDERS: chosen}
            )
            options = {**entry.options}
            if user_input.get(CONF_DEFAULT_PROVIDER) in chosen:
                options[CONF_DEFAULT_PROVIDER] = user_input[CONF_DEFAULT_PROVIDER]
            if CONF_PROVIDER_FALLBACK in user_input:
                options[CONF_PROVIDER_FALLBACK] = user_input[CONF_PROVIDER_FALLBACK]
            return self.async_create_entry(title="", data=options)
        fields = provider_fields(
            accounts,
            configured_accounts(entry),
            entry.options.get(CONF_DEFAULT_PROVIDER),
            entry.options.get(CONF_PROVIDER_FALLBACK, False),
        )
        return self.async_show_form(step_id="providers", data_schema=vol.Schema(fields))

    async def async_step_automation(self, user_input=None):
        return self._switches("automation", TRIGGER_OPTIONS, user_input)

    async def async_step_notifications(self, user_input=None):
        return self._switches("notifications", NOTICE_OPTIONS, user_input)

    def _switches(self, step, keys, user_input):
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.entry.options, **user_input}
            )
        options = self.entry.options
        fields = {
            vol.Required(
                key, default=options.get(key, key != CONF_OVERVIEW_SENSOR)
            ): bool
            for key in keys
        }
        if step == "automation":
            fields[
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                )
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=168,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="h",
                )
            )
        return self.async_show_form(step_id=step, data_schema=vol.Schema(fields))

    async def async_step_deactivate(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("undo"):
                try:
                    await self.hass.data[DOMAIN].restore_all()
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
            self.hass.data[DOMAIN].guided_disable = True
            self.hass.async_create_task(
                self.hass.config_entries.async_set_disabled_by(
                    self.entry.entry_id, config_entries.ConfigEntryDisabler.USER
                )
            )
            return self.async_abort(reason="deactivated")
        return self.async_show_form(
            step_id="deactivate",
            errors=errors,
            description_placeholders={"detail": ""},
            data_schema=vol.Schema({vol.Required("undo", default=False): bool}),
        )
