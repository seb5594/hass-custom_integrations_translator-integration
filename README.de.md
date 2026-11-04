# Vorlage für Home-Assistant-Integrationen

[🇬🇧 English](README.md) · **🇩🇪 Deutsch**

Die Vorlage enthält eine Beispielintegration mit Konfigurationsdialog, Tests gegen Home Assistant und einer Pipeline für die Release-ZIPs.

1. Erstelle ein Repository mit dem Namen `hass-<projekt>-integration`.
2. Benenne `custom_components/example_integration/` um. Gleiche den Ordnernamen mit `domain` in `manifest.json`, `DOMAIN` in `const.py` und dem ZIP-Namen in `hacs.json` ab. Ersetze die Repository-URLs.
3. Ersetze den Beispielcode und ergänze Tests unter `.github/tests/`. Tests für den echten Home-Assistant-Core gehören nach `.github/ha_tests/`. Die Untergrenze in `hacs.json` gibt an, welche Version du unterstützt.
4. Hinterlege `ORCHESTRATION_PAT` für den Zugriff auf die private Workflow-Engine. Mit einem Checkout unter `.engine/` aktualisiert `python .engine/.scripts/readme.py` den Titel und die Badges der englischen README.
5. Erhöhe für ein Release die Version in `manifest.json` und ergänze den [Changelog](CHANGELOG.md). Auf `main` veröffentlicht die Pipeline die ZIP-Dateien. Eine Version wie `1.0.0b1` kennzeichnet eine Vorabversion.
