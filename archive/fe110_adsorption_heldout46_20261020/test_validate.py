import copy

import numpy as np
import pytest

from archive.fe110_adsorption_heldout46_20261020.validate import metrics
from archive.fe110_adsorption_validation_20261018.runtime import validate_scope, verify_independent_source
from archive.fe110_adsorption_validation_20261018.test_force24 import force_scope
from scripts.artifact_io import sha256_file, write_json_exclusive


def independent_scope():
    request, auth, sha, exception = copy.deepcopy(force_scope())
    request.update(document_kind="adsorption_independent_force_validation",
        sample_role="frozen_whole_job_heldout_not_used_for_current_fit_or_selection",
        samples=[{"sample_id": str(i), "source_name": "09_C" if i < 23 else "10_A"} for i in range(46)],
        source_manifest_sha256="f"*64)
    exception.update(sample_count=46, source_names=["09_C", "10_A"], prediction_count=92, frozen_proposal_sha256="f"*64)
    return request, auth, sha, exception


def test_independent_scope_uses_new_role_without_weakening_old_diagnostics():
    validate_scope(*independent_scope())


@pytest.mark.parametrize("problem", ["role", "count", "proposal", "budget", "optimization", "duplicate", "model", "source"])
def test_independent_scope_rejects_changes(problem):
    request, auth, sha, exception = independent_scope()
    if problem == "role":
        request["sample_role"] = "screened_untrained_diagnostic_not_independent_heldout"
    elif problem == "count":
        request["samples"].pop()
    elif problem == "proposal":
        request["source_manifest_sha256"] = "changed"
    elif problem == "budget":
        request["max_wall_seconds"] += 1
    elif problem == "optimization":
        request["geometry_cases"] = [{"name": "09_C"}]
    elif problem == "duplicate":
        request["samples"][1] = request["samples"][0]
    elif problem == "model":
        request["models"]["candidate"]["sha256"] = "changed"
    else:
        request["samples"][0]["source_name"] = "10_C"
    with pytest.raises(ValueError):
        validate_scope(request, auth, sha, exception)


def test_metric_masks_fixed_atoms_and_reports_tail_and_opposed_directions():
    row = {"sample_id": "x", "symbols": ["Fe", "C", "H"], "fixed_atom_indices_0based": [0],
        "force_role_groups": {"adsorbate_C": [1], "adsorbate_H": [2], "adsorbate_O": [], "near_Fe": [], "other_Fe": []},
        "forces_eV_per_A": [[100, 0, 0], [1, 0, 0], [0, .00001, 0]]}
    pred = {"x": [[-100, 0, 0], [-1, 0, 0], [0, .00001, 0]]}
    result = metrics([row], pred, "adsorbate")
    assert result["atom_count"] == 2
    assert result["vector_mae_eV_A"] == pytest.approx(1)
    assert result["vector_rmse_eV_A"] == pytest.approx(np.sqrt(2))
    assert result["vector_max_eV_A"] == 2
    assert result["vector_p95_eV_A"] == pytest.approx(1.9)
    assert result["opposed_force_vectors"] == 1
    assert result["direction_atom_count"] == 1
    assert metrics([row], pred, "adsorbate_O") == {"atom_count": 0}


def test_frozen_source_rejects_force_mutation_and_job_leakage(tmp_path):
    row = {"sample_id": "x", "calculation_group": "test", "structure_equivalence_sha256": "testgeometry",
        "structure_path": "old", "forces_eV_per_A": [[1., 0., 0.]],
        "label_source": {"path": "labels.json", "sha256": "", "sample_id": "x"}}
    write_json_exclusive(tmp_path / "labels.json", {"label": "unchanged"})
    row["label_source"]["sha256"] = sha256_file(tmp_path / "labels.json")
    train = {"calculation_group": "train", "structure_equivalence_sha256": "traingeometry"}
    path = tmp_path / "manifest.json"
    manifest = {"splits": {"heldout": [row], "train": [train], "development": []}, "quarantined_observed_heldout": [None]*16}
    write_json_exclusive(path, manifest)
    source = {"document_kind": "adsorption_independent_validation_proposal", "selected_arm": "control",
        "selection_frozen_before_heldout_prediction": True, "models": {}, "samples": [row],
        "training_manifest": {"sha256": sha256_file(path)}}
    request = {"models": {}, "samples": [copy.deepcopy(row)],
        "frozen_training_manifest": {"path": path.name, "sha256": sha256_file(path)}}
    verify_independent_source(tmp_path, request, source)
    request["samples"][0]["forces_eV_per_A"][0][0] = 2.
    with pytest.raises(ValueError, match="frozen label changed"):
        verify_independent_source(tmp_path, request, source)
    request["samples"] = [copy.deepcopy(row)]
    leak = tmp_path / "leak.json"
    train["calculation_group"] = "test"
    write_json_exclusive(leak, manifest)
    request["frozen_training_manifest"] = {"path": leak.name, "sha256": sha256_file(leak)}
    source["training_manifest"]["sha256"] = sha256_file(leak)
    with pytest.raises(ValueError, match="leakage"):
        verify_independent_source(tmp_path, request, source)
