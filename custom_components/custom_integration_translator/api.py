"""Administrator-only API for the translation panel."""

import base64

from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError
from homeassistant.generated.languages import LANGUAGES

from .catalog import CatalogError, initial_path, read
from .compat import vol
from .const import DOMAIN
from .provider import estimate
from .providers import CONF_PROVIDER_FALLBACK


@websocket_api.websocket_command(
    {
        "type": f"{DOMAIN}/workspace",
        vol.Required("action"): vol.In(
            [
                "settings",
                "list",
                "detail",
                "translate",
                "restore",
                "original",
                "estimate",
                "usage",
            ]
        ),
        vol.Optional("domain"): str,
        vol.Optional("language"): vol.In(LANGUAGES),
        vol.Optional("revision"): str,
        vol.Optional("paths"): [[str]],
        vol.Optional("terms"): [str],
        vol.Optional("texts"): [str],
        vol.Optional("provider"): str,
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
    if action == "estimate":
        return await runtime.io(estimate, msg["texts"], msg.get("terms", []))
    if action == "usage":
        provider = runtime.providers.get(msg.get("provider")) or runtime.provider
        usage = await provider.usage()
        return {**usage, "provider": provider.key, "provider_name": provider.name}
    if action == "settings":
        return await settings(runtime)
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
    result = {}
    if action == "translate":
        used = await runtime.translate(
            domain,
            language,
            msg["revision"],
            msg["paths"],
            msg.get("terms", []),
            msg.get("provider"),
        )
        if used is not None:
            result = {"provider": used.key, "provider_name": used.name}
    if action == "restore":
        await runtime.restore(domain, language, msg.get("revision"))
    await runtime.refresh(domain=domain)
    return result


async def settings(runtime):
    """What the workspace needs to start: the services, their languages and the defaults."""
    providers = []
    for provider in runtime.providers.all():
        try:
            languages, error = list(await provider.languages()), None
        except HomeAssistantError as err:
            languages, error = [], str(err)
        providers.append(
            {
                "key": provider.key,
                "name": provider.name,
                "languages": languages,
                "error": error,
            }
        )
    fallback = bool(runtime.entry.options.get(CONF_PROVIDER_FALLBACK, False))
    # Only the preferred service is offered unless another one may take over.
    pool = providers if fallback else providers[:1]
    languages = sorted({language for item in pool for language in item["languages"]})
    problem = next((item["error"] for item in pool if item["error"]), None)
    if not providers:
        problem = "No translation service is available. Set up DeepL Translator or Google Translator."
    managed = await runtime.io(runtime.catalog.managed)
    return {
        "language": runtime.language,
        "languages": languages,
        "error": problem if not languages else None,
        "providers": providers,
        "provider": providers[0]["key"] if providers else None,
        "fallback": fallback,
        "recoverable": sorted({language for _, language in managed}),
        "terms": runtime.entry.options.get("protected_words", ""),
    }
