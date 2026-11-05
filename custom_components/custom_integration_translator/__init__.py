"""Set up the translator and its optional sidebar panel."""

from pathlib import Path

from homeassistant.components import (
    frontend,
    panel_custom,
    persistent_notification,
    websocket_api,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service

from .api import workspace
from .const import ASSETS, DOMAIN, NAME, PANEL
from .runtime import Runtime

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
LAUNCHER = f"{ASSETS}/launcher.js?v=2026.11.05.3"


@callback
def open_workspace(hass, context):
    if context and context.user_id:
        hass.bus.async_fire(
            f"{DOMAIN}_open", {"user_id": context.user_id}, context=context
        )
    else:
        label = (
            "Übersetzungen öffnen"
            if hass.config.language.startswith("de")
            else "Open translations"
        )
        persistent_notification.async_create(
            hass, f"[{label}](/{PANEL})", title=NAME, notification_id=f"{DOMAIN}_open"
        )


async def async_setup(hass, config):
    await hass.http.async_register_static_paths(
        [StaticPathConfig(ASSETS, str(Path(__file__).parent / "frontend"), False)]
    )
    websocket_api.async_register_command(hass, workspace)
    return True


async def async_setup_entry(hass, entry):
    runtime = Runtime(hass, entry)
    hass.data[DOMAIN] = runtime
    entry.runtime_data = runtime

    async def handle_open(call):
        open_workspace(hass, call.context)

    service.async_register_admin_service(hass, DOMAIN, "open_workspace", handle_open)
    await panel_custom.async_register_panel(
        hass,
        PANEL,
        "cit-workspace",
        sidebar_title=NAME if entry.options.get("sidebar") else None,
        sidebar_icon="mdi:translate",
        module_url=f"{ASSETS}/workspace.js?v=2026.11.05.3",
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    frontend.add_extra_js_url(hass, LAUNCHER)
    await hass.config_entries.async_forward_entry_setups(entry, ["button"])
    entry.async_on_unload(entry.add_update_listener(reload_entry))
    runtime.monitor()
    return True


async def reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    runtime = entry.runtime_data
    runtime.active = False
    if not await hass.config_entries.async_unload_platforms(entry, ["button"]):
        runtime.active = True
        return False
    async with runtime.lock:
        runtime.cleanup()
    frontend.remove_extra_js_url(hass, LAUNCHER)
    frontend.async_remove_panel(hass, PANEL)
    hass.services.async_remove(DOMAIN, "open_workspace")
    hass.data.pop(DOMAIN, None)
    if entry.disabled_by and not getattr(runtime, "guided_disable", False):
        await offer_cleanup(hass)
    return True


async def offer_cleanup(hass):
    from .catalog import Catalog
    from .repairs import offer_review

    managed = await hass.async_add_executor_job(Catalog(hass.config.config_dir).managed)
    if managed:
        offer_review(hass, len(managed))


async def async_remove_entry(hass, entry):
    await offer_cleanup(hass)
