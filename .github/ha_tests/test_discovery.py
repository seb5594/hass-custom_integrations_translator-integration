"""Installation signals, scan frequency and unload behavior on the real HA event loop."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import (
    EVENT_COMPONENT_LOADED,
    EVENT_CORE_CONFIG_UPDATE,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

try:
    from pytest_homeassistant.common import async_fire_time_changed
except ImportError:
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.custom_integration_translator.discovery import monitor
from custom_components.custom_integration_translator.runtime import Runtime


@pytest.fixture
def discovery(hass):
    cleanups = []
    runtime = SimpleNamespace(
        hass=hass,
        refresh=AsyncMock(),
        entry=SimpleNamespace(options={}, async_on_unload=cleanups.append),
    )
    yield runtime, cleanups
    for cleanup in reversed(cleanups):
        cleanup()


async def advance(hass, seconds):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("signal", "payload"),
    [
        ("hacs_dispatch_repository", {"action": "install"}),
        ("hacs_dispatch_repository", {"action": "uninstall"}),
        ("marketplace_repository", {"action": "uninstall"}),
        ("marketplace_repository_install_progress", {"progress": False}),
    ],
)
async def test_completed_operations_are_coalesced(hass, discovery, signal, payload):
    runtime, cleanups = discovery
    runtime.entry.options["scan_interval_hours"] = 0
    monitor(runtime)
    await hass.async_block_till_done()
    await advance(hass, 11)
    runtime.refresh.reset_mock()
    for _ in range(5):
        async_dispatcher_send(hass, signal, payload)
    await hass.async_block_till_done()
    runtime.refresh.assert_not_called()
    await advance(hass, 11)
    runtime.refresh.assert_awaited_once()
    # A pending event and all listeners must disappear when the entry unloads.
    async_dispatcher_send(hass, signal, payload)
    await hass.async_block_till_done()
    for cleanup in reversed(cleanups):
        cleanup()
    cleanups.clear()
    async_dispatcher_send(hass, signal, payload)
    await advance(hass, 30)
    runtime.refresh.assert_awaited_once()


async def test_metadata_and_download_progress_do_not_scan(hass, discovery):
    runtime, _ = discovery
    monitor(runtime)
    await hass.async_block_till_done()
    await advance(hass, 11)
    runtime.refresh.reset_mock()
    for action in ("update", "registration", None):
        async_dispatcher_send(hass, "hacs_dispatch_repository", {"action": action})
        async_dispatcher_send(hass, "marketplace_repository", {"action": action})
    for progress in (0, 10, 30, 70, 90, None):
        async_dispatcher_send(
            hass, "marketplace_repository_install_progress", {"progress": progress}
        )
    await hass.async_block_till_done()
    await advance(hass, 3600)
    runtime.refresh.assert_not_called()


@pytest.mark.parametrize(
    ("options", "hours"),
    [({}, 168), ({"scan_interval_hours": 24}, 24), ({"scan_interval_hours": 48}, 48)],
)
async def test_fallback_interval(hass, discovery, options, hours):
    runtime, _ = discovery
    runtime.entry.options = options
    monitor(runtime)
    await hass.async_block_till_done()
    await advance(hass, 11)
    runtime.refresh.reset_mock()
    await advance(hass, hours * 3600 - 60)
    runtime.refresh.assert_not_called()
    await advance(hass, hours * 3600 + 1)
    runtime.refresh.assert_awaited_once()


async def test_startup_still_scans_with_periodic_check_disabled(hass, discovery):
    runtime, _ = discovery
    runtime.entry.options["scan_interval_hours"] = 0
    monitor(runtime)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    await advance(hass, 11)
    runtime.refresh.assert_awaited_once()
    await advance(hass, 7 * 24 * 3600)
    runtime.refresh.assert_awaited_once()


@pytest.mark.parametrize("domain", [None, "example"])
async def test_discovery_waits_for_translation_lock(hass, domain):
    entry = SimpleNamespace(data={"deepl_entry": "account"}, options={})
    runtime = Runtime(hass, entry)
    runtime.provider.languages = AsyncMock(return_value={hass.config.language: "EN"})
    runtime.catalog.scan = Mock(return_value=[])
    runtime.catalog.summary = Mock(return_value={"domain": "example", "missing": 0})
    async with runtime.lock:
        task = asyncio.create_task(runtime.refresh(domain=domain))
        await asyncio.sleep(0)
        assert not task.done()
    await task
    assert runtime.catalog.scan.call_count == int(domain is None)
    assert runtime.catalog.summary.call_count == int(domain is not None)


async def test_master_switch_prevents_all_background_work(hass, discovery):
    runtime, cleanups = discovery
    runtime.entry.options = {"automatic_checks": False, "scan_interval_hours": 1}
    monitor(runtime)
    assert not cleanups
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE, {"language": "de"})
    async_dispatcher_send(hass, "hacs_dispatch_repository", {"action": "install"})
    async_dispatcher_send(
        hass, "marketplace_repository_install_progress", {"progress": False}
    )
    await advance(hass, 8 * 24 * 3600)
    runtime.refresh.assert_not_called()


async def test_disabled_notices_register_no_background_work(hass, discovery):
    runtime, cleanups = discovery
    runtime.entry.options = {"notify_missing": False, "repair_missing": False}
    monitor(runtime)
    assert not cleanups
    async_dispatcher_send(hass, "hacs_dispatch_repository", {"action": "install"})
    await advance(hass, 8 * 24 * 3600)
    runtime.refresh.assert_not_called()


@pytest.mark.parametrize(
    "option,event,data,dispatcher",
    [
        ("scan_startup", EVENT_HOMEASSISTANT_STARTED, {}, False),
        ("watch_hacs", "hacs_dispatch_repository", {"action": "install"}, True),
        (
            "watch_marketplace",
            "marketplace_repository_install_progress",
            {"progress": False},
            True,
        ),
        ("scan_loaded", EVENT_COMPONENT_LOADED, {"component": "example"}, False),
        ("scan_language", EVENT_CORE_CONFIG_UPDATE, {"language": "de"}, False),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
async def test_trigger_switches(
    hass, discovery, option, event, data, dispatcher, enabled
):
    runtime, _ = discovery
    runtime.entry.options = {
        "scan_startup": False,
        "watch_hacs": False,
        "watch_marketplace": False,
        "scan_loaded": False,
        "scan_language": False,
        "scan_interval_hours": 0,
        option: enabled,
    }
    monitor(runtime)
    with patch(
        "custom_components.custom_integration_translator.discovery.async_get_integration",
        new=AsyncMock(return_value=SimpleNamespace(is_built_in=False)),
    ):
        if dispatcher:
            async_dispatcher_send(hass, event, data)
        else:
            hass.bus.async_fire(event, data)
        await hass.async_block_till_done()
        await advance(hass, 11)
    assert runtime.refresh.await_count == int(enabled)
