import tomllib
from pathlib import Path

import pytest

from licence_gate import check_provenance, load_registry

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "licences" / "sources.toml"


@pytest.fixture(scope="module")
def sources() -> dict:
    loaded, errors = load_registry(REGISTRY)
    assert errors == []
    return loaded


def provenance(kind: str, licence: str, *sources: str) -> dict:
    doc = f'artifact = "x"\nkind = "{kind}"\nlicence = "{licence}"\n'
    for sid in sources:
        doc += f'[[inputs]]\nsource = "{sid}"\nas_of = 2026-11-03\n'
    return tomllib.loads(doc)


def errors_for(sources: dict, doc: dict) -> list[str]:
    return check_provenance(Path("provenance.toml"), doc, sources)


def test_cleared_source_passes(sources: dict) -> None:
    assert errors_for(sources, provenance("weights", "Apache-2.0", "ecb-reference-rates")) == []


def test_nse_market_data_blocked_without_permission(sources: dict) -> None:
    errors = errors_for(sources, provenance("metrics", "Apache-2.0", "nse-market-data"))
    assert any("denied without written permission" in e for e in errors)


def test_nse_circulars_only_feed_reference_facts(sources: dict) -> None:
    assert errors_for(sources, provenance("reference-facts", "Apache-2.0", "nse-circulars")) == []
    errors = errors_for(sources, provenance("dataset", "Apache-2.0", "nse-circulars"))
    assert any("may not feed a 'dataset'" in e for e in errors)


def test_unverified_source_blocked(sources: dict) -> None:
    errors = errors_for(sources, provenance("dataset", "Apache-2.0", "fed-h10"))
    assert any("not yet verified" in e for e in errors)


def test_share_alike_licence_enforced(sources: dict) -> None:
    bad = errors_for(sources, provenance("weights", "Apache-2.0", "binance-vision"))
    assert any("share-alike" in e for e in bad)
    assert errors_for(sources, provenance("weights", "cc-by-nc-sa-4.0", "binance-vision")) == []


def test_unknown_source_and_missing_date(sources: dict) -> None:
    doc = tomllib.loads('kind = "dataset"\nlicence = "MIT"\n[[inputs]]\nsource = "nope"\n')
    errors = errors_for(sources, doc)
    assert any("as_of" in e for e in errors)
    assert any("not in" in e for e in errors)


def test_fred_denied_for_training(sources: dict) -> None:
    errors = errors_for(sources, provenance("weights", "Apache-2.0", "fred"))
    assert any("denied" in e for e in errors)


def test_registry_rejects_bad_entries(tmp_path: Path) -> None:
    bad = tmp_path / "sources.toml"
    bad.write_text(
        '[[source]]\nid = "a"\nname = "A"\nurl = "u"\nlicence = "l"\nstatus = "maybe"\n'
        '[[source]]\nid = "a"\nname = "A"\nurl = "u"\nlicence = "l"\nstatus = "ok"\n'
        'allowed_kinds = ["vibes"]\n'
        '[[source]]\nid = "b"\n'
    )
    _, errors = load_registry(bad)
    assert len(errors) == 4


def test_registry_catches_misspelt_share_alike(tmp_path: Path) -> None:
    bad = tmp_path / "sources.toml"
    bad.write_text(
        '[[source]]\nid = "wb"\nname = "W"\nurl = "u"\nlicence = "CC BY-SA 4.0"\n'
        'status = "ok"\nallowed_kinds = ["weights"]\nshare-alike = "cc-by-sa-4.0"\n'
    )
    _, errors = load_registry(bad)
    assert any("unknown keys ['share-alike']" in e for e in errors)
    assert any("looks share-alike" in e for e in errors)


def test_provenance_catches_misspelt_keys(sources: dict) -> None:
    doc = provenance("dataset", "Apache-2.0", "ecb-reference-rates")
    doc["licnece"] = "MIT"
    doc["inputs"][0]["asof"] = "2026-11-03"
    errors = errors_for(sources, doc)
    assert any("unknown keys ['licnece']" in e for e in errors)
    assert any("unknown keys ['asof']" in e for e in errors)
