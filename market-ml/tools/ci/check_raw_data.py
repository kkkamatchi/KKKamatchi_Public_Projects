"""Fail if data files, model weights or oversized files are tracked in this repository.

Market data from exchanges, brokers and most vendors may not be redistributed, and
model weights are published to Hugging Face behind the licence gate, never committed
(see DATA_POLICY.md). This catches the common accidents:

- a data, archive or model-weight suffix anywhere in the name (so `.csv.bz2` counts);
- a Jupyter notebook saved with outputs, which can embed data tables;
- any file over 500 KB.

Paths matching a glob in the repository root's `.raw-data-allow` (synthetic fixtures)
are exempt. Checks cover the whole repository, not just this project.

Usage: check_raw_data.py [FILE ...]   (no files: check everything git would commit)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

DATA = {".parquet", ".pq", ".csv", ".tsv", ".feather", ".arrow", ".ipc", ".orc", ".avro"}
DATA |= {".json", ".jsonl", ".ndjson", ".dat", ".h5", ".hdf5", ".pkl", ".pickle", ".npy"}
DATA |= {".npz", ".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".duckdb", ".db", ".sqlite"}
DATA |= {".sqlite3"}
ARCHIVES = {".zip", ".gz", ".bz2", ".xz", ".zst", ".lz4", ".7z", ".rar", ".tar", ".tgz"}
WEIGHTS = {".joblib", ".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".bin", ".pb", ".gguf"}
WEIGHTS |= {".keras", ".cbm", ".ubj"}
BLOCKED_SUFFIXES = frozenset(DATA | ARCHIVES | WEIGHTS)
MAX_BYTES = 500_000
ALLOW_FILE = ".raw-data-allow"


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip())


def candidate_files(root: Path) -> list[str]:
    """Tracked files plus untracked files that are not ignored."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [p for p in out.stdout.decode().split("\0") if p]


def load_allow_patterns(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _notebook_has_outputs(path: Path) -> bool:
    try:
        cells = json.loads(path.read_text(encoding="utf-8")).get("cells", [])
    except (ValueError, UnicodeDecodeError, AttributeError):
        return True  # unreadable: let a human look
    return any(cell.get("outputs") for cell in cells if isinstance(cell, dict))


def find_problems(paths: Iterable[str], allow_patterns: Sequence[str], root: Path) -> list[str]:
    problems = []
    for raw in sorted(set(paths)):
        path = PurePosixPath(raw)
        if any(fnmatchcase(str(path), pattern) for pattern in allow_patterns):
            continue
        if {s.lower() for s in path.suffixes} & BLOCKED_SUFFIXES:
            problems.append(f"{path}: data, archive or model-weight file")
        full = root / path
        if not full.is_file():
            continue
        if full.stat().st_size > MAX_BYTES:
            problems.append(f"{path}: larger than {MAX_BYTES // 1000} KB")
        if path.suffix.lower() == ".ipynb" and _notebook_has_outputs(full):
            problems.append(f"{path}: notebook saved with outputs (clear them first)")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="repo-relative paths (default: all candidates)")
    args = parser.parse_args(argv)

    root = repo_root()
    paths = args.files or candidate_files(root)
    problems = find_problems(paths, load_allow_patterns(root / ALLOW_FILE), root)
    if problems:
        print("Blocked from the repo (see DATA_POLICY.md):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"Synthetic fixtures go under a path listed in {ALLOW_FILE}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
