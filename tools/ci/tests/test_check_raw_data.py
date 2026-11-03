import json
import subprocess
from pathlib import Path

from check_raw_data import find_problems

ALLOW = ["packages/*/tests/fixtures/synthetic/*"]
REPO = Path(__file__).resolve().parents[3]


def problems(paths: list[str], root: Path, allow: list[str] = ALLOW) -> list[str]:
    return find_problems(paths, allow, root)


def test_blocks_data_archives_and_weights_anywhere(tmp_path: Path) -> None:
    paths = [
        "bhavcopy.csv",
        "lake/nse/2026-11-03.parquet",
        "x/fo.DAT",
        "dump.csv.bz2",
        "research/kite_candles.json",
        "models/nifty50_lgbm.joblib",
        "weights/model.safetensors",
    ]
    assert len(problems(paths, tmp_path)) == len(paths)


def test_ignores_code_and_docs(tmp_path: Path) -> None:
    assert problems(["README.md", "src/a.py", "rates.toml", "ci.yml"], tmp_path) == []


def test_allows_synthetic_fixtures_only_where_listed(tmp_path: Path) -> None:
    ok = "packages/india-costs/tests/fixtures/synthetic/prices.csv"
    nested = "packages/india-costs/tests/fixtures/synthetic/deep/prices.parquet"
    elsewhere = "packages/india-costs/tests/fixtures/real/prices.csv"
    found = problems([ok, nested, elsewhere], tmp_path)
    assert found == [f"{elsewhere}: data, archive or model-weight file"]


def test_notebooks_must_be_saved_without_outputs(tmp_path: Path) -> None:
    def notebook(name: str, outputs: list[object]) -> str:
        cell = {"cell_type": "code", "source": "df", "outputs": outputs}
        (tmp_path / name).write_text(json.dumps({"cells": [cell]}))
        return name

    clean = notebook("clean.ipynb", [])
    dirty = notebook("eda.ipynb", [{"data": {"text/csv": "SYMBOL,CLOSE\nX,1\n"}}])
    assert problems([clean, dirty], tmp_path) == [
        "eda.ipynb: notebook saved with outputs (clear them first)"
    ]


def test_blocks_large_files(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_bytes(b"x" * 600_000)
    assert problems(["big.txt"], tmp_path) == ["big.txt: larger than 500 KB"]


def test_package_sources_are_not_gitignored() -> None:
    """An unanchored ignore rule once hid the bundled rate table from git."""
    sources = [
        str(p.relative_to(REPO))
        for p in (REPO / "packages").glob("*/src/**/*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    assert "packages/india-costs/src/india_costs/data/nse.toml" in sources
    ignored = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=REPO,
        input="\n".join(sources),
        capture_output=True,
        text=True,
    ).stdout.split()
    assert ignored == []
