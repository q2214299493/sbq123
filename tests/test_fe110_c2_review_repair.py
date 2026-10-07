"""Exact chemistry, surface-aware duplicates and an unexecuted repair proposal."""
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

from archive.fe110_five_c2_adsorption_20261006.build_supplement import equivalent_rmsd
from archive.fe110_five_c2_adsorption_20261006.review_gpu_supplement import geometry
from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar
from scripts.aqcat25_handoff import validate_handoff
from scripts.artifact_io import sha256_file

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"


def test_relaxed_duplicate_comparison_preserves_real_height():
    path = BASE / "gpu_supplement_v1/01_extra1/output/job_2142/POSCAR"
    first = read_poscar(path)
    second = deepcopy(first)
    second.frac[45:, 2] += 0.30 / first.cell[2, 2]
    symmetry = [(np.eye(3), np.zeros(3))]
    assert equivalent_rmsd(first, second, symmetry) < 1e-12
    assert np.isclose(equivalent_rmsd(first, second, symmetry, remove_height_shift=False), 0.30)


@pytest.mark.parametrize("name,intact", [("01_extra1", True), ("02_extra1", True),
                                        ("02_extra2", True), ("03_extra1", True), ("03_extra2", False)])
def test_actual_returns_and_chemical_failure(name, intact):
    directory = BASE / "gpu_supplement_v1" / name
    output = directory / "output/job_2142"
    document = validate_handoff(output / "gpu_result_manifest.json", root=directory)
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert document["producer"]["gpu_job_id"] == "2142"
    assert document["producer_exit_record"]["exit_code"] == 0
    assert document["domain_assessment"]["status"] == "in_domain"
    assert result["converged"] and result["movable_fmax_eV_per_A"] <= 0.10
    assert document["result"]["predicted_force"]["fmax"] == result["movable_fmax_eV_per_A"]
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    frozen = read_poscar(BASE / "gpu_supplement_v1/01_extra1/POSCAR")
    slab = Poscar("clean Fe45 extracted from frozen input", frozen.cell, ["Fe"], [45],
                  frozen.frac[:45], frozen.flags[:45])
    actual = geometry(directory / "POSCAR", output / "POSCAR", slab, rules)
    assert actual["pass"] is intact
    if not intact:
        assert actual["chemistry"]["lost_bonds"] == [(0, 1)]
        assert actual["chemistry"]["dissociated"]


def test_live_vasp_match_is_not_energy_proven_duplicate():
    review = json.loads((BASE / "gpu_supplement_review_v1/review.json").read_text())
    item = next(r for r in review["records"] if r["name"] == "02_extra1")
    assert item["status"] == "GEOMETRIC_MATCH_EXISTING_VASP"
    assert not item["duplicates"]
    assert all(m["same_model_energy_difference_eV"] is None for m in item["VASP_geometry_matches"])
    assert not review["submit_gpu"] and not review["submit_vasp"] and not review["scientific_acceptance"]
    assert review["height_shift_removed_for_relaxed_duplicates"] is False


def test_repair_is_exact_intact_local_template_without_execution():
    review = json.loads((BASE / "supplement_repair_v1/repair_review.json").read_text(encoding="utf-8"))
    assert not review["gpu_submitted"] and not review["vasp_submitted"] and not review["scientific_acceptance"]
    assert review["recipe"]["anchor_global_0based"] == 46
    assert review["recipe"]["site"] == "short_bridge"
    assert review["geometry"]["verdict"] == "pass" and not review["geometry"]["warnings"]
    assert review["geometry"]["maximum_bond_length_change_angstrom"] < 1e-10
    assert min(review["symmetry_RMSD_A_height_removed_initial_seed_only"].values()) > 0.20
    assert sha256_file(ROOT / review["structure_path"]) == review["structure_sha256"]
    source = read_poscar(ROOT / review["source_path"])
    target = read_poscar(ROOT / review["structure_path"])
    assert source.symbols == target.symbols and source.counts == target.counts
    assert target.flags[:18] == [("F", "F", "F")]*18
    assert target.flags[18:] == [("T", "T", "T")]*31
