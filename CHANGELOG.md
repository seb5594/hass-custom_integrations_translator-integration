# Changelog

## 2026.11.05.2

- Detect HACS and Marketplace installations and removals through dispatcher signals, with events coalesced over ten seconds.
- Replace five-minute polling with a configurable daily fallback, including an option to disable periodic checks.
- Keep discovery requests pending while a translation is writing and cancel listeners on unload.

## 2026.11.05.1

- Initial Custom Integration Translator release with DeepL account selection, a popup and an optional sidebar workspace.
- Review source and target phrases, fill missing keys, protect names and placeholders, or retranslate selected text.
- Discover missing translations, create Repairs issues and recover exact developer originals after repeated edits.
