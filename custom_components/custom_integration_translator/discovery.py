"""React to completed installations, with an infrequent fallback for manual copies."""

import logging
from datetime import timedelta

from homeassistant.const import EVENT_COMPONENT_LOADED, EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import IntegrationNotLoaded, async_get_loaded_integration

from .const import DOMAIN

CONF_SCAN_INTERVAL = "scan_interval_hours"
DEFAULT_SCAN_INTERVAL = 24
EVENT_COOLDOWN = 10
_LOGGER = logging.getLogger(__name__)


def monitor(runtime):
    """Subscribe without requiring HACS or Marketplace to be installed."""
    hass, entry = runtime.hass, runtime.entry
    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=EVENT_COOLDOWN,
        immediate=False,
        function=runtime.refresh,
        background=True,
    )
    entry.async_on_unload(debouncer.async_shutdown)

    @callback
    def repository_changed(data):
        # HACS emits install for both first installation and version updates.
        # Empty/registration/update metadata messages are deliberately ignored.
        if isinstance(data, dict) and data.get("action") in ("install", "uninstall"):
            debouncer.async_schedule_call()

    @callback
    def marketplace_finished(data):
        # False ends an attempt after the write or rollback. Numeric progress
        # and routine repository metadata updates do not trigger disk scans.
        if isinstance(data, dict) and data.get("progress") is False:
            debouncer.async_schedule_call()

    @callback
    def component_loaded(event):
        domain = event.data.get("component")
        if not domain or domain == DOMAIN:
            return
        try:
            integration = async_get_loaded_integration(hass, domain)
        except IntegrationNotLoaded:
            return
        if not integration.is_built_in:
            debouncer.async_schedule_call()

    @callback
    def config_updated(event):
        if (
            "language" in event.data
            and entry.options.get("language", "system") == "system"
        ):
            debouncer.async_schedule_call()

    @callback
    def started(_hass):
        debouncer.async_schedule_call()

    for signal, handler in (
        ("hacs_dispatch_repository", repository_changed),
        ("marketplace_repository", repository_changed),
        ("marketplace_repository_install_progress", marketplace_finished),
    ):
        entry.async_on_unload(async_dispatcher_connect(hass, signal, handler))
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_COMPONENT_LOADED, component_loaded)
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, config_updated)
    )
    entry.async_on_unload(async_at_started(hass, started))

    hours = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if hours:
        entry.async_on_unload(
            async_track_time_interval(
                hass,
                runtime.refresh,
                timedelta(hours=hours),
                cancel_on_shutdown=True,
            )
        )
