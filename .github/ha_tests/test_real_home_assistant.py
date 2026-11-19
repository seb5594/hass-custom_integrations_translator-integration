"""Exercise setup, discovery, DeepL's service contract and deactivation in a real core."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

try:
    from pytest_homeassistant.common import MockConfigEntry
except ImportError:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.repairs import repairs_flow_manager

from custom_components.custom_integration_translator.api import dispatch
from custom_components.custom_integration_translator.const import DEEPL, DOMAIN, PANEL
from custom_components.custom_integration_translator.runtime import Runtime


@pytest.fixture
async def frontend_ready(hass, tmp_path, enable_custom_integrations):
    hass.config.config_dir = str(tmp_path)
    hass.config.language = "de"
    # These tests cover frontend registration; onboarding and socket binding are
    # unrelated. Browser tests separately exercise the actual HTTP server.
    hass.config.components.add("onboarding")
    # The shared test plugin counts the manifest dependencies as loaded; this fixture sets up the
    # real HTTP server (only its socket stays unbound), which the frontend needs.
    hass.config.components.difference_update({"http", "frontend", "panel_custom"})
    with patch(
        "homeassistant.components.http.HomeAssistantHTTP.start", new=AsyncMock()
    ):
        assert await async_setup_component(hass, "frontend", {})
        assert await async_setup_component(hass, "persistent_notification", {})
        yield tmp_path


async def test_requires_a_translation_service(hass, frontend_ready):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["reason"] == "provider_required"
    assert result["description_placeholders"] == {
        "providers": "[DeepL Translator](https://github.com/seb5594/hass-deepl_translator-integration)"
        " · [Google Translator](https://github.com/seb5594/hass-google_translator-integration)"
    }


async def test_guided_translation_and_recovery(hass, frontend_ready):
    folder = frontend_ready / "custom_components/example"
    translations = folder / "translations"
    translations.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"name":"Example"}')
    (translations / "en.json").write_text('{"one":"Open ACME {name}","two":"Close"}')
    (translations / "de.json").write_bytes(b'{"two":"Zu"}')
    account = MockConfigEntry(
        domain=DEEPL, title="Test account", state=ConfigEntryState.LOADED
    )
    account.add_to_hass(hass)

    async def languages(call):
        assert call.data["config_entry_id"] == account.entry_id
        return {"languages": [{"code": "DE"}, {"code": "PT-BR"}]}

    async def translate(call):
        assert call.data["target_language"] == "DE"
        assert call.data["source_language"] == "EN"
        assert call.data["config_entry_id"] == account.entry_id
        assert "ACME" not in call.data["text"][0]
        return {
            "translations": [
                {"text": value.replace("Open", "Öffne")} for value in call.data["text"]
            ]
        }

    for service, handler in (
        ("get_languages", languages),
        ("translate_text", translate),
    ):
        hass.services.async_register(
            DEEPL, service, handler, supports_response=SupportsResponse.OPTIONAL
        )
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"deepl_entry": account.entry_id}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    runtime = hass.data[DOMAIN]
    assert entry.options["overview_sensor"]
    assert not entry.options["notify_missing"]
    assert not entry.options["repair_missing"]
    await runtime.refresh()
    assert not runtime.alerts and not runtime.issues
    assert runtime.overview["integrations"] == 1
    sensor = hass.states.get(hass.states.async_entity_ids("sensor")[0])
    assert sensor.state == "1"
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "notify_missing": True, "repair_missing": True}
    )
    await hass.async_block_till_done()
    runtime = hass.data[DOMAIN]
    assert hass.data[frontend.DATA_PANELS][PANEL].sidebar_title is None
    assert hass.states.async_entity_ids("button")
    assert hass.services.has_service(DOMAIN, "open_workspace")
    assert (await dispatch(runtime, {"action": "settings"}))["languages"] == [
        "de",
        "pt-BR",
    ]
    new_folder = frontend_ready / "custom_components" / "new_light"
    (new_folder / "translations").mkdir(parents=True)
    (new_folder / "manifest.json").write_text('{"name": "New Light"}')
    (new_folder / "translations" / "en.json").write_text('{"button":"Turn on"}')
    await runtime.refresh()
    assert "new_light_de" in runtime.alerts
    assert not (new_folder / "translations" / "de.json").exists()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "example_de")
    item = await dispatch(
        runtime, {"action": "detail", "domain": "example", "language": "de"}
    )
    with pytest.raises(HomeAssistantError):
        await runtime.provider.translate(["Open"], "en", "fr", [])
    await dispatch(
        runtime,
        {
            "action": "translate",
            "domain": "example",
            "language": "de",
            "paths": [["one"]],
            "terms": ["ACME"],
            "revision": item["revision"],
        },
    )
    assert "Öffne ACME {name}" in (translations / "de.json").read_text()
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "example_de")
    await hass.config_entries.async_set_disabled_by(
        entry.entry_id, ConfigEntryDisabler.USER
    )
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert ir.async_get(hass).async_get_issue(DOMAIN, "retained")
    manager = repairs_flow_manager(hass)
    repair = await manager.async_init(
        DOMAIN, context={"issue_id": "retained"}, data={"issue_id": "retained"}
    )
    assert repair["step_id"] == "review"
    assert (await manager.async_configure(repair["flow_id"], {"undo": True}))[
        "type"
    ] == "create_entry"
    assert (translations / "de.json").read_bytes() == b'{"two":"Zu"}'


async def test_preferences_and_guided_disable(hass, frontend_ready):
    async def languages(call):
        return {"languages": [{"code": "DE"}]}

    hass.services.async_register(
        DEEPL, "get_languages", languages, supports_response=SupportsResponse.ONLY
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"deepl_entry": "account"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    options = hass.config_entries.options
    flow = await options.async_init(entry.entry_id)
    form = await options.async_configure(
        flow["flow_id"], {"next_step_id": "preferences"}
    )
    assert form["type"] == "form"
    saved = await options.async_configure(
        flow["flow_id"],
        {
            "language": "system",
            "sidebar": True,
            "protected_words": "ACME",
        },
    )
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.data[DOMAIN].language == "de"
    assert hass.data[frontend.DATA_PANELS][PANEL].sidebar_title
    flow = await options.async_init(entry.entry_id)
    form = await options.async_configure(
        flow["flow_id"], {"next_step_id": "deactivate"}
    )
    assert form["type"] == "form"
    result = await options.async_configure(flow["flow_id"], {})
    assert result["reason"] == "deactivated"
    await hass.async_block_till_done()
    assert entry.disabled_by is ConfigEntryDisabler.USER


@pytest.mark.parametrize(
    "notify,repair", [(False, False), (False, True), (True, False), (True, True)]
)
async def test_notice_switches(hass, frontend_ready, notify, repair):
    from unittest.mock import AsyncMock, Mock

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deepl_entry": "account"},
        options={"notify_missing": notify, "repair_missing": repair},
    )
    runtime = Runtime(hass, entry)
    runtime.provider.languages = AsyncMock(return_value={"de": "DE"})
    runtime.catalog.scan = Mock(
        return_value=[
            {"domain": "new", "name": "New", "missing": 1, "exists": False},
            {"domain": "partial", "name": "Partial", "missing": 1, "exists": True},
        ]
    )
    await runtime.refresh()
    assert runtime.alerts == ({"new_de"} if notify else set())
    assert runtime.issues == ({"partial_de"} if repair else set())
    assert bool(ir.async_get(hass).async_get_issue(DOMAIN, "partial_de")) == repair
    if not notify and not repair:
        runtime.provider.languages.assert_not_called()
        runtime.catalog.scan.assert_not_called()
    runtime.cleanup()
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "partial_de")


async def test_manual_translation_when_automatic_checks_are_disabled(
    hass, frontend_ready
):
    from unittest.mock import AsyncMock

    folder = frontend_ready / "custom_components/example/translations"
    folder.mkdir(parents=True)
    (folder.parent / "manifest.json").write_text('{"name":"Example"}')
    (folder / "en.json").write_text('{"one":"Open"}')
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deepl_entry": "account"},
        options={"automatic_checks": False},
    )
    runtime = Runtime(hass, entry)
    runtime.provider.languages = AsyncMock()
    runtime.provider.translate = AsyncMock(return_value=["Öffnen"])
    items = await dispatch(runtime, {"action": "list", "language": "de"})
    assert items[0]["domain"] == "example"
    detail = await dispatch(
        runtime, {"action": "detail", "domain": "example", "language": "de"}
    )
    await dispatch(
        runtime,
        {
            "action": "translate",
            "domain": "example",
            "language": "de",
            "revision": detail["revision"],
            "paths": [["one"]],
        },
    )
    assert "Öffnen" in (folder / "de.json").read_text()
    runtime.provider.languages.assert_not_called()


async def test_settings_pages_preserve_each_other_and_work_offline(
    hass, frontend_ready
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deepl_entry": "account"},
        options={
            "automatic_checks": False,
            "language": "de",
            "protected_words": "ACME",
            "scan_interval_hours": 48,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    manager = hass.config_entries.options
    for step, changes in [
        ("notifications", {"notify_missing": False, "repair_missing": False}),
        ("automation", {"automatic_checks": False, "watch_hacs": False}),
    ]:
        flow = await manager.async_init(entry.entry_id)
        form = await manager.async_configure(flow["flow_id"], {"next_step_id": step})
        assert form["type"] == "form"
        result = await manager.async_configure(flow["flow_id"], changes)
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
    assert entry.options["language"] == "de"
    assert entry.options["protected_words"] == "ACME"
    assert entry.options["scan_interval_hours"] == 48
    assert not entry.options["notify_missing"]
    assert not entry.options["repair_missing"]
    assert not entry.options["watch_hacs"]
    assert not entry.options["automatic_checks"]


@pytest.mark.parametrize("edited_language", ["de", "fr"])
async def test_mutations_refresh_only_the_edited_integration(
    hass, frontend_ready, edited_language
):
    import json

    for domain in ("edited", "unrelated", "partial"):
        folder = frontend_ready / "custom_components" / domain
        (folder / "translations").mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({"name": domain}))
        (folder / "translations/en.json").write_text('{"one":"Open","two":"Close"}')
    (frontend_ready / "custom_components/partial/translations/de.json").write_text(
        '{"one":"Auf"}'
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"deepl_entry": "account"})
    runtime = Runtime(hass, entry)
    runtime.provider.languages = AsyncMock(return_value={"de": "DE", "fr": "FR"})
    runtime.provider.translate = AsyncMock(return_value=["Translated"])
    await runtime.refresh()
    assert runtime.alerts == {"edited_de", "unrelated_de"}
    assert runtime.issues == {"partial_de"}
    unrelated_issue = ir.async_get(hass).async_get_issue(DOMAIN, "partial_de")
    detail = await dispatch(
        runtime, {"action": "detail", "domain": "edited", "language": edited_language}
    )
    with (
        patch.object(
            runtime.catalog, "scan", side_effect=AssertionError("Unexpected full scan")
        ),
        patch.object(
            runtime.catalog, "summary", wraps=runtime.catalog.summary
        ) as summary,
    ):
        await dispatch(
            runtime,
            {
                "action": "translate",
                "domain": "edited",
                "language": edited_language,
                "revision": detail["revision"],
                "paths": [["one"]],
            },
        )
        summary.assert_called_once_with("edited", "de")
        assert "unrelated_de" in runtime.alerts
        assert (
            ir.async_get(hass).async_get_issue(DOMAIN, "partial_de") is unrelated_issue
        )
        if edited_language == "de":
            assert "edited_de" not in runtime.alerts
            issue = ir.async_get(hass).async_get_issue(DOMAIN, "edited_de")
            assert issue.translation_placeholders["count"] == "1"
        else:
            assert "edited_de" in runtime.alerts
            assert runtime.issues == {"partial_de"}
        detail = await dispatch(
            runtime,
            {"action": "detail", "domain": "edited", "language": edited_language},
        )
        await dispatch(
            runtime,
            {
                "action": "restore",
                "domain": "edited",
                "language": edited_language,
                "revision": detail["revision"],
            },
        )
        assert summary.call_count == 2
    assert runtime.alerts == {"edited_de", "unrelated_de"}
    assert runtime.issues == {"partial_de"}
    assert not (
        frontend_ready / f"custom_components/edited/translations/{edited_language}.json"
    ).exists()
    runtime.cleanup()


async def test_targeted_refresh_reconciles_all_notices_after_language_change(
    hass, frontend_ready
):
    for domain in ("one", "two"):
        folder = frontend_ready / "custom_components" / domain
        (folder / "translations").mkdir(parents=True)
        (folder / "manifest.json").write_text('{"name":"Example"}')
        (folder / "translations/en.json").write_text('{"one":"Open"}')
    runtime = Runtime(
        hass, MockConfigEntry(domain=DOMAIN, data={"deepl_entry": "account"})
    )
    runtime.provider.languages = AsyncMock(return_value={"de": "DE", "fr": "FR"})
    await runtime.refresh()
    hass.config.language = "fr"
    with patch.object(runtime.catalog, "scan", wraps=runtime.catalog.scan) as scan:
        await runtime.refresh(domain="one")
        scan.assert_called_once_with("fr")
    assert runtime.alerts == {"one_fr", "two_fr"}
    runtime.provider.languages.return_value = {"de": "DE"}
    await runtime.refresh(domain="one")
    assert not runtime.alerts
    assert not runtime.issues
    runtime.cleanup()


async def test_quiet_overview_updates_without_notifications_or_extra_polling(
    hass, frontend_ready
):
    from unittest.mock import Mock

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deepl_entry": "account"},
        options={
            "overview_sensor": True,
            "notify_missing": False,
            "repair_missing": False,
        },
    )
    entry.add_to_hass(hass)

    async def languages(call):
        return {"languages": [{"code": "DE"}]}

    hass.services.async_register(
        DEEPL, "get_languages", languages, supports_response=SupportsResponse.ONLY
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = hass.data[DOMAIN]
    runtime.catalog.scan = Mock(
        return_value=[
            {"domain": "new", "missing": 3, "count": 3, "exists": False},
            {"domain": "partial", "missing": 2, "count": 4, "exists": True},
        ]
    )
    with patch(
        "custom_components.custom_integration_translator.runtime.persistent_notification.async_create"
    ) as notify:
        await runtime.refresh()
        assert not runtime.alerts and not runtime.issues
        notify.assert_not_called()
    sensor_id = hass.states.async_entity_ids("sensor")[0]
    assert hass.states.get(sensor_id).state == "2"
    assert hass.states.get(sensor_id).attributes["missing_phrases"] == 5
    runtime.catalog.summary = Mock(
        return_value={"domain": "new", "missing": 0, "count": 3, "exists": True}
    )
    await runtime.refresh(domain="new")
    assert hass.states.get(sensor_id).state == "1"
    assert hass.states.get(sensor_id).attributes["missing_phrases"] == 2
    runtime.provider.languages = AsyncMock(side_effect=HomeAssistantError("offline"))
    await runtime.refresh()
    assert hass.states.get(sensor_id).state == "unavailable"
    await hass.config_entries.async_unload(entry.entry_id)


# --- DeepL and Google side by side -------------------------------------------------------------

GOOGLE = "google_translator"


def register_services(hass, domain, codes, translate=None, usage=None):
    """Answer like a translation service integration of Home Assistant."""
    calls = []

    async def languages(call):
        return {"languages": [{"code": code} for code in codes]}

    async def translate_text(call):
        calls.append(dict(call.data))
        if translate is not None:
            return translate(call)
        return {"translations": [{"text": f"{domain}: {text}"} for text in call.data["text"]]}

    hass.services.async_register(domain, "get_languages", languages, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(domain, "translate_text", translate_text, supports_response=SupportsResponse.OPTIONAL)
    if usage is not None:

        async def get_usage(call):
            return usage

        hass.services.async_register(domain, "get_usage", get_usage, supports_response=SupportsResponse.ONLY)
    return calls


def add_loaded_account(hass, domain, title):
    account = MockConfigEntry(domain=domain, title=title, state=ConfigEntryState.LOADED)
    account.add_to_hass(hass)
    return account


@pytest.fixture
def example_integration(frontend_ready):
    folder = frontend_ready / "custom_components/example"
    (folder / "translations").mkdir(parents=True)
    (folder / "manifest.json").write_text('{"name":"Example"}')
    (folder / "translations" / "en.json").write_text('{"one":"Open"}')
    return folder


async def test_setup_offers_every_installed_service_and_stores_the_choice(hass, frontend_ready):
    deepl = add_loaded_account(hass, DEEPL, "DeepL (Free)")
    google = add_loaded_account(hass, GOOGLE, "Google Translate")
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == "form"
    assert set(flow["data_schema"].schema) >= {"deepl_entry", "google_entry", "default_provider"}
    with patch(
        "custom_components.custom_integration_translator.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {"deepl_entry": deepl.entry_id, "google_entry": google.entry_id, "default_provider": GOOGLE},
        )
    assert result["type"] == "create_entry"
    assert result["data"] == {"providers": {DEEPL: deepl.entry_id, GOOGLE: google.entry_id}}
    assert result["options"]["default_provider"] == GOOGLE


async def test_google_alone_is_enough_to_set_up(hass, frontend_ready):
    google = add_loaded_account(hass, GOOGLE, "Google Translate")
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert set(flow["data_schema"].schema) == {"google_entry"}
    with patch(
        "custom_components.custom_integration_translator.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"google_entry": google.entry_id})
    assert result["data"] == {"providers": {GOOGLE: google.entry_id}}
    assert "default_provider" not in result["options"]


async def test_the_workspace_lists_services_with_their_own_languages(hass, example_integration):
    register_services(hass, DEEPL, ["DE", "FR"])
    register_services(hass, GOOGLE, ["de", "pt", "zh-CN"])
    deepl = add_loaded_account(hass, DEEPL, "DeepL")
    google = add_loaded_account(hass, GOOGLE, "Google")
    runtime = Runtime(
        hass, MockConfigEntry(domain=DOMAIN, data={"providers": {DEEPL: deepl.entry_id, GOOGLE: google.entry_id}})
    )
    settings = await dispatch(runtime, {"action": "settings"})
    assert [(item["key"], item["name"]) for item in settings["providers"]] == [(DEEPL, "DeepL"), (GOOGLE, "Google")]
    assert settings["provider"] == DEEPL and settings["fallback"] is False
    assert settings["languages"] == ["de", "fr"]  # only the preferred service unless another may take over
    assert {item["key"]: item["languages"] for item in settings["providers"]}[GOOGLE] == ["de", "pt", "pt-BR", "zh-Hans"]
    accounts = {"providers": {DEEPL: deepl.entry_id, GOOGLE: google.entry_id}}
    takeover = Runtime(hass, MockConfigEntry(domain=DOMAIN, data=accounts, options={"provider_fallback": True}))
    assert (await dispatch(takeover, {"action": "settings"}))["languages"] == ["de", "fr", "pt", "pt-BR", "zh-Hans"]


async def test_a_service_can_be_chosen_per_translation(hass, example_integration):
    deepl_calls = register_services(hass, DEEPL, ["DE"])
    google_calls = register_services(hass, GOOGLE, ["de"])
    deepl = add_loaded_account(hass, DEEPL, "DeepL")
    google = add_loaded_account(hass, GOOGLE, "Google")
    runtime = Runtime(
        hass, MockConfigEntry(domain=DOMAIN, data={"providers": {DEEPL: deepl.entry_id, GOOGLE: google.entry_id}}, options={"automatic_checks": False})
    )
    detail = await dispatch(runtime, {"action": "detail", "domain": "example", "language": "de"})
    request = {"action": "translate", "domain": "example", "language": "de", "revision": detail["revision"], "paths": [["one"]]}
    result = await dispatch(runtime, {**request, "provider": GOOGLE})
    assert result == {"provider": GOOGLE, "provider_name": "Google"}
    assert google_calls[0]["config_entry_id"] == google.entry_id and not deepl_calls
    assert "google_translator: Open" in (example_integration / "translations/de.json").read_text()
    detail = await dispatch(runtime, {"action": "detail", "domain": "example", "language": "de"})
    result = await dispatch(runtime, {**request, "revision": detail["revision"]})
    assert result["provider"] == DEEPL and deepl_calls[0]["config_entry_id"] == deepl.entry_id
    assert deepl_calls[0]["target_language"] == "DE" and google_calls[0]["target_language"] == "de"


async def test_the_takeover_names_the_service_that_translated(hass, example_integration):
    def refuse(call):
        raise HomeAssistantError("quota used up")

    register_services(hass, DEEPL, ["DE"], translate=refuse)
    register_services(hass, GOOGLE, ["de"])
    runtime = Runtime(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            data={"providers": {DEEPL: "d", GOOGLE: "g"}},
            options={"automatic_checks": False, "provider_fallback": True},
        ),
    )
    detail = await dispatch(runtime, {"action": "detail", "domain": "example", "language": "de"})
    result = await dispatch(
        runtime,
        {"action": "translate", "domain": "example", "language": "de", "revision": detail["revision"], "paths": [["one"]]},
    )
    assert result == {"provider": GOOGLE, "provider_name": "Google"}


async def test_usage_is_asked_from_the_chosen_service_and_labelled(hass, frontend_ready):
    register_services(hass, DEEPL, ["DE"], usage={"available": True, "character_count": 1, "character_limit": 10, "characters_remaining": 9, "unlimited": False})
    register_services(hass, GOOGLE, ["de"], usage={"available": True, "estimated": True, "character_count": 5, "character_limit": None, "characters_remaining": None, "unlimited": True})
    runtime = Runtime(hass, MockConfigEntry(domain=DOMAIN, data={"providers": {DEEPL: "d", GOOGLE: "g"}}))
    usage = await dispatch(runtime, {"action": "usage"})
    assert (usage["provider"], usage["provider_name"], usage["character_limit"]) == (DEEPL, "DeepL", 10)
    usage = await dispatch(runtime, {"action": "usage", "provider": GOOGLE})
    assert (usage["provider_name"], usage["estimated"], usage["unlimited"]) == ("Google", True, True)


async def test_discovery_checks_use_every_service_language(hass, frontend_ready):
    """A language only the second service offers is still worth a suggestion."""
    from unittest.mock import Mock

    register_services(hass, DEEPL, ["FR"])
    register_services(hass, GOOGLE, ["de"])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"providers": {DEEPL: "d", GOOGLE: "g"}},
        options={"notify_missing": True, "repair_missing": False},
    )
    runtime = Runtime(hass, entry)
    runtime.catalog.scan = Mock(return_value=[{"domain": "new", "name": "New", "missing": 1, "exists": False}])
    await runtime.refresh()
    assert runtime.alerts == {"new_de"}


async def test_options_choose_accounts_default_service_and_takeover(hass, frontend_ready):
    deepl = add_loaded_account(hass, DEEPL, "DeepL")
    google = add_loaded_account(hass, GOOGLE, "Google")
    register_services(hass, DEEPL, ["DE"])
    entry = MockConfigEntry(domain=DOMAIN, data={"deepl_entry": deepl.entry_id})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    options = hass.config_entries.options
    flow = await options.async_init(entry.entry_id)
    assert "providers" in flow["menu_options"]
    form = await options.async_configure(flow["flow_id"], {"next_step_id": "providers"})
    assert form["type"] == "form" and set(form["data_schema"].schema) >= {"provider_fallback", "default_provider"}
    result = await options.async_configure(
        flow["flow_id"],
        {"deepl_entry": deepl.entry_id, "google_entry": google.entry_id, "default_provider": GOOGLE, "provider_fallback": True},
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.data == {"providers": {DEEPL: deepl.entry_id, GOOGLE: google.entry_id}}
    assert entry.options["default_provider"] == GOOGLE and entry.options["provider_fallback"] is True
    assert hass.data[DOMAIN].provider.key == GOOGLE
    await hass.config_entries.async_unload(entry.entry_id)


async def test_preferences_offer_the_languages_of_all_services(hass, frontend_ready):
    register_services(hass, DEEPL, ["DE"])
    register_services(hass, GOOGLE, ["de", "pt"])
    entry = MockConfigEntry(domain=DOMAIN, data={"providers": {DEEPL: "d", GOOGLE: "g"}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "preferences"})
    selector = next(iter(form["data_schema"].schema.values()))
    assert selector.config["options"] == ["system", "de", "pt", "pt-BR"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_translator_set_up_for_deepl_alone_still_works_and_notices_google(hass, frontend_ready):
    register_services(hass, DEEPL, ["DE"])
    register_services(hass, GOOGLE, ["de"])
    entry = MockConfigEntry(domain=DOMAIN, data={"deepl_entry": "account"})
    runtime = Runtime(hass, entry)
    assert [item.key for item in runtime.providers.all()] == [DEEPL]
    add_loaded_account(hass, GOOGLE, "Google")
    assert [item.key for item in runtime.providers.all()] == [DEEPL, GOOGLE]
