from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.adsorption.preflight_fe110_adsorption import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation


def _write_poscar(path: Path, hydrogen_count: int) -> None:
    coordinates = (
        ["0 0 0 F F F"] * 18
        + ["0 0 0 T T T"] * 27
        + ["0.2 0.2 0.6 T T T"]
        + ["0.3 0.3 0.6 T T T"] * hydrogen_count
    )
    text = (
        "Fe45 C H\n"
        "1.0\n"
        "10 0 0\n"
        "0 10 0\n"
        "0 0 20\n"
        "Fe C H\n"
        f"45 1 {hydrogen_count}\n"
        "Selective dynamics\n"
        "Direct\n"
        + "\n".join(coordinates)
        + "\n"
    )
    path.write_text(text, encoding="ascii")


@pytest.mark.parametrize("hydrogen_count", [1, 2])
def test_preflight_accepts_supported_c_h_adsorption_compositions(
    tmp_path: Path, hydrogen_count: int
) -> None:
    _write_poscar(tmp_path / "POSCAR", hydrogen_count)
    build_fe110_adsorption_relaxation(tmp_path)
    (tmp_path / "candidate_manifest.json").write_text(
        json.dumps({"candidate": "test"}) + "\n", encoding="utf-8"
    )
    report = preflight(tmp_path)
    assert report["passed"] is True
    assert report["structure"]["counts"] == [45, 1, hydrogen_count]


def test_preflight_rejects_unsupported_hydrogen_count(tmp_path: Path) -> None:
    _write_poscar(tmp_path / "POSCAR", 3)
    build_fe110_adsorption_relaxation(tmp_path)
    (tmp_path / "candidate_manifest.json").write_text(
        json.dumps({"candidate": "test"}) + "\n", encoding="utf-8"
    )
    report = preflight(tmp_path)
    assert report["passed"] is False
    assert "POSCAR_COMPOSITION_OR_ORDER_MISMATCH" in report["errors"]


def test_preflight_accepts_c2ho_h_endpoint_composition(tmp_path: Path) -> None:
    coordinates = (
        ["0 0 0 F F F"] * 18
        + ["0 0 0 T T T"] * 27
        + ["0.2 0.2 0.6 T T T"] * 2
        + ["0.3 0.3 0.6 T T T"]
        + ["0.4 0.4 0.6 T T T"] * 2
    )
    (tmp_path / "POSCAR").write_text(
        "Fe45 C2 O H2\n"
        "1.0\n"
        "10 0 0\n"
        "0 10 0\n"
        "0 0 20\n"
        "Fe C O H\n"
        "45 2 1 2\n"
        "Selective dynamics\n"
        "Direct\n"
        + "\n".join(coordinates)
        + "\n",
        encoding="ascii",
    )
    build_fe110_adsorption_relaxation(tmp_path)
    (tmp_path / "candidate_manifest.json").write_text(
        json.dumps({"candidate": "test"}) + "\n", encoding="utf-8"
    )
    report = preflight(tmp_path)
    assert report["passed"] is True
    assert report["structure"]["counts"] == [45, 2, 1, 2]
