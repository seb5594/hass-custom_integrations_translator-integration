"""Translation service adapters. A provider returns HA language keys and one result per input phrase."""

from __future__ import annotations

import re
from collections import Counter
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError
from homeassistant.generated.languages import LANGUAGES

from .const import DEEPL, GOOGLE

_DEEPL_ALIASES = {"en": "EN-US", "pt": "PT-PT", "zh-Hans": "ZH-HANS", "zh-Hant": "ZH-HANT"}
# Google spells a few languages differently from Home Assistant, and its plain "pt" is Brazilian
# Portuguese while Home Assistant's is European. Other regions fall back to their language on
# their own (pt-BR -> pt), so only the real differences are listed.
_GOOGLE_ALIASES = {
    "he": "iw",
    "nb": "no",
    "nn": "no",
    "pt": "pt-PT",
    "zh-Hans": "zh-CN",
    "zh-Hant": "zh-TW",
}
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


class Provider:
    """One translation service that is installed as a Home Assistant integration.

    The services of DeepL Translator and Google Translator answer in the same shape, so the
    only differences are the spelling of language codes and a few names.
    """

    domain = ""
    name = ""

    def __init__(self, hass, entry_id):
        self.hass = hass
        self.entry_id = entry_id

    @property
    def key(self):
        return self.domain

    def target_code(self, ha_key, supported):
        """The code of this service for a Home Assistant language, or None."""
        raise NotImplementedError

    def source_code(self, source, languages):
        """The code of this service for the source language of the phrases."""
        raise NotImplementedError

    async def call(self, service, fields):
        if not self.hass.services.has_service(self.domain, service):
            raise HomeAssistantError(f"{self.name} is unavailable")
        return await self.hass.services.async_call(
            self.domain,
            service,
            {**fields, "config_entry_id": self.entry_id},
            blocking=True,
            return_response=True,
        )

    async def languages(self):
        response = await self.call("get_languages", {"type": "target"})
        supported = {item["code"] for item in response["languages"]}
        return {
            key: code
            for key in sorted(LANGUAGES)
            if (code := self.target_code(key, supported)) is not None
        }

    async def usage(self):
        if not self.hass.services.has_service(self.domain, "get_usage"):
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
                f"{self.name} does not support the selected target language"
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
                    "source_language": self.source_code(source, languages),
                },
            )
            translations = response.get("translations", [])
            if len(translations) != len(masked):
                raise HomeAssistantError(f"{self.name} returned an incomplete batch")
            for item, mapping in zip(translations, mappings, strict=True):
                value = item.get("text")
                if not isinstance(value, str) or not value.strip():
                    raise HomeAssistantError(f"{self.name} returned an empty phrase")
                if Counter(token_pattern.findall(value)) != Counter(mapping.keys()):
                    raise HomeAssistantError(
                        f"{self.name} changed a protected word or placeholder"
                    )
                results.append(
                    token_pattern.sub(
                        lambda match, terms=mapping: terms[match.group()], value
                    )
                )
        translated = dict(zip(unique_phrases, results, strict=True))
        return [translated[phrase] for phrase in phrases]


class DeepLProvider(Provider):
    domain = DEEPL
    name = "DeepL"

    def target_code(self, ha_key, supported):
        code = _DEEPL_ALIASES.get(ha_key, ha_key.upper())
        return code if code in {item.upper() for item in supported} else None

    def source_code(self, source, languages):
        return source.split("-")[0].upper()


class GoogleProvider(Provider):
    domain = GOOGLE
    name = "Google"

    def target_code(self, ha_key, supported):
        by_lower = {code.lower(): code for code in supported}
        base = ha_key.split("-")[0]
        for candidate in (_GOOGLE_ALIASES.get(ha_key), ha_key, base, _GOOGLE_ALIASES.get(base)):
            if candidate and candidate.lower() in by_lower:
                return by_lower[candidate.lower()]
        return None

    def source_code(self, source, languages):
        base = source.split("-")[0]
        return languages.get(source) or languages.get(base) or base.lower()


class UnavailableProvider(Provider):
    """Stands in when no translation service is installed, so callers get a clear error."""

    name = "Translation service"

    def __init__(self, hass):
        super().__init__(hass, None)

    async def call(self, service, fields):
        raise HomeAssistantError(
            "No translation service is available. Set up DeepL Translator or Google Translator."
        )


PROVIDER_TYPES = (DeepLProvider, GoogleProvider)
