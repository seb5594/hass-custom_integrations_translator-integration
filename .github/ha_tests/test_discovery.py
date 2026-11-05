"""Installation signals, scan frequency and unload behavior on the real HA event loop."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
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
    await hass.async_block_till_done(wait_background_tasks=True)


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


async def test_discovery_waits_for_translation_lock(hass):
    entry = SimpleNamespace(data={"deepl_entry": "account"}, options={})
    runtime = Runtime(hass, entry)
    runtime.provider.languages = AsyncMock(return_value={hass.config.language: "EN"})
    runtime.catalog.scan = Mock(return_value=[])
    async with runtime.lock:
        task = asyncio.create_task(runtime.refresh())
        await asyncio.sleep(0)
        assert not task.done()
    await task
    runtime.catalog.scan.assert_called_once()
