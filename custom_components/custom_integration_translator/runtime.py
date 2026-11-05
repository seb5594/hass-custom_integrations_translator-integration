"""Translation workflow and discovery for one config entry."""

import asyncio
import logging
from urllib.parse import urlencode

from homeassistant.components import persistent_notification
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from .catalog import Catalog, CatalogError
from .const import DOMAIN, NAME, PANEL
from .discovery import (
    CONF_AUTOMATIC_CHECKS,
    CONF_NOTIFY_MISSING,
    CONF_REPAIR_MISSING,
    monitor,
)
from .provider import DeepLProvider

_LOGGER = logging.getLogger(__name__)


def file_lock(hass):
    """Coordinate active translations with repairs after disabling or removing an entry."""
    return hass.data.setdefault(f"{DOMAIN}_file_lock", asyncio.Lock())


class Runtime:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.catalog = Catalog(hass.config.config_dir)
        self.provider = DeepLProvider(hass, entry.data["deepl_entry"])
        self.lock = file_lock(hass)
        self.active = True
        self.alerts = set()
        self.issues = set()

    @property
    def language(self):
        language = self.entry.options.get("language", "system")
        return self.hass.config.language if language == "system" else language

    async def io(self, func, *args):
        return await self.hass.async_add_executor_job(func, *args)

    async def translate(self, domain, language, revision, paths, terms):
        async with self.lock:
            detail = await self.io(self.catalog.detail, domain, language)
            if not self.active or detail["conflict"] or detail["revision"] != revision:
                raise CatalogError("Files changed. Open the integration again.")
            selected = {tuple(path) for path in paths}
            rows = [row for row in detail["rows"] if tuple(row["path"]) in selected]
            if not rows or len(rows) != len(selected):
                raise CatalogError("Invalid phrase selection")
            values = await self.provider.translate(
                [row["source"] for row in rows],
                detail["source_language"],
                language,
                terms,
            )
            if not self.active:
                raise CatalogError("Integration disabled")
            changes = {
                tuple(row["path"]): value
                for row, value in zip(rows, values, strict=True)
            }
            await self.io(self.catalog.save, domain, language, revision, changes)

    async def restore(self, domain, language, revision=None):
        async with self.lock:
            if not self.active:
                raise CatalogError("Integration disabled")
            await self.io(self.catalog.restore, domain, language, revision)

    async def restore_all(self):
        async with self.lock:
            await self.io(self.catalog.restore_all)

    def monitor(self):
        monitor(self)

    async def refresh(self, now=None):
        if not self.active or not self.entry.options.get(CONF_AUTOMATIC_CHECKS, True):
            return
        if not any(
            self.entry.options.get(key, True)
            for key in (CONF_NOTIFY_MISSING, CONF_REPAIR_MISSING)
        ):
            self.cleanup()
            return
        async with self.lock:
            if not self.active:
                return
            try:
                language = self.language
                supported = await self.provider.languages()
                items = (
                    await self.io(self.catalog.scan, language)
                    if language in supported
                    else []
                )
            except (HomeAssistantError, OSError, ValueError) as err:
                _LOGGER.debug("Discovery postponed: %s", err)
                return
            if not self.active:
                return
            alerts, issues = set(), set()
            german = self.hass.config.language.startswith("de")
            for item in items:
                if not item["missing"] or item.get("conflict"):
                    continue
                domain = item["domain"]
                key = f"{domain}_{language}"
                url = f"/{PANEL}?" + urlencode({"domain": domain, "language": language})
                if item["exists"]:
                    if not self.entry.options.get(CONF_REPAIR_MISSING, True):
                        continue
                    issues.add(key)
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        key,
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="missing",
                        translation_placeholders={
                            "name": item["name"],
                            "language": language,
                            "count": str(item["missing"]),
                            "url": url,
                        },
                    )
                else:
                    if not self.entry.options.get(CONF_NOTIFY_MISSING, True):
                        continue
                    alerts.add(key)
                    if key not in self.alerts:
                        label = (
                            "Übersetzung anlegen" if german else "Create translation"
                        )
                        persistent_notification.async_create(
                            self.hass,
                            f"{item['name']} ({language}) · [{label}]({url})",
                            title=NAME,
                            notification_id=f"{DOMAIN}_{key}",
                        )
            for key in self.alerts - alerts:
                persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{key}")
            for key in self.issues - issues:
                ir.async_delete_issue(self.hass, DOMAIN, key)
            self.alerts, self.issues = alerts, issues

    def cleanup(self):
        for key in self.alerts:
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{key}")
        for key in self.issues:
            ir.async_delete_issue(self.hass, DOMAIN, key)
        self.alerts.clear()
        self.issues.clear()
