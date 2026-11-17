"""The translation services a translator entry can use, and how one is chosen.

Installed services are found when they are needed, not copied into the entry: a service that is
set up later (or removed again) shows up (or disappears) without touching the translator's
settings. The entry only remembers a choice where it matters, such as which of several accounts
of one service to use.
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .const import DEEPL, GOOGLE
from .provider import PROVIDER_TYPES, Provider, UnavailableProvider

CONF_PROVIDERS = "providers"
CONF_LEGACY_DEEPL = "deepl_entry"
CONF_DEFAULT_PROVIDER = "default_provider"
CONF_PROVIDER_FALLBACK = "provider_fallback"
# The form field in which an account of each service is chosen.
ACCOUNT_FIELDS = {DEEPL: "deepl_entry", GOOGLE: "google_entry"}
PROVIDER_URLS = {
    DEEPL: "https://github.com/seb5594/hass-deepl_translator-integration",
    GOOGLE: "https://github.com/seb5594/hass-google_translator-integration",
}


def configured_accounts(entry):
    """The account chosen for each service: {domain: config entry id}."""
    accounts = dict(entry.data.get(CONF_PROVIDERS) or {})
    # Entries created before Google was supported only knew a DeepL account.
    if CONF_LEGACY_DEEPL in entry.data:
        accounts.setdefault(DEEPL, entry.data[CONF_LEGACY_DEEPL])
    return accounts


def loaded_accounts(hass, domain):
    """The loaded config entries of a service: {entry id: title}."""
    return {
        account.entry_id: account.title
        for account in hass.config_entries.async_entries(domain)
        if account.state is ConfigEntryState.LOADED
    }


def available_accounts(hass):
    """The loaded accounts of every installed service: {domain: {entry id: title}}."""
    return {
        provider_type.domain: accounts
        for provider_type in PROVIDER_TYPES
        if (accounts := loaded_accounts(hass, provider_type.domain))
    }


class ProviderSet:
    """The services of one translator entry, with the preferred one first."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._cache = {}

    def _provider(self, provider_type, entry_id):
        key = (provider_type.domain, entry_id)
        if key not in self._cache:
            self._cache[key] = provider_type(self.hass, entry_id)
        return self._cache[key]

    def all(self):
        """Every usable service: the chosen accounts, plus services that are installed alone."""
        accounts = configured_accounts(self.entry)
        providers = []
        for provider_type in PROVIDER_TYPES:
            entry_id = accounts.get(provider_type.domain)
            if entry_id is None:
                loaded = loaded_accounts(self.hass, provider_type.domain)
                # With several accounts only the user can tell which one is meant.
                entry_id = next(iter(loaded)) if len(loaded) == 1 else None
            if entry_id is not None:
                providers.append(self._provider(provider_type, entry_id))
        preferred = self.entry.options.get(CONF_DEFAULT_PROVIDER)
        return sorted(providers, key=lambda provider: provider.key != preferred)

    @property
    def default(self):
        providers = self.all()
        return providers[0] if providers else UnavailableProvider(self.hass)

    def get(self, key):
        """The service with this key, or None."""
        return next((provider for provider in self.all() if provider.key == key), None)

    async def languages(self):
        """The target languages of every service that answers: {key: {HA language: code}}.

        Raises the last error when none does, so callers can tell "unavailable" from "empty".
        """
        result, error = {}, None
        for provider in self.all():
            try:
                result[provider.key] = await provider.languages()
            except HomeAssistantError as err:
                error = err
        if not result:
            raise error or HomeAssistantError("No translation service is available")
        return result

    async def translate(self, phrases, source, target, terms, preferred=None):
        """Translate with the preferred service; optionally let another one take over.

        Returns the translations and the service that produced them. The takeover only happens
        when the option is on, and never hides that it happened: the caller learns who translated.
        """
        providers = self.all()
        if not providers:
            return await UnavailableProvider(self.hass).translate(phrases, source, target, terms), None
        chosen = self.get(preferred) if preferred else None
        if preferred and chosen is None:
            raise HomeAssistantError("The selected translation service is not available")
        order = [chosen or providers[0]]
        if self.entry.options.get(CONF_PROVIDER_FALLBACK, False):
            order += [provider for provider in providers if provider is not order[0]]
        failures = []
        for provider in order:
            try:
                return await provider.translate(phrases, source, target, terms), provider
            except HomeAssistantError as err:
                failures.append(f"{provider.name}: {err}")
        raise HomeAssistantError(" · ".join(failures))
