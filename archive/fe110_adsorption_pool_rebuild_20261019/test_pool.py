import json
import hashlib

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms

from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import selected_steps as prior_steps
from archive.fe110_adsorption_pool_rebuild_20261019 import prepare_pool
from archive.fe110_adsorption_pool_rebuild_20261019.prepare_pool import collapse_redundant, cross_partition_pairs, reader_source, selected_steps
from archive.fe110_adsorption_pool_rebuild_20261019.roles import ROLE_WEIGHTS, atom_weights, grouped_vector_loss, pose_distance, pose_variants, role_groups
from scripts.adsorption.build_fe110_adsorption import Poscar


@pytest.mark.parametrize("total", [5, 95, 131, 198, 300])
def test_expansion_preserves_previous24_sampling(total):
    selected = selected_steps(total)
    assert set(prior_steps(total)) <= set(selected)
    assert selected == sorted(set(selected))
    assert min(selected) == 1 and max(selected) == total
    assert len(selected) <= 26


def test_v1_success_reused_only_with_original_reader_and_payload_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_pool, "DEST", tmp_path)
    record = {"name": "fixture", "atom_count": 50}
    folder = tmp_path / "raw/fixture"
    folder.mkdir(parents=True)
    payload = b"source bytes preserved"
    (folder / "source.json").write_bytes(payload)
    receipt = {"exit_code": 0, "reader_sha256": hashlib.sha256(reader_source(record, 1).encode()).hexdigest(),
               "output_sha256": hashlib.sha256(payload).hexdigest()}
    (folder / "receipt.json").write_text(json.dumps(receipt))
    assert prepare_pool.verified_collection(record) == folder
    assert prepare_pool.collect_one(record)["status"] == "REUSED_VERIFIED_COLLECTION"
    assert not (folder / "attempt_v2").exists()
    (folder / "source.json").write_bytes(payload + b"tampered")
    with pytest.raises(ValueError, match="binding changed"):
        prepare_pool.verified_collection(record)


def test_failed_v2_is_preserved_not_automatically_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_pool, "DEST", tmp_path)
    folder = tmp_path / "raw/fixture/attempt_v2"
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_text(json.dumps({"exit_code": 124}))
    with pytest.raises(FileExistsError, match="preserved v2 attempt"):
        prepare_pool.collect_one({"name": "fixture", "atom_count": 50})


def test_prior_replay_energy_alias_preserves_original_value():
    row = {"energy_eV_force_label_only": -366.87875155}
    prepare_pool.normalize_energy_metadata(row)
    assert row["toten_eV_force_label_only"] == row["energy_eV_force_label_only"] == -366.87875155
    with pytest.raises(ValueError, match="inconsistent"):
        prepare_pool.normalize_energy_metadata({"energy_eV_force_label_only": -1., "final_toten_eV": -2.})


def test_replay_source_falls_back_to_real_calculation_group():
    assert prepare_pool.source_name({"calculation_group": "legacy_vasp_ch_top"}) == "legacy_vasp_ch_top"
    assert prepare_pool.source_name({"source_name": "06_C", "calculation_group": "current_vasp_job_9848801"}) == "06_C"


@pytest.mark.parametrize("converged", [True, False])
def test_closed_trajectory_force_labels_do_not_require_final_ionic_convergence(tmp_path, capsys, converged):
    for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR", "POTCAR"):
        (tmp_path/name).write_text("unit fixture only\n")
    lines = []
    for step in range(1, 6):
        lines += [f"Iteration {step}( 3)\n", "aborting loop because EDIFF is reached\n", "TOTAL-FORCE (eV/Angst)\n", "-----\n"]
        lines += ["0.00000 0.00000 0.00000 0.0 0.0 0.0\n"]*50
        lines += ["-----\n", f"free  energy   TOTEN  = {-step:.8f} eV\n"]
    if converged:
        lines += ["reached required accuracy\n"]
    lines += ["General timing and accounting informations\n"]
    (tmp_path/"OUTCAR").write_text("".join(lines))
    record = {"name": "fixture", "remote_dir": str(tmp_path), "atom_count": 50}
    exec(reader_source(record, version=1), {})
    original = json.loads(capsys.readouterr().out)
    exec(reader_source(record, version=2), {})
    result = json.loads(capsys.readouterr().out)
    assert result == original  # Raw force tables, byte ranges, and whole OUTCAR hash.
    assert result["ionic_converged"] is converged
    assert len(result["frames"]) == 5
    assert all(f["EDIFF_marker_before_force"] for f in result["frames"])


def atoms():
    value = Atoms("Fe45C2OH", positions=np.zeros((49, 3)), cell=np.eye(3)*30, pbc=True)
    value.positions[:45, 0] = np.arange(45)*.3
    value.positions[45:] = [[1, 0, 2], [3, 0, 2], [2, 0, 2], [1, 0, 3]]
    value.set_constraint(FixAtoms(indices=range(18)))
    return value


def test_roles_are_chemical_not_fixed_atom_ids():
    value = atoms()
    groups = role_groups(value)
    assert groups["adsorbate_C"] == [45, 46]
    assert not any(i < 18 for group in groups.values() for i in group)
    value[45].symbol, value[47].symbol = "O", "C"
    assert role_groups(value)["adsorbate_C"] == [46, 47]


def test_group_normalization_and_fixed_atom_exclusion():
    value = atoms()
    groups = role_groups(value)
    weights = atom_weights(groups, len(value))
    assert weights.sum() == pytest.approx(1.)
    assert np.count_nonzero(weights[:18]) == 0
    total = sum(ROLE_WEIGHTS[k] for k, indices in groups.items() if indices)
    assert weights[groups["adsorbate_C"]].sum() == pytest.approx(2./total)
    reference, predicted = np.zeros((49, 3)), np.zeros((49, 3))
    predicted[:18] = 1000
    assert grouped_vector_loss(reference, predicted, groups) == 0.
    predicted[45] = [1, 0, 0]
    assert grouped_vector_loss(reference, predicted, groups) == pytest.approx(weights[45])
    predicted[45, 0] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        grouped_vector_loss(reference, predicted, groups)


def test_carbon_permutation_only_for_leakage_audit():
    frac = np.zeros((49, 3))
    frac[45:] = [[.2, .3, .4], [.6, .4, .5], [.4, .4, .5], [.2, .3, .5]]
    first = Poscar("fixture", np.eye(3)*10, ["Fe", "C", "O", "H"], [45, 2, 1, 1], frac.copy(), [("T", "T", "T")]*49)
    second = Poscar("fixture", first.cell, first.symbols, first.counts, frac.copy(), first.flags)
    second.frac[[45, 46]] = second.frac[[46, 45]]
    original = second.frac.copy()
    variants = pose_variants(second, [(np.eye(3, dtype=int), np.zeros(3))])
    assert pose_distance(first, variants) == pytest.approx(0.)
    np.testing.assert_array_equal(second.frac, original)


def test_different_element_order_does_not_hide_same_geometry():
    frac = np.zeros((49, 3))
    frac[45:] = [[.2, .3, .4], [.6, .4, .5], [.4, .4, .5], [.2, .3, .5]]
    first = Poscar("fixture", np.eye(3)*10, ["Fe", "C", "O", "H"], [45, 2, 1, 1], frac.copy(), [("T", "T", "T")]*49)
    reordered = frac.copy()
    reordered[45:] = frac[[47, 45, 46, 48]]
    second = Poscar("fixture", first.cell, ["Fe", "O", "C", "H"], [45, 1, 2, 1], reordered, first.flags)
    variants = pose_variants(second, [(np.eye(3, dtype=int), np.zeros(3))])
    assert pose_distance(first, variants) == pytest.approx(0.)
    np.testing.assert_array_equal(second.frac, reordered)


def test_force_changing_near_geometries_are_not_discarded():
    first = {"sample_id": "a", "origin": "expanded_closed_trajectory", "calculation_group": "one_job", "forces_eV_per_A": np.zeros((49, 3)).tolist()}
    second = {**first, "sample_id": "b", "forces_eV_per_A": np.zeros((49, 3)).tolist()}
    second["forces_eV_per_A"][46][0] = .03
    redundant = {**first, "sample_id": "c", "forces_eV_per_A": np.zeros((49, 3)).tolist()}
    redundant["forces_eV_per_A"][46][0] = .001
    kept, dropped = collapse_redundant([first, second, redundant], lambda a, b: .001)
    assert [r["sample_id"] for r in kept] == ["a", "b"]
    assert dropped[0]["sample_id"] == "c"


def test_split_isolation_comparison_skips_same_partition():
    rows = [{"sample_id": "a", "split": "train"}, {"sample_id": "b", "split": "train"}, {"sample_id": "c", "split": "heldout"}]
    found = list(cross_partition_pairs(rows, lambda a, b: .19, .2))
    assert [(a["sample_id"], b["sample_id"]) for a, b, _ in found] == [("a", "c"), ("b", "c")]
