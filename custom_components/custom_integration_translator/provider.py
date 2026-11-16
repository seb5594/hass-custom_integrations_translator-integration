"""DeepL adapter. A provider returns HA language keys and one result per input phrase."""

from __future__ import annotations

import re
from collections import Counter
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError
from homeassistant.generated.languages import LANGUAGES

from .const import DEEPL

_ALIASES = {"en": "EN-US", "pt": "PT-PT", "zh-Hans": "ZH-HANS", "zh-Hant": "ZH-HANT"}
_FORMAT = r"\[%[^\]]*%\]|\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}|\$?\{[^{}]+\}|%\([^)]+\)[a-zA-Z]|%[sdif]|https?://[^\s<>)]+"


def mask_phrase(pattern, prefix, phrase):
    mapping = {}

    def mask(match):
        token = f"{prefix}{len(mapping)}X"
        mapping[token] = match.group()
        return token

    return pattern.sub(mask, phrase), mapping


def protection_pattern(terms):
    terms = sorted(
        {term.strip() for term in terms if term.strip()}, key=len, reverse=True
    )
    return re.compile("|".join([_FORMAT, *map(re.escape, terms)]), re.DOTALL)


def estimate(phrases, terms):
    """Count the same deduplicated, masked Unicode code points sent for translation."""
    unique = list(dict.fromkeys(phrases))
    pattern = protection_pattern(terms)
    # UUID values vary; their lengths and per-phrase marker indices do not.
    characters = sum(
        len(mask_phrase(pattern, "CIT" + "0" * 32 + "X", text)[0]) for text in unique
    )
    return {
        "selected_phrases": len(phrases),
        "unique_phrases": len(unique),
        "words": sum(len(text.split()) for text in unique),
        "source_characters": sum(len(text) for text in unique),
        "characters": characters,
    }


class DeepLProvider:
    def __init__(self, hass, entry_id):
        self.hass = hass
        self.entry_id = entry_id

    async def call(self, service, fields):
        if not self.hass.services.has_service(DEEPL, service):
            raise HomeAssistantError("DeepL Translator is unavailable")
        return await self.hass.services.async_call(
            DEEPL,
            service,
            {**fields, "config_entry_id": self.entry_id},
            blocking=True,
            return_response=True,
        )

    async def languages(self):
        response = await self.call("get_languages", {"type": "target"})
        supported = {item["code"].upper() for item in response["languages"]}
        return {
            key: code
            for key in sorted(LANGUAGES)
            if (code := _ALIASES.get(key, key.upper())) in supported
        }

    async def usage(self):
        if not self.hass.services.has_service(DEEPL, "get_usage"):
            return {"available": False, "reason": "update_required"}
        try:
            return await self.call("get_usage", {"refresh": True})
        except HomeAssistantError:
            return {"available": False, "reason": "unavailable"}

    async def translate(self, phrases, source, target, terms):
        if not phrases:
            return []
        unique_phrases = list(dict.fromkeys(phrases))
        # The same check applies to credentials using the API and the MCP backend.
        languages = await self.languages()
        if target not in languages:
            raise HomeAssistantError(
                "DeepL does not support the selected target language"
            )
        pattern = protection_pattern(terms)
        prefix = "CIT" + uuid4().hex + "X"
        token_pattern = re.compile(re.escape(prefix) + r"\d+X")
        results = []
        for start in range(0, len(unique_phrases), 50):
            masked = []
            mappings = []
            for phrase in unique_phrases[start : start + 50]:
                text, mapping = mask_phrase(pattern, prefix, phrase)
                masked.append(text)
                mappings.append(mapping)
            response = await self.call(
                "translate_text",
                {
                    "text": masked,
                    "target_language": languages[target],
                    "source_language": source.split("-")[0].upper(),
                },
            )
            translations = response.get("translations", [])
            if len(translations) != len(masked):
                raise HomeAssistantError("DeepL returned an incomplete batch")
            for item, mapping in zip(translations, mappings, strict=True):
                value = item.get("text")
                if not isinstance(value, str) or not value.strip():
                    raise HomeAssistantError("DeepL returned an empty phrase")
                if Counter(token_pattern.findall(value)) != Counter(mapping.keys()):
                    raise HomeAssistantError(
                        "DeepL changed a protected word or placeholder"
                    )
                results.append(
                    token_pattern.sub(
                        lambda match, terms=mapping: terms[match.group()], value
                    )
                )
        translated = dict(zip(unique_phrases, results, strict=True))
        return [translated[phrase] for phrase in phrases]
