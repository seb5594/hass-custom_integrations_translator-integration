"""Translation batching preserves selection order, duplicates and protected terms."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.custom_integration_translator.provider import DeepLProvider


async def test_duplicate_phrases_only_sent_once_across_batches(hass):
    provider = DeepLProvider(hass, "account")
    sent = []

    async def call(service, fields):
        if service == "get_languages":
            return {"languages": [{"code": "DE"}]}
        sent.append(fields["text"])
        assert all(
            "ACME" not in text and "{name}" not in text for text in fields["text"]
        )
        return {"translations": [{"text": "DE " + text} for text in fields["text"]]}

    provider.call = AsyncMock(side_effect=call)
    unique = [f"Open ACME {{name}} {index}" for index in range(51)]
    phrases = [unique[-1], *unique, *reversed(unique), unique[0]]
    result = await provider.translate(phrases, "en", "de", ["ACME"])
    assert result == ["DE " + phrase for phrase in phrases]
    assert [len(batch) for batch in sent] == [50, 1]


@pytest.mark.parametrize("failure", ["incomplete", "protected_word"])
async def test_deduplicated_batch_still_rejects_bad_responses(hass, failure):
    provider = DeepLProvider(hass, "account")

    async def call(service, fields):
        if service == "get_languages":
            return {"languages": [{"code": "DE"}]}
        return {
            "translations": []
            if failure == "incomplete"
            else [{"text": "Lost protection"}]
        }

    provider.call = AsyncMock(side_effect=call)
    with pytest.raises(HomeAssistantError):
        await provider.translate(["Open ACME", "Open ACME"], "en", "de", ["ACME"])


async def test_empty_selection_does_not_contact_provider(hass):
    provider = DeepLProvider(hass, "account")
    provider.call = AsyncMock()
    assert await provider.translate([], "en", "de", []) == []
    provider.call.assert_not_called()


async def test_estimate_counts_actual_masked_unicode_payload(hass):
    from custom_components.custom_integration_translator.provider import estimate

    provider = DeepLProvider(hass, "account")
    sent = []

    async def call(service, fields):
        if service == "get_languages":
            return {"languages": [{"code": "DE"}]}
        sent.extend(fields["text"])
        return {"translations": [{"text": text} for text in fields["text"]]}

    provider.call = AsyncMock(side_effect=call)
    phrases = ["Open ACME {name} 😀 é", "Open ACME {name} 😀 é", "Close"]
    planned = estimate(phrases, ["ACME"])
    assert planned["selected_phrases"] == 3
    assert planned["unique_phrases"] == 2
    await provider.translate(phrases, "en", "de", ["ACME"])
    assert planned["characters"] == sum(map(len, sent))
    assert planned["characters"] > planned["source_characters"]
    assert estimate([], [])["characters"] == 0


async def test_usage_without_new_deepl_service_is_explicitly_unknown(hass):
    assert await DeepLProvider(hass, "account").usage() == {
        "available": False,
        "reason": "update_required",
    }
