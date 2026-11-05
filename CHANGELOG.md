# Changelog

## 2026.11.05.4

- Support Core 2023.7 and newer through compatible schema, frontend, runtime, options and event APIs, with historical Core tests.

- Add an automatic-check master switch and individual startup, HACS, Marketplace, component-load and language-change switches.
- Separately control missing-language notifications and missing-phrase Repairs issues. Settings pages preserve each other and work without contacting DeepL.
- Change the license to MIT, copyright seb5594 (Sebastian Schmidt).

## 2026.11.05.3

- Offer a native discovery card with explicit confirmation through DeepL Translator 1.0.0b3 or newer after installation or startup. Existing, disabled and ignored entries are respected.
- Default the additional scan to once a week (168 hours); preserve explicitly saved intervals and support 0 to disable polling.

## 2026.11.05.2

- Detect HACS and Marketplace installations and removals through dispatcher signals, with events coalesced over ten seconds.
- Replace five-minute polling with a configurable daily fallback, including an option to disable periodic checks.
- Keep discovery requests pending while a translation is writing and cancel listeners on unload.

## 2026.11.05.1

- Initial Custom Integration Translator release with DeepL account selection, a popup and an optional sidebar workspace.
- Review source and target phrases, fill missing keys, protect names and placeholders, or retranslate selected text.
- Discover missing translations, create Repairs issues and recover exact developer originals after repeated edits.
