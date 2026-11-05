"""React to completed installations, with an infrequent fallback for manual copies."""

import logging
from datetime import timedelta

from homeassistant.const import EVENT_COMPONENT_LOADED, EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .compat import schedule_refresh
from .const import DOMAIN

CONF_SCAN_INTERVAL = "scan_interval_hours"
CONF_AUTOMATIC_CHECKS = "automatic_checks"
CONF_SCAN_STARTUP = "scan_startup"
CONF_WATCH_HACS = "watch_hacs"
CONF_WATCH_MARKETPLACE = "watch_marketplace"
CONF_SCAN_LOADED = "scan_loaded"
CONF_SCAN_LANGUAGE = "scan_language"
CONF_NOTIFY_MISSING = "notify_missing"
CONF_REPAIR_MISSING = "repair_missing"
TRIGGER_OPTIONS = (
    CONF_AUTOMATIC_CHECKS,
    CONF_SCAN_STARTUP,
    CONF_WATCH_HACS,
    CONF_WATCH_MARKETPLACE,
    CONF_SCAN_LOADED,
    CONF_SCAN_LANGUAGE,
)
NOTICE_OPTIONS = (CONF_NOTIFY_MISSING, CONF_REPAIR_MISSING)
DEFAULT_SCAN_INTERVAL = 168
EVENT_COOLDOWN = 10
_LOGGER = logging.getLogger(__name__)


def monitor(runtime):
    """Subscribe without requiring HACS or Marketplace to be installed."""
    hass, entry = runtime.hass, runtime.entry
    if not entry.options.get(CONF_AUTOMATIC_CHECKS, True):
        return
    schedule = schedule_refresh(hass, entry, _LOGGER, runtime.refresh, EVENT_COOLDOWN)

    @callback
    def repository_changed(data):
        # HACS emits install for both first installation and version updates.
        # Empty/registration/update metadata messages are deliberately ignored.
        if isinstance(data, dict) and data.get("action") in ("install", "uninstall"):
            schedule()

    @callback
    def marketplace_finished(data):
        # False ends an attempt after the write or rollback. Numeric progress
        # and routine repository metadata updates do not trigger disk scans.
        if isinstance(data, dict) and data.get("progress") is False:
            schedule()

    async def component_loaded(event):
        domain = event.data.get("component")
        if not domain or domain == DOMAIN:
            return
        try:
            integration = await async_get_integration(hass, domain)
        except IntegrationNotFound:
            return
        if not integration.is_built_in:
            schedule()

    @callback
    def config_updated(event):
        if (
            "language" in event.data
            and entry.options.get("language", "system") == "system"
        ):
            schedule()

    @callback
    def started(_hass):
        schedule()

    for option, signal, handler in (
        (CONF_WATCH_HACS, "hacs_dispatch_repository", repository_changed),
        (CONF_WATCH_MARKETPLACE, "marketplace_repository", repository_changed),
        (
            CONF_WATCH_MARKETPLACE,
            "marketplace_repository_install_progress",
            marketplace_finished,
        ),
    ):
        if entry.options.get(option, True):
            entry.async_on_unload(async_dispatcher_connect(hass, signal, handler))
    if entry.options.get(CONF_SCAN_LOADED, True):
        entry.async_on_unload(
            hass.bus.async_listen(EVENT_COMPONENT_LOADED, component_loaded)
        )
    if entry.options.get(CONF_SCAN_LANGUAGE, True):
        entry.async_on_unload(
            hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, config_updated)
        )
    if entry.options.get(CONF_SCAN_STARTUP, True):
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
