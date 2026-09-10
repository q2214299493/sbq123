"""Prepare a reviewed GPU-path Dimer through the canonical gate; never submit."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json, source_file_manifest
from scripts.ml_candidate_source import load_candidate_path
from scripts.dual_model_ml_neb import _load_request
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.gpu_dimer_parent import PARENT_METHOD, validate_reviewed_gpu_parent
from scripts.ts_strategy_engine.handoff import prepare_dimer_handoff
from scripts.vasp_inputs import build_fe110_dimer

ROOT = Path(__file__).resolve().parents[1]


def bind(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def prepare(request_path, manifest_path, review_path, contract_path, parent, destination, *, cores):
    if parent.exists() or destination.exists():
        raise FileExistsError("New parent and Dimer directories are required")
    policy = ROOT / "configs/dimer_gate.yaml"
    contract = load_contract(contract_path)
    review = load_json_object(review_path)
    request = _load_request(request_path)
    manifest = load_json_object(manifest_path)
    _, rows = load_candidate_path(request, manifest, manifest_path, request_path, method="ml_neb", minimum_images=3)
    analysis = {
        "document_kind": "gpu_dimer_parent_analysis", "producer": "scripts.prepare_gpu_path_dimer",
        "source_files": source_file_manifest([request_path, manifest_path, review_path, contract_path, policy]),
        "status": "ML_CANDIDATE_REVIEWED", "parent_neb_method": PARENT_METHOD,
        "maximum_image": review["candidate_image"], "internal_maximum": True,
        "image_sequence_complete": True, "geometry_validated": True,
        "path_reviewed": True, "path_binding_valid": True,
        "dimer_gate_policy_file": str(policy), "dimer_gate_policy_sha256": sha256_file(policy),
        "gpu_reviewed_path_evidence": {name: bind(path) for name, path in (
            ("request", request_path), ("manifest", manifest_path), ("review", review_path), ("contract", contract_path))},
        "images": [{"image": row["image"], "structure_sha256": row["sha256"],
                    "source": "ML_prediction_only"} for row in rows],
        **{key: contract[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")},
    }
    validated = validate_reviewed_gpu_parent(analysis)
    if not validated["passed"]:
        raise ValueError(validated["errors"])
    index = int(review["candidate_image"])
    paths = [rows[i]["source_path"] for i in (index - 1, index, index + 1)]
    triad = evaluate_candidate_triad(*paths, analysis, contract["reaction_atoms"])
    if not triad["hard_gate_passed"]:
        raise ValueError(triad["hard_gate_errors"])
    geometry = load_json_object(Path(review["evidence"]["geometry"]["path"]))
    thresholds_path = ROOT / "configs/neb_agent/default_thresholds.yaml"
    thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    parent.mkdir(parents=True)
    write_json(parent / "analysis.json", analysis)
    write_json(parent / "candidate_triad_gate.json", triad)
    write_json(parent / "path_review.json", {**review, "status": "accepted"})
    decision = decide_execution(geometry, analysis, thresholds, climb=False, path_reviewed=True,
                                source_bindings={"analysis": bind(parent / "analysis.json"),
                                                 "thresholds": bind(thresholds_path),
                                                 "geometry": review["evidence"]["geometry"]})
    gate_path = parent / "dimer_preparation_gate.json"
    write_json(gate_path, decision)
    require_action(gate_path, "PREPARE_DIMER_HANDOFF", decision["state_sha256"])
    binding = {key: contract[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")}
    binding["report_sha256"] = sha256_file(manifest_path)
    prepare_dimer_handoff(paths[1], paths[0], paths[2], destination, False,
                         analysis_path=parent / "analysis.json", path_review_path=parent / "path_review.json",
                         reaction_indices=contract["reaction_atoms"], contract_binding=binding,
                         gate_decision=gate_path, gate_state_sha256=decision["state_sha256"])
    write_json(destination / "input_generation_manifest.json", build_fe110_dimer(destination, cores=cores))
    return {"destination": str(destination), "decision": decision["DECISION"], "submitted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("request", "manifest", "review", "contract", "parent", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cores", type=int, required=True)
    args = parser.parse_args()
    print(prepare(args.request.resolve(), args.manifest.resolve(), args.review.resolve(),
                  args.contract.resolve(), args.parent.resolve(), args.destination.resolve(), cores=args.cores))


if __name__ == "__main__":
    main()
