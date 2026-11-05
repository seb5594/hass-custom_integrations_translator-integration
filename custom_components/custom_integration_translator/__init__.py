"""Set up the translator and its optional sidebar panel."""

from pathlib import Path

from homeassistant.components import (
    frontend,
    persistent_notification,
    websocket_api,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service

from .api import workspace
from .compat import register_assets, register_panel, remove_launcher
from .const import ASSETS, DOMAIN, NAME, PANEL
from .runtime import Runtime

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
LAUNCHER = f"{ASSETS}/launcher.js?v=2026.11.05.8"


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
    await register_assets(hass, ASSETS, str(Path(__file__).parent / "frontend"))
    websocket_api.async_register_command(hass, workspace)
    return True


async def async_setup_entry(hass, entry):
    runtime = Runtime(hass, entry)
    hass.data[DOMAIN] = runtime
    if hasattr(ConfigEntry, "runtime_data"):
        entry.runtime_data = runtime

    async def handle_open(call):
        open_workspace(hass, call.context)

    service.async_register_admin_service(hass, DOMAIN, "open_workspace", handle_open)
    await register_panel(
        hass,
        DOMAIN,
        PANEL,
        "cit-workspace",
        sidebar_title=NAME if entry.options.get("sidebar") else None,
        sidebar_icon="mdi:translate",
        module_url=f"{ASSETS}/workspace.js?v=2026.11.05.8",
        require_admin=True,
    )
    frontend.add_extra_js_url(hass, LAUNCHER)
    await hass.config_entries.async_forward_entry_setups(entry, ["button"])
    entry.async_on_unload(entry.add_update_listener(reload_entry))
    runtime.monitor()
    return True


async def reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    runtime = hass.data[DOMAIN]
    runtime.active = False
    if not await hass.config_entries.async_unload_platforms(entry, ["button"]):
        runtime.active = True
        return False
    async with runtime.lock:
        runtime.cleanup()
    remove_launcher(hass, LAUNCHER)
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
