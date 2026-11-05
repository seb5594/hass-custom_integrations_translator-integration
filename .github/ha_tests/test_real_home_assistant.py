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
    with patch(
        "homeassistant.components.http.HomeAssistantHTTP.start", new=AsyncMock()
    ):
        assert await async_setup_component(hass, "frontend", {})
        assert await async_setup_component(hass, "persistent_notification", {})
        yield tmp_path


async def test_requires_deepl(hass, frontend_ready):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["reason"] == "deepl_required"


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
