"""Review retained files even after the config entry has been removed."""

from homeassistant.components.repairs import RepairsFlow
from homeassistant.helpers import issue_registry as ir

from .catalog import Catalog
from .compat import vol
from .const import DOMAIN
from .runtime import file_lock


def offer_review(hass, count):
    ir.async_create_issue(
        hass,
        DOMAIN,
        "retained",
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="retained",
        translation_placeholders={"count": str(count)},
    )


class RetainedFilesFlow(RepairsFlow):
    async def async_step_init(self, user_input=None):
        return await self.async_step_review()

    async def async_step_review(self, user_input=None):
        error = ""
        if user_input is not None:
            try:
                if user_input.get("undo"):
                    if runtime := self.hass.data.get(DOMAIN):
                        await runtime.restore_all()
                    else:
                        catalog = Catalog(self.hass.config.config_dir)

                        async with file_lock(self.hass):
                            await self.hass.async_add_executor_job(catalog.restore_all)
                # The repairs flow manager clears the issue on successful completion.
                return self.async_create_entry(title="", data={})
            except (OSError, ValueError) as err:
                error = str(err)
        return self.async_show_form(
            step_id="review",
            description_placeholders={"detail": error},
            data_schema=vol.Schema({vol.Required("undo", default=False): bool}),
        )


async def async_create_fix_flow(hass, issue_id, data):
    return RetainedFilesFlow()
