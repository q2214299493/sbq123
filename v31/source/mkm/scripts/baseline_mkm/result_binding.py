"""Read-only binding of an accepted CATKINAS point and its observed steady-state solution."""

import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_json
from scripts.baseline_mkm.steady_states import observe
from scripts.kinetic_data.scientific_identity import check_binding, dataset_reference, read_artifact
from scripts.multiphase_contracts import read_unique_json as read


def bind_result(run, *, normalization_profile=None):
    run = Path(run)
    plan = read(run / "plan.json")
    dataset, dataset_hash = read_artifact(run / "dataset.json")
    inputs = dict(network=sha256_file(run / "network.json"), dataset=dataset_hash,
                  configuration=sha256_file(run / "configuration.json"))
    if inputs != plan["input_hashes"] or dataset["network_version"] != plan["network_version_id"]:
        raise ValueError("MKM network, dataset or configuration differs from approved plan")
    approved_profile = plan.get("normalization_profile_sha256")
    profile = normalization_profile or plan.get("normalization_profile")
    profile_hash = sha256_file(Path(profile)) if profile else None
    if approved_profile and profile_hash != approved_profile:
        raise ValueError("MKM normalization profile differs from approved plan")
    point = observe(run, Path(profile) if profile else None)
    result = read(run / "result.json")
    if (result["run_id"] != plan["run_id"] or point["plan_sha256"] != result["plan_sha256"]
            or point["result_sha256"] != sha256_file(run / "result.json")
            or dataset["dataset_version"] != plan["kinetic_dataset_version"]):
        raise ValueError("MKM result identity differs from accepted execution")
    root = {k: point[k] for k in ("coverage", "vacancy", "native_initial", "initial_coverages",
                                  "single_point_residual", "analysis_residual")}
    evidence = {k: point[k] for k in ("plan_sha256", "receipt_sha256", "result_sha256", "native_input_sha256",
                                      "mat_sha256", "log_sha256", "runtime")}
    payload = dict(format="mkm-point-binding/1", run_id=plan["run_id"], scope=result["scope"],
                   dataset=dataset_reference(dataset, dataset_hash), input_hashes=inputs,
                   conditions={k: plan[k] for k in ("temperature_K", "total_pressure_bar",
                                                      "partial_pressures_bar", "standard_states")},
                   execution=evidence, normalization=point["normalization"], net_rate_unit=point["net_rate_unit"],
                   normalization_profile_sha256=profile_hash, profile_bound_by_plan=bool(approved_profile),
                   root=root, root_state_sha256=sha256_json({k: root[k] for k in ("coverage", "vacancy")}))
    return dict(payload, binding_sha256=sha256_json(payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--normalization-profile", type=Path, help="Reviewed profile for legacy points")
    args = parser.parse_args()
    binding = bind_result(args.run, normalization_profile=args.normalization_profile)
    if args.verify:
        check_binding(read(args.verify), binding)
    print(json.dumps(binding, indent=2, allow_nan=False))
