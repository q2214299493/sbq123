import copy
import json

import numpy as np
import pytest

from archive.fe110_adsorption_validation_20261018.force24 import aggregate, read_predictions, stage
from archive.fe110_adsorption_validation_20261018.runtime import validate_scope
from archive.fe110_adsorption_validation_20261018.test_runtime import scope


def force_scope():
    request, auth, sha, exception = copy.deepcopy(scope())
    request.update(document_kind="adsorption_exact_trajectory_force_comparison", limits={}, geometry_cases=[],
        sample_role="screened_untrained_diagnostic_not_independent_heldout",
        samples=[{"sample_id": str(i), "source_name": name} for i, name in enumerate(["06_C", "07_B", "08_A"] * 8)])
    del request["heldout"]
    exception.update(sample_count=24, source_names=["06_C", "07_B", "08_A"])
    auth["action"] = "RUN_GPU_ADSORPTION_EXACT_FORCES"
    return request, auth, sha, exception


def test_force_only_scope_passes():
    validate_scope(*force_scope())


@pytest.mark.parametrize("change", ["optimize", "geometry", "heldout", "duplicate", "source", "action", "count"])
def test_force_only_scope_cannot_expand(change):
    request, auth, sha, exception = force_scope()
    if change == "optimize":
        request["limits"] = {"max_steps": 1}
    elif change == "geometry":
        request["geometry_cases"] = [{"name": "06_C"}]
    elif change == "heldout":
        request["sample_role"] = "independent_heldout"
    elif change == "duplicate":
        request["samples"][0] = request["samples"][1]
    elif change == "source":
        request["samples"][0]["source_name"] = "08_B"
    elif change == "action":
        auth["action"] = "RUN_GPU_ADSORPTION_FROZEN_VALIDATION"
    else:
        request["samples"].pop()
    with pytest.raises(ValueError):
        validate_scope(request, auth, sha, exception)


def sample():
    return {"sample_id": "test", "symbols": ["Fe"] * 45 + ["C", "O"],
            "fixed_atom_indices_0based": list(range(18)), "forces_eV_per_A": np.zeros((47, 3)).tolist(),
            "structure_sha256": "a" * 64, "ionic_step": 1, "source_total_steps": 131}


def test_aggregate_counts_only_free_atoms_and_weights_atom_vectors():
    row = sample()
    pred = np.zeros((47, 3))
    pred[:18] = 100
    pred[45] = [2, 0, 0]
    result = aggregate([row], {"test": pred.tolist()})
    assert result["adsorbate"]["vector_rmse_eV_A"] == pytest.approx(np.sqrt(2))
    assert result["Fe"]["vector_rmse_eV_A"] == 0


def test_stage_is_sampling_metadata_not_a_physics_gate():
    row = sample()
    assert stage(row) == "early_steps_1_2_5"
    row["ionic_step"] = 66
    assert stage(row) == "intermediate_sampled_steps"
    row["ionic_step"] = 130
    assert stage(row) == "last_two_steps"


@pytest.mark.parametrize("change", [None, "checkpoint", "duplicate", "structure", "nan", "shape"])
def test_prediction_binding_and_finite_complete_forces(tmp_path, change):
    row = sample()
    request = {"samples": [row], "models": {"baseline": {"sha256": "b" * 64}}}
    payload = {"checkpoint_sha256": "b" * 64, "samples": [{"sample_id": "test",
        "structure_sha256": row["structure_sha256"], "predicted_forces_eV_per_A": row["forces_eV_per_A"]}]}
    if change == "checkpoint":
        payload["checkpoint_sha256"] = "c" * 64
    elif change == "duplicate":
        payload["samples"] *= 2
    elif change == "structure":
        payload["samples"][0]["structure_sha256"] = "d" * 64
    elif change == "nan":
        payload["samples"][0]["predicted_forces_eV_per_A"][45][0] = float("nan")
    elif change == "shape":
        payload["samples"][0]["predicted_forces_eV_per_A"].pop()
    (tmp_path / "output").mkdir()
    (tmp_path / "output/baseline_forces.json").write_text(json.dumps(payload))
    if change:
        with pytest.raises(ValueError):
            read_predictions(request, tmp_path, "baseline")
    else:
        assert set(read_predictions(request, tmp_path, "baseline")) == {"test"}
