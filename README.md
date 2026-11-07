<!-- header:begin (generated from project metadata) -->
<h1 align="center">Custom Integration Translator</h1>

<p align="center">
  <img src="https://raw.githubusercontent.com/seb5594/hass-custom_integrations_translator-integration/main/custom_components/custom_integration_translator/brand/icon@2x.png" alt="Custom Integration Translator" width="160" height="160">
</p>

---

<p align="center">
  <a href="https://paypal.me/seb5594"><img src="https://img.shields.io/static/v1?label=Support&amp;message=PayPal&amp;color=0070BA&amp;logo=paypal&amp;logoColor=white&amp;style=for-the-badge" alt="PayPal" height="40"></a>
  <a href="https://buymeacoffee.com/seb5594"><img src="https://img.shields.io/static/v1?label=Support&amp;message=Buy%20Me%20a%20Coffee&amp;color=FFDD00&amp;logo=buy-me-a-coffee&amp;logoColor=black&amp;style=for-the-badge" alt="Buy Me a Coffee" height="40"></a><br>
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=seb5594&amp;repository=hass-custom_integrations_translator-integration&amp;category=integration"><img src="https://img.shields.io/static/v1?label=HACS%20%C2%B7%20Marketplace&amp;message=Add%20integration&amp;color=41BDF5&amp;logo=homeassistantcommunitystore&amp;logoColor=white&amp;style=for-the-badge" alt="HACS · Marketplace" height="28"></a>
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration/actions/workflows/compat.yml"><img src="https://img.shields.io/static/v1?label=home%20assistant&amp;message=%E2%89%A5%202023.7.0&amp;color=1877A5&amp;style=for-the-badge" alt="home assistant" height="28"></a>
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration/releases/tag/v2026.11.06.1"><img src="https://img.shields.io/static/v1?label=version&amp;message=2026.11.06.1&amp;color=1877A5&amp;style=for-the-badge" alt="version" height="28"></a><br>
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration/releases"><img src="https://img.shields.io/github/downloads/seb5594/hass-custom_integrations_translator-integration/v2026.11.06.1/total?label=downloads&amp;color=1877A5&amp;style=flat" alt="downloads" height="20"></a>
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration/issues"><img src="https://img.shields.io/github/issues/seb5594/hass-custom_integrations_translator-integration?label=issues&amp;style=flat" alt="issues" height="20"></a>
  <img src="https://img.shields.io/static/v1?label=tests&amp;message=12%20passed&amp;color=2F855A&amp;style=flat" alt="tests" height="20">
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/seb5594/hass-custom_integrations_translator-integration/ci.yml?branch=main&amp;label=checks&amp;style=flat" alt="checks" height="20"></a>
  <a href="https://github.com/seb5594/hass-custom_integrations_translator-integration#license"><img src="https://img.shields.io/github/license/seb5594/hass-custom_integrations_translator-integration?label=license&amp;style=flat" alt="license" height="20"></a>
</p>
<!-- header:end -->

Translate individual phrases in HACS integrations from within Home Assistant. Compare source and target text, fill missing phrases or retranslate a selection using your existing DeepL account.

[Deutsch](README.de.md)

## Installation

1. Use Home Assistant 2023.7.0 or later. Install and configure [DeepL Translator](https://github.com/seb5594/hass-deepl_translator-integration) first.
2. For manual installation, copy `custom_components/custom_integration_translator` into the matching directory under your Home Assistant configuration folder and restart Home Assistant. For a published release, add this repository to HACS as a custom repository of type **Integration**.
3. With **DeepL Translator 1.0.0b4 or newer** configured, a **Discovered** card appears under **Settings → Devices & services** after HACS/Marketplace installation or startup. Confirm setup and select your DeepL account. Alternatively, use **Add integration → Custom Integration Translator**. Home Assistant's **Ignore** option hides the suggestion persistently. Manual setup still works with older DeepL versions. The discovery card appears in the integrations overview; the associated device is created after setup.
4. As an administrator, press **Open translations** on the integration's device, call `custom_integration_translator.open_workspace`, or visit `/custom-integration-translator` on your instance. Refresh the browser after initial setup if needed. Automations without a user context post a notification linking to the workspace.

## Translate selected phrases

The list shows missing and total phrases, for example **2 missing of 5** or **All 2 missing**. The integration's friendly name is prefilled as a protected term alongside saved defaults. You can edit or remove it; edits are retained per integration while the workspace is open.

The target defaults to the Home Assistant system language. Available targets are the intersection of HA language keys and languages reported by the selected DeepL account. Under **Configure → Language and sidebar**, you can override the default, save protected words and opt into a sidebar shortcut.

Choose an integration. Missing phrases are preselected. Compare the source and current value, then press **Translate selection**. To inspect a complete translation, turn off **Hide translated integrations**. Incomplete integrations come first. Names are sorted alphabetically within each group.

Large translations display 100 phrases per page. Search source text, existing translations or keys to find specific phrases. Searching and paging preserve your selection; the selected count includes hidden phrases. **Select all** and **Missing only** replace the selection with matching results across all pages. **Clear selection** clears the entire selection. Only the visible rows are rendered, and bulk selection updates existing checkboxes without rebuilding the editor.

- English `translations/en.json` is preferred, followed by English `strings.json` and another available developer translation. The workspace displays the source language. Generated files are excluded as translation sources.
- Only selected strings are sent to DeepL. Other target entries, including target-only keys, are preserved. Previously generated phrases are labeled **DeepL**.
- Identical selected source phrases are sent only once per translation request, reducing submitted characters. Each selected key still receives its translation.
- Enter product names with their exact spelling, one per line. The provider masks protected terms and placeholders. An incomplete response or a changed protection marker cancels the write. Your DeepL account's usage terms apply.
- Restart Home Assistant and refresh the browser after writing to update cached translations.

## Discovery and recovery

New setups enable a quiet **Integrations with missing translations** sensor on the translator device, with attributes for missing phrases, missing language files, conflicts and scan errors. It uses the existing checks without extra polling and stays unavailable until a successful check. Individual notifications and Repairs issues default to off for new setups. Existing installations keep their choices: under **Configure → Notifications**, enable the overview sensor and turn off the two individual notification types to switch to this quieter view.

The translator reacts to completed HACS and Marketplace installations, updates and removals, as well as custom integration loading and system language changes. Events within ten seconds are combined into one check. A startup check and a weekly fallback cover manual file copies. Under **Configure → Automatic checks**, set the additional check interval to 0–168 hours. The default is 168 hours (one week). Explicitly saved intervals are preserved. Setting 0 disables only the periodic check. A persistent notification links directly to an integration missing the selected language. A Repairs issue links to the missing phrases when a translation already exists. Translation starts only after your selection. After translating or restoring a file, only the edited integration is checked again for suggestions; unrelated notifications and Repairs issues stay in place. Installation events and periodic checks still scan all integrations. A change of the monitored language also refreshes all suggestions.

Before modifying an existing file, the translator saves its exact bytes as `translations/<language>.json.bak`. A recovery journal in `.storage/custom_integration_translator/` also holds the original outside the HACS-managed directory. The initial developer version stays available for download even after a restore and a later upstream release. Include that directory in backups.

Use **Restore original** to restore the developer's bytes, or **Delete generated file** if the translator created the file. External edits suspend translation. When an original exists, it is available for download. Explicitly restoring across an external edit preserves the newer file as `<language>.json.<SHA256>.bak`. Automatic cleanup stops on a conflict.

Use **Configure → Disable translator** to choose whether to undo all changes before disabling. Keeping translations is the default. Using Home Assistant's native Disable or Delete command also keeps files and offers a Repairs dialog afterward if there are managed translations. Complete recovery before uninstalling the translator's code through HACS.


Under **Configure → Automatic checks**, disable all background checks with the master switch, or separately control startup, HACS, Marketplace, custom integration loading and system language changes. The 0–168 hour interval is on the same page. **Configure → Notifications** separately controls the overview sensor, missing-language notifications and missing-phrase Repairs issues. Saving removes existing translation suggestions of a disabled type; recovery dialogs remain available. Manual selection, translation and restoration in the workspace still work. Turning off the sensor and both notification types stops background listeners and timers. Other preferences are preserved. In DeepL Translator 1.0.0b4+, **Configure → Discover Custom Integration Translator** controls the initial discovery suggestion per DeepL account; disable it on every account to stop suggestions entirely.

## Usage preview

Before translation, the workspace shows selected phrases, unique texts, an approximate word count and estimated transmitted characters. The calculation uses the same protection markers and duplicate removal as translation. [DeepL counts source Unicode code points, including whitespace](https://support.deepl.com/hc/en-us/articles/360020685720-Usage-count-and-billing-in-DeepL-API); words are informational. Protected terms are replaced by markers, and those marker characters also count.

For the account balance, update DeepL Translator to **2026.11.06.1 or newer**. The workspace uses its public `get_usage` action when opening an editor, after a translation attempt and when you press **Refresh account usage**. Changing checkboxes or terms only recalculates on Home Assistant; it does not query DeepL or translate text. It shows the reported remaining quota and estimated balance after your selection. Cache hits, concurrent account usage and reporting delays can affect the result. Successful partial batches can consume quota even if a later batch fails and no file is saved. A missing API, failed usage request or OAuth account displays an unknown balance; uncapped accounts show no fixed limit. No fixed subscription allowance is assumed.

## Compatibility

Supports Home Assistant Core 2023.7 and newer. Service responses, introduced in Core 2023.7, are required for the DeepL integration contract. The shared `hass-workflows` compatibility matrix tests historical Core releases and the current stable release. Older installations use compatible frontend, configuration and event APIs. HACS events work when HACS is installed; Marketplace events apply only to Core versions that provide Marketplace. Use a current browser for the workspace. Automatic discovery on older Core versions requires DeepL Translator 1.0.0b4 and Custom Integration Translator 2026.11.05.4 or newer.

## Development

[AI provider feasibility and the recommended integration path](docs/AI_PROVIDERS.md) documents the evaluated options. This release still translates through DeepL; an optional AI Task adapter is proposed for a follow-up.

Versions use `YYYY.MM.DD.BUILD`. The adapter in `provider.py` uses the public `deepl_translator.get_languages` and `deepl_translator.translate_text` actions. Another provider can implement language discovery and phrase translation independently of the file recovery and review interface.

<!-- support:begin (generated, shared text) -->
## Say thanks

All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time and care, and many of the smart home gadgets I buy end up here because I want to make them cloud-free and smart-home ready. Every bit of support means a lot to me.

If my work helped you or turned out to be useful, show your appreciation with a hot drink for my next sleepless night.

[![PayPal](https://img.shields.io/static/v1?label=Support&message=PayPal&color=0070BA&logo=paypal&logoColor=white&style=for-the-badge)](https://paypal.me/seb5594) [![Buy Me a Coffee](https://img.shields.io/static/v1?label=Support&message=Buy%20Me%20a%20Coffee&color=FFDD00&logo=buy-me-a-coffee&logoColor=black&style=for-the-badge)](https://buymeacoffee.com/seb5594)
<!-- support:end -->

<!-- license:begin (generated from the license file) -->
## License

[![license](https://img.shields.io/static/v1?label=license&message=MIT&color=5B6770&style=flat)](LICENSE)

Published under the [MIT License](LICENSE).
<!-- license:end -->
