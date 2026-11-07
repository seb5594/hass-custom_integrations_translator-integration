# Changelog

## 2026.11.07.1

- Declare the HTTP dependency and fix setup-link placeholders and the retained-files repair translation schema.

- Prepare a release validated by the shared HASS Marketplace workflow, including HACS and Hassfest without ignored checks.
- Keep the generated Marketplace submission files available as a workflow artifact.

## 2026.11.06.1

- Show missing phrases relative to the total, with a distinct label when every phrase is missing.
- Start new setups with a quiet overview sensor instead of individual notifications and Repairs issues; keep existing choices and provide separate switches. Reuse event-driven checks without extra polling.
- Prefill the integration friendly name as a protected term and preserve workspace edits per integration.
- Preview deduplicated word and character counts including protection markers, and show the DeepL account balance and projected remainder through DeepL Translator 2026.11.06.1+. Distinguish unlimited, unavailable and OAuth accounts.
- Document evaluated AI translation options and the proposed optional AI Task adapter.

## 2026.11.05.8

- After translating or restoring a file, refresh suggestions only for the edited integration instead of scanning every custom integration. Preserve unrelated notifications and Repairs issues.
- Reconcile all suggestions when the monitored language changes or is no longer supported. Targeted refreshes still wait for active file operations and honor automatic-check settings.

## 2026.11.05.7

- Render at most 100 phrase rows per page to keep large translation editors responsive. Bulk selection updates existing checkboxes without rebuilding the editor.
- Search source phrases, existing translations and keys. Preserve selections when paging or searching, show the total selected count and let bulk actions select matching results across all pages.
- Add frontend regression tests to the shared hass-workflows validation.

## 2026.11.05.6

- Reduce scan work by skipping editor rows and revision hashes, parsing the selected source once and only enumerating fallback languages when needed. File conflict and original recovery checks remain active.
- Send identical selected source phrases to DeepL only once per request, then restore the selected order and protected terms for every phrase.
- Avoid background listeners and timers when both missing-language notifications and missing-phrase Repairs issues are disabled.

## 2026.11.05.5

- Include the MIT license and copyright notice in the installable integration ZIP as well as the repository.

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
