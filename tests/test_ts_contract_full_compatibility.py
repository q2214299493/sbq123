"""Retain complete registered scientific compatibility in TS contracts."""

from copy import deepcopy

import pytest

from scripts.artifact_io import sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.contract import load_contract, normalize_contract


def _payload():
    return {
        "reaction_id": "fixture_c_c_coupling",
        "reaction_family": "co_insertion",
        "reactant_id": "ch_plus_co",
        "product_id": "chco",
        "index_base": 0,
        "atom_map": [[0, 0], [1, 1], [2, 2]],
        "atom_symbols": ["Fe", "C", "C"],
        "reaction_atoms": [1, 2],
        "broken_bonds": [],
        "formed_bonds": [[1, 2]],
        "site_changes": [],
        "endpoints": {
            name: {
                "calculation_id": name,
                "structure_file_id": name + "_structure",
                "static_result_id": name + "_energy",
            }
            for name in ("initial", "final")
        },
        "compatibility": {
            "material": "fe", "surface": "fe110", "branch": "fixture",
            "slab_model": "fixture_fe_fixed", "xc": "pbe",
            "potcar_family": "paw_pbe", "encut_ev": 400.0,
            "kmesh": [5, 5, 1], "magnetic_state": "ispin2_Fe2p2_adsorbate0_seed",
            "coverage": "3x3_one_C2HO", "ismear": 1, "sigma_ev": 0.2,
            "fixed_atom_indices_zero_based": [0], "ldipol": False,
            "vacuum_thickness_angstrom": 15.0,
            "final_energy_convention": "fe110_converged_toten_sigma0p20_v1",
            "cell_angstrom": [[8.0, 0.0, 0.0], [4.0, 6.0, 0.0], [0.0, 0.0, 23.0]],
            "slab_layers": 5,
            "clean_slab_sha256": "a" * 64,
            "potcar_bundle_sha256": "b" * 64,
            "ediff_ev": 1e-5,
            "force_threshold_ev_per_A": 0.02,
        },
    }


def test_contract_preserves_full_registry_compatibility_fingerprint():
    payload = _payload()
    original = deepcopy(payload)
    normalized = normalize_contract(payload)
    assert payload == original
    assert normalized["compatibility"] == payload["compatibility"]
    assert normalized["compatibility_sha256"] == sha256_json(payload["compatibility"])
    assert normalize_contract(normalized) == normalized


def test_json_contract_exponent_floats_preserve_hashes_on_disk(tmp_path):
    normalized = normalize_contract(_payload())
    path = tmp_path / "contract.json"
    write_json_exclusive(path, normalized)
    # YAML 1.1 can interpret JSON's 1e-05 as text; a JSON contract must not.
    assert load_contract(path) == normalized


@pytest.mark.parametrize("field,value", [
    ("clean_slab_sha256", "c" * 64),
    ("potcar_bundle_sha256", "d" * 64),
    ("ediff_ev", 1e-6),
    ("slab_layers", 4),
])
def test_extra_scientific_field_changes_are_hash_bound(field, value):
    payload = _payload()
    baseline = normalize_contract(payload)
    payload["compatibility"][field] = value
    assert normalize_contract(payload)["compatibility_sha256"] != baseline["compatibility_sha256"]


def test_extra_scientific_metadata_cannot_contain_nonfinite_values():
    payload = _payload()
    payload["compatibility"]["cell_angstrom"][0][0] = float("nan")
    with pytest.raises(ValueError):
        normalize_contract(payload)
