from __future__ import annotations

import json
from pathlib import Path

from scripts.adsorption.build_fe110_c2_coads import build, build_missing
from scripts.adsorption.c2_coads_catalog import CANDIDATE_SITE_LABELS


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "adsorption" / "build_fe110_c2_coads.py"
LABEL_CATALOG = ROOT / "scripts" / "adsorption" / "c2_coads_catalog.py"
CURRENT_STATE = ROOT / "docs" / "02_CURRENT_STATE.md"
SLAB = ROOT / "calculations" / "true_fe110_clean_20260629" / "POSCAR"

EXPECTED_SITE_LABELS = {
    "CplusO_C-lb_O-h_adj": "C*+O*/C@lb+O@h_adj",
    "C2O_kappa-Calpha_lb_tilted": "C₂O*/κ-Cα/lb_tilted",
    "C2O_eta2CalphaCbeta_h-lb-h": "C₂O**/η²(Cα,Cβ)/h-lb-h",
    "C2_eta2CC_h-lb-h": "C₂**/η²(C,C)/h-lb-h",
    "C2plusO_eta2CC_h-lb-h_O-lb_adj": "C₂**/η²(C,C)/h-lb-h+O@lb_adj",
    "CplusO_C-lb_O-lb-adj": "C*+O*/C@lb+O@lb/adj",
    "C2O_eta2CalphaCbeta_C2-2-derived": "C₂O**/η²-CαCβ/C₂-2-derived",
    "C2_eta2CC_C2-2-diagonal": "C₂**/η²-CC/C₂-2-diagonal",
    "C2plusO_C2-1_O-h-adj": "C₂**/C₂-1+O@h/adj",
    "C2plusO_C2-2-diagonal_O-lb-adj": "C₂**/C₂-2-diagonal+O@lb/adj",
    "C2plusO_C2-2-diagonal_O-h-adj": "C₂**/C₂-2-diagonal+O@h/adj",
}

MOJIBAKE_MARKERS = ("鈷侽", "鈷?", "魏-C伪", "畏虏", "C尾")


def test_c2_coads_builder_source_and_labels_are_utf8() -> None:
    sources = [path.read_bytes().decode("utf-8", errors="strict") for path in (BUILDER, LABEL_CATALOG, CURRENT_STATE)]

    assert not any(marker in source for source in sources for marker in MOJIBAKE_MARKERS)
    assert CANDIDATE_SITE_LABELS == EXPECTED_SITE_LABELS
    assert all(label in sources[-1] for label in EXPECTED_SITE_LABELS.values())


def test_c2_coads_manifests_preserve_utf8_site_labels(tmp_path: Path) -> None:
    initial = build(SLAB, tmp_path / "initial")
    missing = build_missing(SLAB, tmp_path / "missing")

    for candidate_set, manifest in (("initial", initial), ("missing", missing)):
        manifest_path = tmp_path / candidate_set / "candidate_manifest.json"
        raw = manifest_path.read_bytes()
        decoded = raw.decode("utf-8", errors="strict")
        loaded = json.loads(decoded)

        assert loaded == manifest
        assert {
            candidate["name"]: candidate["site_label"] for candidate in loaded["candidates"]
        } == {
            candidate["name"]: EXPECTED_SITE_LABELS[candidate["name"]]
            for candidate in loaded["candidates"]
        }
        for candidate in loaded["candidates"]:
            assert candidate["site_label"] in decoded
        assert not any(marker in decoded for marker in MOJIBAKE_MARKERS)
