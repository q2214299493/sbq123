from __future__ import annotations

import copy

import numpy as np
import pytest

from scripts.adsorption.reico_joint_coverage import (
    fixed_threshold_soap, joint_force_table, missing_environment_groups, require_training,
)


def row(sid, signature="A", force=1., group="job1", composition="C2HO"):
    return {"sample_id": sid, "partition": "train", "composition": composition,
            "family_id": group, "source_group": group, "joint_signature": signature,
            "graph_signature": signature, "coordination_signature": signature,
            "joint_by_scale": {"1.2": signature, "1.25": signature, "1.3": signature},
            "movable_fmax_eV_A": force, "magnetic_review_level": "LEGACY_TOTAL_MAGNETIZATION_ONLY",
            "adsorbate_component_count": 1, "novelty_ratio": .5, "exceeds_internal_threshold": False}


@pytest.mark.parametrize("partition", ["development", "final_test", "heldout", None])
def test_reject_reserved_rows(partition):
    value = row("x")
    value["partition"] = partition
    with pytest.raises(ValueError, match="training records only"):
        require_training([value])


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        require_training([row("x"), row("x")])


def test_low_force_boundary_and_one_source_are_explicit():
    rows = [row("x", force=.05), row("y", force=.049), row("z", force=.051)]
    original = copy.deepcopy(rows)
    report = joint_force_table(rows, [0, .05, .1, 1])["C2HO"]
    assert report["low_force_le_0p05"] == 2
    assert report["low_force_source_groups"] == ["job1"]
    assert report["fmax_histogram"]["[0,0.05)"] == 1
    assert report["fmax_histogram"]["[0.05,0.1)"] == 2
    assert report["magnetic_review_levels"] == {"LEGACY_TOTAL_MAGNETIZATION_ONLY": 3}
    assert rows == original


def test_low_force_disconnected_not_called_connected():
    value = row("x", force=.01)
    value["adsorbate_component_count"] = 2
    report = joint_force_table([value], [0, .05])["C2HO"]
    assert report["low_force_le_0p05"] == 1
    assert report["connected_low_force_frames"] == 0


def test_existing_selected_label_separated_from_unselected_gap():
    pool = [row("current"), row("selected", "B"), row("unselected", "C")]
    before = copy.deepcopy(pool)
    report, gaps = missing_environment_groups(pool, [pool[0]], {"current", "selected"})
    assert report["C2HO"]["joint_signature"]["current_missing"] == 2
    assert report["C2HO"]["joint_signature"]["missing_if_all_original_selected_labels_admitted"] == 1
    assert gaps[0]["original_selected_labels_not_in_package"] == ["selected"]
    assert gaps[0]["next_action"] == "REVIEW_EXISTING_SELECTED_LABELS"
    assert gaps[1]["DFT_force_of_missing_frames"] == "UNKNOWN_NOT_INFERRED_FROM_NEIGHBORS"
    assert pool == before


def test_cutoff_sensitive_gap_not_robust():
    pool = [row("current"), row("candidate", "B")]
    pool[1]["joint_by_scale"]["1.2"] = "A"
    _, gaps = missing_environment_groups(pool, [pool[0]], {"current"})
    assert gaps[0]["robust_missing_frames_all_scales"] == 0


def test_other_composition_cannot_fill_same_signature():
    pool = [row("query", "A")]
    training = [row("reference", "A", composition="C3H2O")]
    report, gaps = missing_environment_groups(pool, training, set())
    assert report["C2HO"]["joint_signature"]["current_missing"] == 1
    assert len(gaps) == 1


def descriptor(sid, vector, composition="C2HO"):
    vector = np.array(vector, dtype=float)
    return {**row(sid, composition=composition), "roles": np.array(["C"]),
            "vectors": (vector/np.linalg.norm(vector))[None, :]}


def test_fixed_soap_threshold_and_composition_isolation():
    pool = [descriptor("query", [0, 1])]
    training = [descriptor("same", [1, 0]), descriptor("other", [0, 1], "C3H2O")]
    prior = {"C2HO": {"thresholds": {"C": .2}}}
    report, scores = fixed_threshold_soap(pool, training, prior)
    assert scores[0]["novelty_ratio"] == pytest.approx(5.)
    assert report["C2HO"]["fixed_thresholds"] == {"C": .2}
    _, improved = fixed_threshold_soap(pool, [*training, descriptor("new", [0, 1])], prior)
    assert improved[0]["novelty_ratio"] == pytest.approx(0.)


def test_absent_soap_reference_fails_explicitly():
    with pytest.raises(ValueError, match="missing composition"):
        fixed_threshold_soap([descriptor("query", [0, 1])], [], {"C2HO": {"thresholds": {"C": .2}}})


def test_unbound_extra_old_cache_is_ignored(tmp_path):
    from archive.fe110_joint_coverage_20261023.run import descriptors
    from scripts.adsorption.reico_stratified_audit import CachedSOAP
    from tests.test_reico_environment_audit import slab

    class FreshSOAP:
        def get_number_of_features(self):
            return 2

        def create(self, atoms, centers, n_jobs):
            return np.ones((len(centers), 2))

    old_cache, new_cache = tmp_path/"old", tmp_path/"new"
    old_cache.mkdir()
    structure_hash = "a"*64
    unbound = old_cache/(structure_hash+".npz")
    unbound.write_bytes(b"unbound extra file must not be opened")
    value = {**row("x"), "structure_sha256": structure_hash}
    inventory = []
    result = descriptors([value], {"x": slab()}, {"descriptor": {"near_Fe_A": 3}},
                         old_cache, {}, new_cache, FreshSOAP(), CachedSOAP(2), inventory)
    assert len(result) == 1 and not inventory[0]["reused_prior_cache"]
    assert unbound.read_bytes() == b"unbound extra file must not be opened"
