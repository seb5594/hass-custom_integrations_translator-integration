"""Ownership, interrupted writes and source selection in a disposable HA config."""

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

MODULE = (
    Path(__file__).resolve().parents[2]
    / "custom_components/custom_integration_translator/catalog.py"
)
SPEC = importlib.util.spec_from_file_location("translator_catalog", MODULE)
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class TranslationFiles(unittest.TestCase):
    def setUp(self):
        config = TemporaryDirectory()
        self.addCleanup(config.cleanup)
        self.catalog = catalog.Catalog(config.name)
        self.folder = Path(config.name) / "custom_components" / "example"
        self.tr = self.folder / "translations"
        self.tr.mkdir(parents=True)
        (self.folder / "manifest.json").write_text('{"name":"Example"}')
        (self.tr / "en.json").write_text('{"nested":{"a.b":"Open","a":"Close"}}')
        self.target = self.tr / "de.json"
        self.backup = self.tr / "de.json.bak"
        self.original = (
            b'\xef\xbb\xbf{\r\n "nested": {"a": "Zu"}, "unrelated": "OK"\r\n}\r\n'
        )

    def detail(self):
        return self.catalog.detail("example", "de")

    def save(self, changes):
        self.catalog.save("example", "de", self.detail()["revision"], changes)

    def restore(self):
        self.catalog.restore("example", "de")

    def test_partial_repeat_and_exact_restoration(self):
        self.target.write_bytes(self.original)
        self.save({("nested", "a.b"): "Auf"})
        item = self.detail()
        self.assertEqual(item["missing"], 0)
        self.assertEqual([row["generated"] for row in item["rows"]], [True, False])
        self.save({("nested", "a"): "Schließen"})
        self.assertEqual(
            json.loads(self.target.read_text(encoding="utf-8"))["unrelated"], "OK"
        )
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.backup.unlink()  # HACS may replace the component directory on update.
        self.restore()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.catalog.managed(), [])

    def test_generated_only_is_removed(self):
        self.save({("nested", "a"): "Zu"})
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.detail()["missing"], 1)
        self.restore()
        self.assertFalse(self.target.exists())

    def test_stale_editor_and_external_update(self):
        revision = self.detail()["revision"]
        self.target.write_bytes(self.original)
        with self.assertRaises(catalog.CatalogError):
            self.catalog.save("example", "de", revision, {("nested", "a"): "Zu"})
        self.save({("nested", "a"): "Geändert"})
        self.target.write_bytes(b'{"replacement":"new upstream release"}')
        self.assertTrue(self.detail()["conflict"])
        with self.assertRaises(catalog.CatalogError):
            self.restore()
        self.assertEqual(self.backup.read_bytes(), self.original)
        newer = self.target.read_bytes()
        self.catalog.restore("example", "de", self.detail()["revision"])
        self.assertEqual(self.target.read_bytes(), self.original)
        archive = self.tr / f"de.json.{catalog.digest(newer)}.bak"
        self.assertEqual(archive.read_bytes(), newer)

    def test_reinstalled_identical_developer_file_is_never_deleted(self):
        self.save({("nested", "a"): "Zu"})
        replacement = self.tr / "reinstalled.tmp"
        replacement.write_bytes(self.target.read_bytes())
        replacement.replace(self.target)
        self.assertTrue(self.detail()["conflict"])
        with self.assertRaises(catalog.CatalogError):
            self.restore()
        self.assertTrue(self.target.is_file())

    def test_initial_developer_file_survives_restore_and_later_release(self):
        self.target.write_bytes(self.original)
        self.save({("nested", "a"): "Erste Änderung"})
        self.restore()
        self.backup.unlink()
        self.target.write_bytes(b'{"nested":{"a":"new upstream"}}')
        self.save({("nested", "a"): "Zweite Änderung"})
        journal = self.catalog.paths("example", "de")[3]
        self.assertEqual(catalog.initial_path(journal).read_bytes(), self.original)

    def test_unowned_backup_blocks_edit(self):
        self.backup.write_bytes(b"other developer file")
        with self.assertRaises(catalog.CatalogError):
            self.save({("nested", "a"): "Zu"})
        self.assertFalse(self.target.exists())

    def test_recover_after_target_publish_before_journal_commit(self):
        self.target.write_bytes(self.original)
        publish = catalog.publish

        def interrupt(path, raw, **kwargs):
            if (
                path == self.catalog.paths("example", "de")[3]
                and b'"pending"' not in raw
            ):
                raise OSError("interrupted")
            publish(path, raw, **kwargs)

        with patch.object(catalog, "publish", interrupt), self.assertRaises(OSError):
            self.save({("nested", "a"): "Geschlossen"})
        self.restore()
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_fallback_and_unsafe_paths(self):
        (self.tr / "en.json").unlink()
        (self.folder / "strings.json").write_text('{"a":"English"}')
        (self.tr / "fr.json").write_text('{"a":"Français"}', encoding="utf-8")
        self.assertEqual(self.detail()["source_language"], "en")
        (self.folder / "strings.json").unlink()
        self.assertEqual(self.detail()["source_language"], "fr")
        for domain, language in (("../escape", "de"), ("example", "../outside")):
            with self.assertRaises(catalog.CatalogError):
                self.catalog.detail(domain, language)

    def test_scan_matches_editor_and_observes_file_changes(self):
        def check():
            item = self.catalog.scan("de")[0]
            detail = self.detail()
            self.assertEqual(
                item,
                {
                    key: value
                    for key, value in detail.items()
                    if key not in ("rows", "revision", "target_hash")
                },
            )
            return item

        self.assertEqual(check()["missing"], 2)
        self.target.write_bytes(self.original)
        self.assertEqual(check()["missing"], 1)
        self.save({("nested", "a.b"): "Auf"})
        self.assertEqual(check()["missing"], 0)
        self.target.write_bytes(b'{"nested":{"a":"Developer update"}}')
        self.assertTrue(check()["conflict"])
        self.assertEqual(check()["missing"], 1)
        self.catalog.restore("example", "de", self.detail()["revision"])
        self.assertEqual(check()["missing"], 1)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_fallback_skips_generated_only_source(self):
        (self.tr / "en.json").unlink()
        (self.tr / "fr.json").write_text('{"one":"Ouvrir"}')
        detail = self.catalog.detail("example", "it")
        self.catalog.save("example", "it", detail["revision"], {("one",): "Aprire"})
        (self.tr / "fr.json").unlink()
        self.assertEqual(self.catalog.scan("de")[0]["count"], 0)
        (self.folder / "strings.json").write_text('{"one":"Open"}')
        self.assertEqual(self.catalog.scan("de")[0]["source_language"], "en")
