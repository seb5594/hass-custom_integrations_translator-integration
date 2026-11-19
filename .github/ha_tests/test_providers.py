"""Several translation services: how they are found, chosen, mapped and combined."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

try:
    from pytest_homeassistant.common import MockConfigEntry
except ImportError:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.custom_integration_translator.const import DEEPL, DOMAIN, GOOGLE
from custom_components.custom_integration_translator.provider import (
    DeepLProvider,
    GoogleProvider,
)
from custom_components.custom_integration_translator.providers import (
    ProviderSet,
    configured_accounts,
)

GOOGLE_CODES = ["de", "en", "fr", "pt", "pt-PT", "zh-CN", "zh-TW", "iw", "no", "sr"]


def translator_entry(data=None, options=None):
    return SimpleNamespace(data=data or {}, options=options or {})


def add_account(hass, domain, title="Account", loaded=True):
    entry = MockConfigEntry(
        domain=domain,
        title=title,
        state=ConfigEntryState.LOADED if loaded else ConfigEntryState.NOT_LOADED,
    )
    entry.add_to_hass(hass)
    return entry


# --- language mapping -------------------------------------------------------------------------


async def test_google_languages_are_matched_to_the_codes_google_lists(hass):
    provider = GoogleProvider(hass, "account")
    provider.call = AsyncMock(
        return_value={"languages": [{"code": code} for code in GOOGLE_CODES]}
    )
    languages = await provider.languages()
    assert languages["de"] == "de"
    assert languages["zh-Hans"] == "zh-CN" and languages["zh-Hant"] == "zh-TW"
    assert languages["he"] == "iw" and languages["nb"] == "no"
    assert languages["pt"] == "pt-PT" and languages["pt-BR"] == "pt"
    assert languages["nn"] == "no" and languages["sr-Latn"] == "sr"
    assert languages["en-GB"] == "en"  # a region falls back to its language
    assert "xx" not in languages and "tlh" not in languages


async def test_google_codes_are_case_insensitive(hass):
    provider = GoogleProvider(hass, "account")
    provider.call = AsyncMock(return_value={"languages": [{"code": "ZH-cn"}, {"code": "DE"}]})
    assert (await provider.languages())["zh-Hans"] == "ZH-cn"
    assert (await provider.languages())["de"] == "DE"


async def test_google_portuguese_without_a_european_variant_uses_the_plain_code(hass):
    provider = GoogleProvider(hass, "account")
    provider.call = AsyncMock(return_value={"languages": [{"code": "pt"}]})
    assert await provider.languages() == {"pt": "pt", "pt-BR": "pt"}


async def test_deepl_languages_keep_their_established_mapping(hass):
    provider = DeepLProvider(hass, "account")
    provider.call = AsyncMock(
        return_value={"languages": [{"code": code} for code in ("DE", "EN-US", "PT-PT", "ZH-HANS")]}
    )
    languages = await provider.languages()
    assert languages == {"de": "DE", "en": "EN-US", "pt": "PT-PT", "zh-Hans": "ZH-HANS"}


@pytest.mark.parametrize(
    "source,expected", [("en", "en"), ("en-US", "en"), ("zh-Hans", "zh-CN"), ("pt-BR", "pt"), ("xx", "xx")]
)
def test_google_source_languages(hass, source, expected):
    languages = {"zh-Hans": "zh-CN", "pt-BR": "pt"}
    assert GoogleProvider(hass, "a").source_code(source, languages) == expected


def test_deepl_source_languages_stay_upper_case_without_region(hass):
    assert DeepLProvider(hass, "a").source_code("pt-BR", {}) == "PT"


# --- translating with Google ------------------------------------------------------------------


async def test_google_translation_protects_terms_and_names_itself_in_errors(hass):
    provider = GoogleProvider(hass, "account")
    sent = []

    async def call(service, fields):
        if service == "get_languages":
            return {"languages": [{"code": "de"}]}
        sent.append(fields)
        return {"translations": [{"text": text.replace("Open", "Öffne")} for text in fields["text"]]}

    provider.call = AsyncMock(side_effect=call)
    result = await provider.translate(["Open ACME {name}"], "en-US", "de", ["ACME"])
    assert result == ["Öffne ACME {name}"]
    assert sent[0]["target_language"] == "de" and sent[0]["source_language"] == "en"
    assert "ACME" not in sent[0]["text"][0] and "{name}" not in sent[0]["text"][0]

    with pytest.raises(HomeAssistantError, match="Google does not support"):
        await provider.translate(["Open"], "en", "fr", [])


async def test_a_lost_placeholder_is_reported_by_service_name(hass):
    provider = GoogleProvider(hass, "account")

    async def call(service, fields):
        if service == "get_languages":
            return {"languages": [{"code": "de"}]}
        return {"translations": [{"text": "Verloren"}]}

    provider.call = AsyncMock(side_effect=call)
    with pytest.raises(HomeAssistantError, match="Google changed a protected"):
        await provider.translate(["Open {name}"], "en", "de", [])


async def test_a_missing_service_is_reported_by_name(hass):
    with pytest.raises(HomeAssistantError, match="Google is unavailable"):
        await GoogleProvider(hass, "account").call("get_languages", {})


async def test_usage_reads_the_service_of_the_provider(hass):
    seen = []

    async def usage(call):
        seen.append(call.data)
        return {"available": True, "estimated": True, "character_count": 5}

    hass.services.async_register(GOOGLE, "get_usage", usage, supports_response=SupportsResponse.OPTIONAL)
    assert (await GoogleProvider(hass, "account").usage())["estimated"] is True
    assert seen == [{"refresh": True, "config_entry_id": "account"}]
    assert await DeepLProvider(hass, "account").usage() == {"available": False, "reason": "update_required"}


# --- finding and choosing services ------------------------------------------------------------


def test_entries_created_before_google_only_knew_a_deepl_account():
    assert configured_accounts(translator_entry({"deepl_entry": "old"})) == {DEEPL: "old"}
    assert configured_accounts(translator_entry({"providers": {GOOGLE: "g"}, "deepl_entry": "old"})) == {
        GOOGLE: "g",
        DEEPL: "old",
    }


async def test_a_stored_account_is_used_without_checking_that_it_is_loaded(hass):
    providers = ProviderSet(hass, translator_entry({"deepl_entry": "account"}))
    assert [(item.key, item.entry_id) for item in providers.all()] == [(DEEPL, "account")]


async def test_an_installed_service_shows_up_without_touching_the_settings(hass):
    providers = ProviderSet(hass, translator_entry({"deepl_entry": "account"}))
    assert [item.key for item in providers.all()] == [DEEPL]
    google = add_account(hass, GOOGLE)
    assert [(item.key, item.entry_id) for item in providers.all()] == [
        (DEEPL, "account"),
        (GOOGLE, google.entry_id),
    ]


async def test_with_several_accounts_of_a_service_only_a_choice_picks_one(hass):
    add_account(hass, GOOGLE, "one")
    add_account(hass, GOOGLE, "two")
    assert ProviderSet(hass, translator_entry()).all() == []
    chosen = add_account(hass, GOOGLE, "three")
    providers = ProviderSet(hass, translator_entry({"providers": {GOOGLE: chosen.entry_id}}))
    assert [item.entry_id for item in providers.all()] == [chosen.entry_id]


async def test_accounts_that_are_not_loaded_are_not_picked_up(hass):
    add_account(hass, GOOGLE, loaded=False)
    assert ProviderSet(hass, translator_entry()).all() == []


async def test_the_preferred_service_comes_first_and_objects_are_reused(hass):
    providers = ProviderSet(
        hass,
        translator_entry({"providers": {DEEPL: "d", GOOGLE: "g"}}, {"default_provider": GOOGLE}),
    )
    assert [item.key for item in providers.all()] == [GOOGLE, DEEPL]
    assert providers.default is providers.get(GOOGLE) is providers.all()[0]
    assert providers.get("unknown") is None


async def test_without_any_service_callers_get_a_clear_error(hass):
    providers = ProviderSet(hass, translator_entry())
    with pytest.raises(HomeAssistantError, match="No translation service"):
        await providers.default.languages()
    with pytest.raises(HomeAssistantError, match="No translation service"):
        await providers.languages()
    with pytest.raises(HomeAssistantError, match="No translation service"):
        await providers.translate(["Open"], "en", "de", [])


async def test_languages_come_from_every_service_that_answers(hass):
    providers = ProviderSet(hass, translator_entry({"providers": {DEEPL: "d", GOOGLE: "g"}}))
    deepl, google = providers.get(DEEPL), providers.get(GOOGLE)
    deepl.languages = AsyncMock(side_effect=HomeAssistantError("offline"))
    google.languages = AsyncMock(return_value={"de": "de"})
    assert await providers.languages() == {GOOGLE: {"de": "de"}}
    google.languages = AsyncMock(side_effect=HomeAssistantError("also offline"))
    with pytest.raises(HomeAssistantError, match="also offline"):
        await providers.languages()


# --- choosing and falling back when translating ----------------------------------------------


def two_services(hass, options=None):
    providers = ProviderSet(
        hass, translator_entry({"providers": {DEEPL: "d", GOOGLE: "g"}}, options)
    )
    deepl, google = providers.get(DEEPL), providers.get(GOOGLE)
    deepl.translate = AsyncMock(return_value=["von DeepL"])
    google.translate = AsyncMock(return_value=["von Google"])
    return providers, deepl, google


async def test_the_preferred_service_translates_by_default(hass):
    providers, deepl, google = two_services(hass)
    values, used = await providers.translate(["x"], "en", "de", [])
    assert (values, used) == (["von DeepL"], deepl)
    google.translate.assert_not_called()


async def test_a_service_can_be_chosen_for_one_translation(hass):
    providers, deepl, google = two_services(hass)
    values, used = await providers.translate(["x"], "en", "de", [], preferred=GOOGLE)
    assert (values, used) == (["von Google"], google)
    deepl.translate.assert_not_called()


async def test_a_chosen_service_that_is_gone_is_an_error_not_a_silent_switch(hass):
    providers, _, google = two_services(hass, {"provider_fallback": True})
    with pytest.raises(HomeAssistantError, match="not available"):
        await providers.translate(["x"], "en", "de", [], preferred="unknown")
    google.translate.assert_not_called()


async def test_a_failure_is_not_hidden_by_another_service_unless_asked_to(hass):
    providers, deepl, google = two_services(hass)
    deepl.translate = AsyncMock(side_effect=HomeAssistantError("quota used up"))
    with pytest.raises(HomeAssistantError, match="DeepL: quota used up"):
        await providers.translate(["x"], "en", "de", [])
    google.translate.assert_not_called()


async def test_another_service_takes_over_when_allowed_and_says_so(hass):
    providers, deepl, google = two_services(hass, {"provider_fallback": True})
    deepl.translate = AsyncMock(side_effect=HomeAssistantError("quota used up"))
    values, used = await providers.translate(["x"], "en", "de", [])
    assert (values, used) == (["von Google"], google)


async def test_when_every_service_fails_every_reason_is_reported(hass):
    providers, deepl, google = two_services(hass, {"provider_fallback": True})
    deepl.translate = AsyncMock(side_effect=HomeAssistantError("quota used up"))
    google.translate = AsyncMock(side_effect=HomeAssistantError("limiting requests"))
    with pytest.raises(HomeAssistantError, match="DeepL: quota used up · Google: limiting requests"):
        await providers.translate(["x"], "en", "de", [])


async def test_the_takeover_never_goes_through_the_chosen_service_twice(hass):
    providers, deepl, google = two_services(hass, {"provider_fallback": True})
    google.translate = AsyncMock(side_effect=HomeAssistantError("nope"))
    values, used = await providers.translate(["x"], "en", "de", [], preferred=GOOGLE)
    assert used is deepl and google.translate.await_count == 1
