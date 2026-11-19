"""Independently verify completed AQCat25 comparison outputs and errors."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np


def read_json(path):
    if not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError(f"missing or oversized comparison artifact: {path.name}")
    return json.loads(path.read_bytes())


def verify(bundle, returned):
    request = read_json(bundle / "request.json")
    result = read_json(returned / "comparison_result.json")
    dft = {x["point"]: x for x in read_json(bundle / "validation_points.json")}
    assert sorted(dft) == request["validation"] == [7, 8]
    assert result["base_sha256"] == request["base_sha256"]
    assert result["updates_per_arm"] == request["updates"] == 100
    assert result["force_target_eV_per_A"] == request["force_target_eV_per_A"] == 0.03
    assert result["new_dft_performed"] is False and result["model_promoted"] is False
    assert result["identical_lr_trace"] is True
    trajectories = {}
    errors = {}
    for arm, points in request["training"].items():
        fit = read_json(returned / f"{arm}_fit_result.json")
        assert fit["arm"] == arm and fit["base_sha256"] == request["base_sha256"]
        assert fit["device"] == result["training_device"] and len(fit["checkpoint_sha256"]) == 64
        trace = fit["trace"]
        assert [event["step"] for event in trace] == list(range(1, 101))
        visited = [event["point"] for event in trace]
        assert visited == points * (100 // len(points)) and not set(visited) & dft.keys()
        assert Counter(map(str, visited)) == result["data_counts"][arm]
        trajectories[arm] = [event["lr"] for event in trace]
        assert [x["point"] for x in result["validation"][arm]] == [7, 8]
        errors[arm] = {}
        for row in result["validation"][arm]:
            point = row["point"]
            ref = dft[point]
            assert row["label_sha256"] == ref["label_sha256"]
            model = np.asarray(row["predicted_forces_eV_per_A"])
            label = np.asarray(ref["forces_eV_per_A"])
            assert model.shape == label.shape == (49, 3) and np.isfinite(model).all() and np.isfinite(label).all()
            error = model[18:] - label[18:]
            norms = np.linalg.norm(error, axis=1)
            assert np.isclose(norms.max(), row["max_vector_error_eV_per_A"], rtol=0, atol=1e-12)
            assert np.isclose(np.abs(error).mean(), row["component_mae_eV_per_A"], rtol=0, atol=1e-12)
            assert int(norms.argmax()) + 19 == row["max_error_atom_one_based"]
            errors[arm][point] = {"max_error_eV_A": float(norms.max()),
                                  "component_mae_eV_A": float(np.abs(error).mean()),
                                  "max_atom_1based": int(norms.argmax()) + 19}
    assert trajectories["single"] == trajectories["joint"]
    assert np.max(trajectories["single"]) == 1e-4 and np.min(trajectories["single"]) > 0
    return {"evaluation_job": result["device"]["slurm_job_id"], "gpu_uuid": result["device"]["gpu_uuid"],
            "training_job": result["training_device"]["slurm_job_id"],
            "errors": errors, "updates": 100, "lr_equal_each_step": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("returned", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle, args.returned), indent=2))
