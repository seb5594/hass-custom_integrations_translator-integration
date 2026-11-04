"""Read HA translation dictionaries and commit edits with a recoverable ownership journal."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


class CatalogError(ValueError):
    """An operation needs user attention."""


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def unique_keys(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise CatalogError("Duplicate JSON key")
    return result


def dictionary(raw):
    result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_keys)
    if not isinstance(result, dict):
        raise CatalogError("Expected a JSON object")
    return result


def safe(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise CatalogError(f"Linked path: {path.name}")
    return path


def read(path):
    try:
        return safe(path).read_bytes()
    except FileNotFoundError:
        return None


def publish(path, raw, *, exclusive=False):
    """Publish a complete file in the same filesystem. Never replace an existing backup."""
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        staged = Path(temp.name)
    try:
        with staged.open("wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if exclusive:
            os.link(staged, path)
        else:
            os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def phrases(tree, path=()):
    for key, value in tree.items():
        child = (*path, key)
        if isinstance(value, dict):
            yield from phrases(value, child)
        elif isinstance(value, str) and value.strip():
            yield child, value


def stamp(path):
    try:
        stat = safe(path).stat()
    except FileNotFoundError:
        return None
    return [stat.st_dev, stat.st_ino, stat.st_mtime_ns]


def externally_changed(state, path, raw):
    return digest(raw) != state["last"] or (
        state.get("stamp") is not None and state["stamp"] != stamp(path)
    )


def initial_path(journal):
    return safe(safe(journal.parent / "originals") / journal.name)


def preserve_original(journal, original):
    if original is None:
        return
    archive = initial_path(journal)
    first = read(archive)
    if first is not None and first != original:
        archive = safe(archive.with_name(f"{archive.stem}.{digest(original)}.json"))
    existing = read(archive)
    if existing is None:
        publish(archive, original, exclusive=True)
    elif existing != original:
        raise CatalogError("Original archive conflicts with existing file")


def key_id(path):
    return json.dumps(path, ensure_ascii=False, separators=(",", ":"))


class Catalog:
    def __init__(self, config):
        self.root = Path(config) / "custom_components"
        self.storage = Path(config) / ".storage" / "custom_integration_translator"

    def paths(self, domain, language):
        if not re.fullmatch(r"[a-z0-9_]+", domain) or not re.fullmatch(
            r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language
        ):
            raise CatalogError("Invalid integration or language key")
        folder = safe(safe(self.root) / domain)
        translations = safe(folder / "translations")
        target = safe(translations / f"{language}.json")
        backup = safe(translations / f"{language}.json.bak")
        safe(self.storage.parent)
        journal = safe(safe(safe(self.storage) / domain) / f"{language}.json")
        return folder, target, backup, journal

    def state(self, journal, raw):
        stored = read(journal)
        if stored is None:
            return None
        state = dictionary(stored)
        pending = state.pop("pending", None)
        if pending and digest(raw) == pending["last"]:
            state.update(pending)
        return state

    def detail(self, domain, language):
        folder, target, backup, journal = self.paths(domain, language)
        manifest = dictionary(safe(folder / "manifest.json").read_bytes())
        raw = read(target)
        state = self.state(journal, raw)
        conflict = bool(state and externally_changed(state, target, raw))
        try:
            current = dictionary(raw) if raw is not None else {}
        except ValueError:
            if not conflict:
                raise
            current = {}
        if not state and backup.exists() and read(backup) != raw:
            conflict = True
        source = None
        source_lang = None
        candidates = []
        if language != "en":
            candidates.extend(
                [(target.parent / "en.json", "en"), (folder / "strings.json", "en")]
            )
        candidates.extend(
            (p, p.stem)
            for p in sorted(target.parent.glob("*.json"))
            if p != target and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", p.stem)
        )
        if language == "en":
            candidates.append((folder / "strings.json", "en"))
        for candidate, code in candidates:
            data = read(candidate)
            if data is not None and candidate.parent == target.parent:
                # A generated language must never become the source for another translation.
                source_state = self.state(self.paths(domain, code)[3], data)
                if source_state and not externally_changed(
                    source_state, candidate, data
                ):
                    data = self.original(source_state)
            if data is not None and list(phrases(dictionary(data))):
                source, source_lang = data, code
                break
        values = dict(phrases(current))
        generated = set(state["keys"]) if state and not conflict else set()
        rows = [
            {
                "path": list(path),
                "source": text,
                "target": values.get(path),
                "generated": key_id(path) in generated,
            }
            for path, text in phrases(dictionary(source) if source is not None else {})
        ]
        return {
            "domain": domain,
            "name": manifest.get("name", domain),
            "language": language,
            "source_language": source_lang,
            "exists": raw is not None,
            "managed": state is not None,
            "original": state is not None and state["original"] is not None,
            "initial_available": initial_path(journal).is_file(),
            "conflict": conflict,
            "missing": sum(row["target"] is None for row in rows),
            "count": len(rows),
            "rows": rows,
            "target_hash": digest(raw),
            "revision": digest(
                encode(
                    [
                        source_lang,
                        digest(source),
                        digest(raw),
                        stamp(target),
                        digest(read(journal)),
                    ]
                )
            ),
        }

    def scan(self, language):
        items = []
        for folder in sorted(safe(self.root).iterdir()):
            if folder.name.startswith(".") or not (folder / "manifest.json").is_file():
                continue
            try:
                item = self.detail(folder.name, language)
                del item["rows"]
            except (OSError, ValueError, KeyError) as err:
                item = {
                    "name": folder.name,
                    "domain": folder.name,
                    "error": str(err),
                    "missing": 0,
                }
            items.append(item)
        return sorted(
            items,
            key=lambda item: (
                not item["missing"],
                item["name"].casefold(),
                item["domain"],
            ),
        )

    @staticmethod
    def original(state):
        data = state["original"]
        raw = base64.b64decode(data, validate=True) if data is not None else None
        if digest(raw) != state["original_hash"]:
            raise CatalogError("Damaged original in recovery journal")
        return raw

    def save(self, domain, language, revision, changes):
        detail = self.detail(domain, language)
        if detail["conflict"] or detail["revision"] != revision:
            raise CatalogError("Files changed. Open the integration again.")
        if not changes or not changes.keys() <= {
            tuple(row["path"]) for row in detail["rows"]
        }:
            raise CatalogError("Invalid phrase selection")
        _, target, backup, journal = self.paths(domain, language)
        raw = read(target)
        if digest(raw) != detail["target_hash"]:
            raise CatalogError("Target changed")
        tree = dictionary(raw) if raw is not None else {}
        state = self.state(journal, raw)
        if state is None:
            state = {
                "original": base64.b64encode(raw).decode() if raw is not None else None,
                "original_hash": digest(raw),
                "last": digest(raw),
                "keys": [],
            }
        if externally_changed(state, target, raw):
            raise CatalogError("Target changed")
        original = self.original(state)
        existing_backup = read(backup)
        if existing_backup is not None and existing_backup != original:
            raise CatalogError("Backup belongs to a different file")
        for path, value in changes.items():
            parent = tree
            for key in path[:-1]:
                parent = parent.setdefault(key, {})
                if not isinstance(parent, dict):
                    raise CatalogError(
                        "Source and target have conflicting JSON structures"
                    )
            if path[-1] in parent and not isinstance(parent[path[-1]], str):
                raise CatalogError("Source and target have conflicting JSON structures")
            parent[path[-1]] = value
        result = encode(tree)
        pending = {
            "last": digest(result),
            "stamp": None,
            "keys": sorted(set(state["keys"]) | {key_id(p) for p in changes}),
        }
        preserve_original(journal, original)
        if original is not None and existing_backup is None:
            publish(backup, original, exclusive=True)
        publish(journal, encode({**state, "pending": pending}))
        if read(target) != raw:
            raise CatalogError("Target changed during translation")
        publish(target, result, exclusive=raw is None)
        publish(journal, encode({**state, **pending, "stamp": stamp(target)}))

    def restore(self, domain, language, revision=None):
        folder, target, backup, journal = self.paths(domain, language)
        raw = read(target)
        state = self.state(journal, raw)
        if state is None:
            raise CatalogError("No managed translation")
        original = self.original(state)
        if not (folder / "manifest.json").is_file():
            raise CatalogError("Integration is no longer installed")
        if raw == original:
            journal.unlink()
            return
        if externally_changed(state, target, raw):
            # Only an explicit per-file decision may restore across a HACS/user edit.
            if (
                original is None
                or revision is None
                or self.detail(domain, language)["revision"] != revision
            ):
                raise CatalogError(
                    "External change detected. Review this file in the workspace."
                )
            if raw is not None:
                archive = target.with_suffix(f".json.{digest(raw)}.bak")
                copy = read(archive)
                if copy is None:
                    publish(archive, raw, exclusive=True)
                elif copy != raw:
                    raise CatalogError(
                        "The recovery archive already belongs to another file"
                    )
        if original is None and backup.exists():
            raise CatalogError("An unowned backup exists. No file was deleted.")
        if read(target) != raw:
            raise CatalogError("Target changed during recovery")
        if original is None:
            target.unlink()
        else:
            publish(target, original)
        journal.unlink()

    def restore_all(self):
        for domain, language in self.managed():
            try:
                self.restore(domain, language)
            except (OSError, ValueError) as err:
                raise CatalogError(
                    f"{domain}/translations/{language}.json: {err}"
                ) from err

    def managed(self):
        return [
            (p.parent.name, p.stem) for p in sorted(safe(self.storage).glob("*/*.json"))
        ]
