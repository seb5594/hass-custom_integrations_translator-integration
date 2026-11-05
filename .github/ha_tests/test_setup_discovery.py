"""Native discovery confirmation, duplicate suppression and ignored entries."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState

try:
    from pytest_homeassistant.common import MockConfigEntry
except ImportError:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.custom_integration_translator.const import DEEPL, DOMAIN


async def discover(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "integration_discovery"}, data={}
    )


async def test_confirm_then_choose_account(hass, enable_custom_integrations):
    flow = await discover(hass)
    assert flow["type"] == "form"
    assert flow["step_id"] == "discovery_confirm"
    assert not hass.config_entries.async_entries(DOMAIN)
    duplicate = await discover(hass)
    assert duplicate["type"] == "abort"
    assert duplicate["reason"] == "already_in_progress"
    # Losing the provider must not silently accept setup or discard the suggestion.
    retry = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert retry["errors"] == {"base": "deepl_required"}
    account = MockConfigEntry(
        domain=DEEPL, title="DeepL", state=ConfigEntryState.LOADED
    )
    account.add_to_hass(hass)
    choose = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert choose["step_id"] == "user"
    with patch(
        "custom_components.custom_integration_translator.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"deepl_entry": account.entry_id}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["result"].unique_id == DOMAIN
    assert result["data"] == {"deepl_entry": account.entry_id}


@pytest.mark.parametrize("kind", ["configured", "disabled", "ignored"])
async def test_discovery_respects_existing_choices(
    hass, enable_custom_integrations, kind
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        source="ignore" if kind == "ignored" else "user",
        disabled_by=ConfigEntryDisabler.USER if kind == "disabled" else None,
    )
    entry.add_to_hass(hass)
    result = await discover(hass)
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
