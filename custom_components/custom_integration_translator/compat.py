"""Small API bridges for supported Home Assistant generations."""

from inspect import isawaitable, signature

from homeassistant.components import frontend, panel_custom
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import callback
from homeassistant.helpers.debounce import Debouncer

__all__ = [
    "register_assets",
    "register_panel",
    "remove_launcher",
    "schedule_refresh",
    "vol",
]

# Use the same schema implementation as Core (Voluptuous or Probatio).
if (MAJOR_VERSION, MINOR_VERSION) >= (2026, 11):
    import probatio as vol
else:
    import voluptuous as vol


async def register_assets(hass, url, path):
    if hasattr(hass.http, "async_register_static_paths"):
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(url, path, False)]
        )
    else:
        hass.http.register_static_path(url, path, cache_headers=False)


async def register_panel(hass, domain, *args, **kwargs):
    if "config_panel_domain" in signature(panel_custom.async_register_panel).parameters:
        kwargs["config_panel_domain"] = domain
    await panel_custom.async_register_panel(hass, *args, **kwargs)


def remove_launcher(hass, url):
    if hasattr(frontend, "remove_extra_js_url"):
        frontend.remove_extra_js_url(hass, url)
    else:
        hass.data[frontend.DATA_EXTRA_MODULE_URL].remove(url)


def schedule_refresh(hass, entry, logger, refresh, cooldown):
    """Return a synchronous scheduler and cancel delayed calls on every Core."""
    debouncer = Debouncer(
        hass, logger, cooldown=cooldown, immediate=False, function=refresh
    )
    active = True

    @callback
    def shutdown():
        nonlocal active
        active = False
        debouncer.async_cancel()
        result = debouncer.async_shutdown()
        if isawaitable(result):
            hass.async_create_task(result)

    @callback
    def schedule():
        if active:
            hass.async_create_task(debouncer.async_call())

    entry.async_on_unload(shutdown)
    return schedule
