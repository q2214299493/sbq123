import copy
import json

import pytest

from archive.fe110_adsorption_calibration_20261018.review_existing_candidate import (
    GPU_READER,
    VASP_PROBE,
    summarize,
)


def evidence(candidate_error=0.4):
    manifest = {"splits": {"development": [{"sample_id": "dev", "structure_sha256": "g" * 64,
                                           "sample_role": "adsorption_trajectory_development"}],
                           "heldout": [{"sample_id": "never_predict_here"}]}}
    models = {}
    checkpoints = {}
    for name, error, sha in (("baseline", 0.5, "a" * 64), ("candidate", candidate_error, "b" * 64)):
        checkpoints[name] = {"sha256": sha}
        models[name] = {"checkpoint_sha256": sha,
                        "samples": [{"sample_id": "dev", "structure_sha256": "g" * 64,
                                     "role": "adsorption_trajectory_development",
                                     "groups": {"adsorbate": {"atom_count": 3, "vector_rmse_eV_A": error}}}],
                        "groups": {"C2/adsorbate": {"atom_count": 3, "vector_rmse_eV_A": error}}}
    comparison = {"request_sha256": "r" * 64, "heldout_consumed": False, "models": models}
    return comparison, manifest, "r" * 64, checkpoints


def test_improvement_is_development_evidence_not_promotion():
    result = summarize(*evidence())
    assert result["groups"]["C2/adsorbate"]["reduction_percent"] == pytest.approx(20)
    assert result["checkpoint_promoted"] is False
    assert result["heldout_consumed"] is False
    assert result["geometry_drift_tested"] is False
    assert result["acceleration_proved"] is False


def test_regression_is_warning_not_invented_zero_tolerance_gate():
    result = summarize(*evidence(0.50001))
    assert result["groups"]["C2/adsorbate"]["trend"] == "REGRESSION_WARNING"


@pytest.mark.parametrize("failure", ["heldout", "request", "checkpoint", "structure", "missing_sample",
                                    "duplicate_sample", "aggregate_count", "aggregate_error", "nan", "negative"])
def test_stale_incomplete_or_invalid_evidence_rejected(failure):
    args = copy.deepcopy(evidence())
    comparison, _, _, _ = args
    model = comparison["models"]["candidate"]
    if failure == "heldout":
        comparison["heldout_consumed"] = True
    elif failure == "request":
        comparison["request_sha256"] = "different"
    elif failure == "checkpoint":
        model["checkpoint_sha256"] = "different"
    elif failure == "structure":
        model["samples"][0]["structure_sha256"] = "different"
    elif failure == "missing_sample":
        model["samples"] = []
    elif failure == "duplicate_sample":
        model["samples"].append(copy.deepcopy(model["samples"][0]))
    elif failure == "aggregate_count":
        model["groups"]["C2/adsorbate"]["atom_count"] += 1
    elif failure == "aggregate_error":
        model["groups"]["C2/adsorbate"]["vector_rmse_eV_A"] += 0.1
    else:
        model["samples"][0]["groups"]["adsorbate"]["vector_rmse_eV_A"] = float("nan") if failure == "nan" else -0.1
    with pytest.raises(ValueError):
        summarize(*args)


def test_permission_failure_is_not_missing_calculation(monkeypatch, capsys):
    from pathlib import Path

    def denied(*args, **kwargs):
        raise PermissionError(13, "permission denied", "synthetic_only")

    monkeypatch.setattr(Path, "stat", denied)
    exec(VASP_PROBE, {})
    result = json.loads(capsys.readouterr().out)
    assert result["access_status"] == "ACCESS_ERROR"
    assert result["errno"] == 13
    assert result["remote_write"] is False


def test_remote_collection_does_not_load_or_run_model():
    assert "model_executed':False" in GPU_READER
    assert "import torch" not in GPU_READER
    assert "get_forces" not in GPU_READER
    assert "bsub" not in GPU_READER
    assert "sbatch" not in GPU_READER
