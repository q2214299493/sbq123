import copy

import pytest
from ase.io import write

from scripts.adsorption.reico_selection import frame_distance, select_frames
from scripts.artifact_io import sha256_file
from tests.test_reico_sampling import atoms_fixture


def record(tmp_path, family, step, displacement, partition="train", labeled=False):
    atoms = atoms_fixture()
    atoms.positions[45:, 0] += displacement
    path = tmp_path / f"{family}_{step}.vasp"
    write(path, atoms, format="vasp", direct=True)
    return {"sample_id": f"{family}_{step}", "family_id": family, "step": step,
            "composition": "CH", "partition": partition, "already_DFT_labeled": labeled,
            "structure_path": str(path), "structure_sha256": sha256_file(path),
            "geometry_guard_failures": []}


def test_distance_preserves_site_and_movable_slab_context():
    first = atoms_fixture()
    second = first.copy()
    second.positions[45:, 0] += first.cell[0, 0]
    assert frame_distance(first, second) == pytest.approx(0, abs=1e-12)
    second.positions[45:, 0] -= first.cell[0, 0] - .4
    assert frame_distance(first, second) > .1
    second = first.copy()
    second.positions[18:45, 0] += .4
    assert frame_distance(first, second) > .1


def test_equal_element_permutations_are_duplicates():
    first = atoms_fixture()
    first.symbols[46] = "C"
    second = first.copy()
    second.positions[[45, 46]] = second.positions[[46, 45]]
    assert frame_distance(first, second) == pytest.approx(0, abs=1e-12)


def test_distance_uses_three_dimensional_vector_RMSD():
    first = atoms_fixture()
    second = first.copy()
    second.positions[45:, 0] += .15
    assert frame_distance(first, second) == pytest.approx(.15)


def test_existing_labels_and_farthest_frames_are_kept(tmp_path):
    rows = [record(tmp_path, "one", i, i * .06, labeled=i == 0) for i in range(21)]
    result = select_frames(rows)
    assert [r["step"] for r in result["selected"]] == [0, 10, 20]
    assert result["existing_DFT_labels"] == 1 and result["new_DFT_candidates"] == 2
    assert not result["model_accuracy_or_convergence_filter"]


def test_failure_boundary_is_retained_outside_selection_without_padding(tmp_path):
    rows = [record(tmp_path, "one", 0, 0), record(tmp_path, "one", 1, .01), record(tmp_path, "one", 2, .3)]
    rows[-1]["geometry_guard_failures"] = ["SHORT_CONTACT:C-Fe"]
    result = select_frames(rows)
    assert result["selected_count"] == 1 and result["short_families"] == {"one": 1}
    assert any(r["reason"] == "geometry_guard_boundary_preserved" for r in result["rejected"])


def test_near_duplicates_do_not_cross_data_partitions(tmp_path):
    rows = [record(tmp_path, "train", 0, 0), record(tmp_path, "test", 0, 0, partition="final_test")]
    result = select_frames(rows)
    assert len(result["selected"]) == 1 and result["selected"][0]["partition"] == "final_test"
    assert result["rejected"][0]["reason"] == "near_duplicate_cross_partition"


def test_family_split_leakage_is_rejected(tmp_path):
    rows = [record(tmp_path, "one", 0, 0), record(tmp_path, "one", 1, .3, partition="development")]
    with pytest.raises(ValueError, match="family split"):
        select_frames(rows)


def test_changed_source_bytes_and_duplicate_existing_labels_fail_closed(tmp_path):
    one = record(tmp_path, "one", 0, 0, labeled=True)
    two = record(tmp_path, "two", 0, 0, labeled=True)
    with pytest.raises(ValueError, match="duplicate/split review"):
        select_frames([one, two])
    changed = copy.deepcopy(one)
    changed["structure_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frame bytes"):
        select_frames([changed])
