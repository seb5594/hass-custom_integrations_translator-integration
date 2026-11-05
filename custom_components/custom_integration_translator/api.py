"""Administrator-only API for the translation panel."""

import base64

from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError
from homeassistant.generated.languages import LANGUAGES

from .catalog import CatalogError, initial_path, read
from .compat import vol
from .const import DOMAIN


@websocket_api.websocket_command(
    {
        "type": f"{DOMAIN}/workspace",
        vol.Required("action"): vol.In(
            ["settings", "list", "detail", "translate", "restore", "original"]
        ),
        vol.Optional("domain"): str,
        vol.Optional("language"): vol.In(LANGUAGES),
        vol.Optional("revision"): str,
        vol.Optional("paths"): [[str]],
        vol.Optional("terms"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def workspace(hass, connection, msg):
    runtime = hass.data.get(DOMAIN)
    if runtime is None or not runtime.active:
        connection.send_error(
            msg["id"], "not_loaded", "Custom Integration Translator is disabled"
        )
        return
    try:
        result = await dispatch(runtime, msg)
    except (HomeAssistantError, OSError, ValueError, KeyError) as err:
        connection.send_error(msg["id"], "translation_error", str(err))
        return
    connection.send_result(msg["id"], result)


async def dispatch(runtime, msg):
    catalog = runtime.catalog
    action = msg["action"]
    if action == "settings":
        problem = None
        try:
            languages = list(await runtime.provider.languages())
        except HomeAssistantError as err:
            languages, problem = [], str(err)
        managed = await runtime.io(catalog.managed)
        return {
            "language": runtime.language,
            "languages": languages,
            "error": problem,
            "recoverable": sorted({language for _, language in managed}),
            "terms": runtime.entry.options.get("protected_words", ""),
        }
    language = msg["language"]
    if action == "list":
        return await runtime.io(catalog.scan, language)
    domain = msg["domain"]
    if action == "detail":
        return await runtime.io(catalog.detail, domain, language)
    if action == "original":

        def fetch():
            journal = catalog.paths(domain, language)[3]
            raw = read(initial_path(journal))
            if raw is None:
                raise CatalogError("No saved original")
            return base64.b64encode(raw).decode()

        return await runtime.io(fetch)
    if action == "translate":
        await runtime.translate(
            domain, language, msg["revision"], msg["paths"], msg.get("terms", [])
        )
    if action == "restore":
        await runtime.restore(domain, language, msg.get("revision"))
    await runtime.refresh(domain=domain)
    return {}
