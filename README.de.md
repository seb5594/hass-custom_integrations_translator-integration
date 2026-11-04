# Custom Integration Translator

Ergänze die Übersetzungen deiner HACS-Integrationen direkt in Home Assistant. Du siehst Quelltext und vorhandene Übersetzung nebeneinander und entscheidest für jede Phrase, ob DeepL sie bearbeiten soll.

[English](README.md)

## Einrichten

1. Verwende Home Assistant ab Version 2026.11.0. Installiere zuerst [DeepL Translator](https://github.com/seb5594/hass-deepl_translator-integration) und richte dort dein DeepL-Konto ein.
2. Für die manuelle Installation kopiere den Ordner `custom_components/custom_integration_translator` in den gleichnamigen Pfad unter deinem Home-Assistant-Konfigurationsordner. Starte Home Assistant neu. Für ein veröffentlichtes Release kannst du dieses Repository auch in HACS als benutzerdefiniertes Repository der Kategorie **Integration** hinzufügen.
3. Öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen → Custom Integration Translator** und wähle dein eingerichtetes DeepL-Konto.
4. Drücke als Administrator auf dem zugehörigen Gerät **Übersetzungen öffnen**. Alternativ verwende die Aktion `custom_integration_translator.open_workspace` oder öffne in deiner Instanz `/custom-integration-translator`. Aufrufe aus Automationen ohne Benutzerkontext erzeugen eine Benachrichtigung mit Link. Nach der ersten Einrichtung hilft bei einem bereits geöffneten Browser ein Neuladen.

## Eine Übersetzung ergänzen

Die Ansicht wählt die Systemsprache vor. Angeboten werden Sprachschlüssel, die sowohl Home Assistant als auch dein DeepL-Konto unterstützen. Unter **Konfigurieren → Sprache und Sidebar** kannst du die Voreinstellung ändern, geschützte Begriffe hinterlegen und die optionale Sidebar-Verknüpfung einschalten.

**Beispiel:** Eine Integration enthält zwölf englische Texte, aber nur neun deutsche. Öffne ihren Eintrag. Die drei fehlenden Texte sind bereits markiert. Prüfe die Vorschau, trage bei Bedarf Produktnamen ein und drücke **Auswahl übersetzen (3)**. Der Translator ergänzt die ausgewählten Schlüssel in `translations/de.json`. Andere Texte und zusätzliche Schlüssel der Zielversion bleiben erhalten.

- Die Liste sortiert Integrationen mit fehlenden Texten nach vorn und innerhalb jeder Gruppe alphabetisch. Schalte **Verstecke übersetzte Integrationen** aus, um vollständige Übersetzungen zu prüfen oder zurückzusetzen.
- Als Quelle dient bevorzugt `translations/en.json`, danach `strings.json` oder eine andere vorhandene Sprachdatei. Die Ansicht zeigt die verwendete Quellsprache. Selbst erzeugte Fassungen werden bei der Quellwahl übersprungen.
- Mit **Alle auswählen** kannst du eine vollständige Neuübersetzung anstoßen. **Auswahl aufheben** ermöglicht die Auswahl einzelner Texte. Bereits von DeepL bearbeitete Phrasen sind gekennzeichnet.
- Gib geschützte Wörter oder Produktnamen mit exakter Schreibweise ein, eines pro Zeile. Marken und Platzhalter wie `{name}` werden vor dem Versand maskiert. Verändert DeepL eine Markierung, wird der gesamte Auftrag verworfen. Für die gesendeten Texte gelten die Konditionen deines DeepL-Kontos.
- Starte Home Assistant nach dem Speichern neu und lade den Browser neu, damit auch bereits zwischengespeicherte Übersetzungen aktualisiert werden.

## Neue Integrationen und Reparaturen

Beim Start und alle fünf Minuten prüft der Translator `custom_components`. Fehlt eine unterstützte Zielsprache, führt eine persistente Benachrichtigung unmittelbar zur passenden Phrasenliste. Existiert die Sprachdatei bereits, fehlen aber Schlüssel aus der Quellfassung, erscheint unter **Einstellungen → System → Reparaturen** ein Eintrag mit Anzahl und Link. Die Prüfung allein schreibt keine Sprachdateien und beauftragt keine Übersetzung.

## Original wiederherstellen oder Änderungen behalten

Vor dem ersten Eingriff sichert der Translator den exakten Inhalt einer vorhandenen Sprachdatei, zum Beispiel als `de.json.bak`. Eine zweite Kopie und der Bearbeitungsstand liegen unter `.storage/custom_integration_translator/`, außerhalb des von HACS aktualisierten Komponentenordners. Auch nach einer Wiederherstellung und einem weiteren Update bleibt die erste Entwicklerfassung dort zum Download erhalten. Nimm dieses Verzeichnis in deine Home-Assistant-Sicherungen auf.

**Original wiederherstellen** bringt die ursprünglichen Bytes zurück. Gab es ursprünglich keine Datei, erscheint **Erzeugte Datei löschen**. Erkennt der Translator inzwischen andere Dateiinhalte, sperrt er weitere Übersetzungen. Bei gesichertem Original kannst du es herunterladen oder ausdrücklich wiederherstellen. Bei dieser gezielten Wiederherstellung sichert er die zwischenzeitlich geänderte Datei zusätzlich als `de.json.<SHA256>.bak`. Ein fremdes Backup wird nie ersetzt.

Unter **Konfigurieren → Translator deaktivieren** kannst du vor der Deaktivierung alle verwalteten Änderungen zurücknehmen. Standardmäßig behältst du sie. Verwendest du direkt den nativen Deaktivieren- oder Entfernen-Befehl von Home Assistant, bleiben die Dateien ebenfalls erhalten. Solange Änderungen vorliegen, bietet anschließend ein Reparaturdialog dieselbe Entscheidung an. Triff diese Entscheidung, bevor du die Programmdateien des Translators über HACS deinstallierst. Bei einem Dateikonflikt stoppt die automatische Bereinigung und benennt die betroffene Datei.

## Entwicklung

Die Versionsnummer folgt `YYYY.MM.DD.BUILD`. Die DeepL-Anbindung in `provider.py` nutzt die HA-Aktionen `deepl_translator.get_languages` und `deepl_translator.translate_text`. Dateiverwaltung, Reparaturen und Oberfläche sind davon getrennt. Weitere Anbieter können dieselben Operationen für Sprachliste und Phrasenübersetzung implementieren.

[Apache License 2.0](LICENSE)
