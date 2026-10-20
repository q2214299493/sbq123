import copy

import pytest

from archive.fe110_adsorption_candidate_review_20261020 import review


def arms():
    keys = ("forces_role_vector_mae", "forces_adsorbate_C_vector_mae", "forces_adsorbate_O_vector_mae",
            "forces_adsorbate_H_vector_mae", "forces_near_Fe_vector_mae", "forces_other_Fe_vector_mae", "forces_replay_vector_mae")
    first = dict(zip(keys, (.0398, .0594, .0602, .0128, .0380, .0185, .0091), strict=True), epoch=2)
    second = dict(zip(keys, (.0403, .0588, .0491, .0174, .0416, .0220, .0086), strict=True), epoch=2)
    return {"control": {"development_rounded_native_log": [{**first, "forces_role_vector_mae": .0400, "epoch": 1}, first]},
            "treatment": {"development_rounded_native_log": [{**second, "forces_role_vector_mae": .0420, "epoch": 1}, second]}}


def test_common_development_selection_does_not_hide_group_tradeoffs():
    data = arms()
    before = copy.deepcopy(data)
    result = review.grouped_review(data)
    rows = {row["metric"]: row for row in result["rows"]}
    assert result["best_epochs_from_rounded_native_log"] == {"control": 2, "treatment": 2}
    assert rows["forces_role_vector_mae"]["direction"] == "control_lower"
    assert rows["forces_adsorbate_C_vector_mae"]["direction"] == "treatment_lower"
    assert rows["forces_adsorbate_O_vector_mae"]["relative_change_percent"] < 0
    assert rows["forces_adsorbate_H_vector_mae"]["relative_change_percent"] > 0
    assert rows["forces_near_Fe_vector_mae"]["direction"] == "control_lower"
    assert rows["forces_replay_vector_mae"]["direction"] == "treatment_lower"
    assert result["group_regressions_are_soft_review_warnings_not_zero_tolerance_failures"]
    assert data == before


def test_frozen_holdout_audit_rejects_changed_manifest_binding(monkeypatch):
    monkeypatch.setattr(review, "load_json_object", lambda _: {"artifacts": [{"path": "training_manifest.json", "sha256": "bound"}]})
    monkeypatch.setattr(review, "sha256_file", lambda _: "changed")
    with pytest.raises(ValueError, match="split changed"):
        review.frozen_validation_rows()


@pytest.mark.parametrize("problem", ["count", "job", "equivalent", "quarantine"])
def test_frozen_holdout_audit_rejects_scope_and_split_leakage(monkeypatch, problem):
    rows = [{"source_name": "09_C" if i < 23 else "10_A", "calculation_group": "testjob"+str(i),
             "structure_equivalence_sha256": "testgeometry"+str(i)} for i in range(46)]
    train = [{"calculation_group": "trainjob", "structure_equivalence_sha256": "traingeometry"}]
    manifest = {"splits": {"train": train, "development": [], "heldout": rows}, "quarantined_observed_heldout": [None]*16}
    if problem == "count":
        rows.pop()
    elif problem == "job":
        rows[0]["calculation_group"] = "trainjob"
    elif problem == "equivalent":
        rows[0]["structure_equivalence_sha256"] = "traingeometry"
    else:
        manifest["quarantined_observed_heldout"].pop()
    monkeypatch.setattr(review, "load_json_object", lambda _: {"artifacts": [{"path": "training_manifest.json", "sha256": "bound"}]})
    monkeypatch.setattr(review, "sha256_file", lambda _: "bound")
    monkeypatch.setattr(review, "load_manifest", lambda _: manifest)
    with pytest.raises(ValueError):
        review.frozen_validation_rows()
