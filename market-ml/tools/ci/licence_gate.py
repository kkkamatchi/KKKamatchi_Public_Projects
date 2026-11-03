"""Licence gate: block published artifacts whose inputs are not cleared for that use.

Every artifact that ships data-derived content (a dataset, model weights, published
metrics, or reference tables of facts) has a `provenance.toml` next to it. Each
input names a source from `licences/sources.toml`. The gate fails when:

- a source is unknown, denied (with no written permission on record) or still
  marked "verify";
- the artifact kind is not in the source's `allowed_kinds`;
- a share-alike source feeds an artifact under a different licence;
- an input has no `as_of` date;
- the registry or a provenance file has a misspelt key, or a registry licence looks
  share-alike but the entry does not set `share_alike`.

Usage: licence_gate.py [--registry PATH] [PROVENANCE ...]
(no files: every provenance.toml git would commit)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

KINDS = frozenset({"dataset", "weights", "metrics", "reference-facts"})
STATUSES = frozenset({"ok", "verify", "denied"})
PROJECT = Path(__file__).resolve().parents[2]
REGISTRY = PROJECT / "licences" / "sources.toml"
SOURCE_KEYS = frozenset({"id", "name", "url", "licence", "status", "allowed_kinds", "checked"})
SOURCE_KEYS |= {"share_alike", "permission_ref", "notes"}
PROVENANCE_KEYS = frozenset({"artifact", "kind", "licence", "inputs", "notes"})
INPUT_KEYS = frozenset({"source", "as_of", "url", "notes"})
LOOKS_SHARE_ALIKE = re.compile(r"\bSA\b|ShareAlike|share-alike|ODbL|\bGPL", re.IGNORECASE)


@dataclass(frozen=True)
class Source:
    id: str
    status: str
    allowed_kinds: frozenset[str]
    share_alike: str
    permission_ref: str
    reason: str


def load_registry(path: Path) -> tuple[dict[str, Source], list[str]]:
    data = tomllib.loads(path.read_text())
    sources: dict[str, Source] = {}
    errors: list[str] = []
    for i, raw in enumerate(data.get("source", [])):
        where = f"{path}: source #{i + 1}"
        missing = [k for k in ("id", "name", "url", "licence", "status") if not raw.get(k)]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
            continue
        sid = raw["id"]
        unknown = set(raw) - SOURCE_KEYS
        if unknown:
            errors.append(f"{where} ({sid}): unknown keys {sorted(unknown)}")
        if LOOKS_SHARE_ALIKE.search(raw["licence"]) and not raw.get("share_alike"):
            errors.append(f"{where} ({sid}): licence looks share-alike; set share_alike")
        if sid in sources:
            errors.append(f"{where}: duplicate id {sid!r}")
        if raw["status"] not in STATUSES:
            errors.append(f"{where} ({sid}): status must be one of {sorted(STATUSES)}")
        kinds = frozenset(raw.get("allowed_kinds", []))
        if kinds - KINDS:
            errors.append(f"{where} ({sid}): unknown kinds {sorted(kinds - KINDS)}")
        sources[sid] = Source(
            id=sid,
            status=raw["status"],
            allowed_kinds=kinds,
            share_alike=raw.get("share_alike", ""),
            permission_ref=raw.get("permission_ref", ""),
            reason=raw.get("notes", ""),
        )
    return sources, errors


def check_provenance(
    path: Path, doc: Mapping[str, Any], sources: Mapping[str, Source]
) -> list[str]:
    errors: list[str] = []
    unknown = set(doc) - PROVENANCE_KEYS
    if unknown:
        errors.append(f"{path}: unknown keys {sorted(unknown)}")
    kind = doc.get("kind", "")
    licence = str(doc.get("licence", ""))
    if kind not in KINDS:
        errors.append(f"{path}: kind must be one of {sorted(KINDS)}, got {kind!r}")
        return errors
    if not licence:
        errors.append(f"{path}: missing licence")
    inputs = doc.get("inputs", [])
    if not inputs:
        errors.append(f"{path}: no inputs declared")
    for item in inputs:
        sid = item.get("source", "")
        where = f"{path}: input {sid!r}"
        if set(item) - INPUT_KEYS:
            errors.append(f"{where}: unknown keys {sorted(set(item) - INPUT_KEYS)}")
        as_of = item.get("as_of")
        if not isinstance(as_of, date):
            errors.append(f"{where}: as_of must be a TOML date (YYYY-MM-DD)")
        src = sources.get(sid)
        if src is None:
            errors.append(f"{where}: not in {REGISTRY.relative_to(PROJECT)}")
            continue
        if src.status == "verify":
            errors.append(f"{where}: terms not yet verified; confirm them and set status = 'ok'")
        elif src.status == "denied" and not src.permission_ref:
            errors.append(f"{where}: denied without written permission ({src.reason})")
        if kind not in src.allowed_kinds:
            errors.append(f"{where}: may not feed a {kind!r} artifact")
        if src.share_alike and licence.lower() != src.share_alike.lower():
            errors.append(f"{where}: share-alike source requires licence {src.share_alike!r}")
    return errors


def provenance_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    names = (p for p in out.stdout.decode().split("\0") if p)
    return [root / p for p in names if Path(p).name == "provenance.toml"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args(argv)

    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    sources, errors = load_registry(args.registry or REGISTRY)
    for path in args.files or provenance_files(root):
        doc = tomllib.loads(path.read_text())
        errors.extend(check_provenance(path, doc, sources))
    if errors:
        print("Licence gate failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
