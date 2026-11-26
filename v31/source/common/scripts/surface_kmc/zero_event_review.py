"""Check an oxide zero-event input and request separate approval. No native launcher."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes, sha256_file
from scripts.execution_permission import require_bound_action
from scripts.multiphase_contracts import _unique_keys
from scripts.surface_kmc.oxide_control import render

ACTION = "allow_zacros_zero_event_initialization"
LIMITS = {"max_steps": 0, "native_wall_seconds": 15, "external_timeout_seconds": 30,
          "maximum_processes": 1, "maximum_threads": 1, "retries": 0}


def prepare_request(stage, root, executable):
    """Read and hash the immutable plan, executable, five inputs and their source bindings."""
    raw = (stage / "execution_plan.json").read_bytes()
    plan = json.loads(raw, object_pairs_hook=_unique_keys)
    if (plan["action"] != ACTION or plan["limits"] != LIMITS or plan["dynamic_execution"] is not False
            or plan["human_approval_required"] is not True or plan["production_eligible"] is not False
            or plan["arguments"] != ["--max_steps=0", "--wall_time=15"]
            or plan["environment"] != {"OMP_NUM_THREADS": "1"}):
        raise ValueError("Invalid zero-event execution scope or budget")
    archived = json.loads((root / "reports/multiphase/phase2_5_1/zacros_validation.json").read_bytes())
    if (plan["engine"]["version"] != "4.0" or plan["engine"]["sha256"] != archived["executable_sha256"]
            or sha256_file(executable) != archived["executable_sha256"]):
        raise ValueError("Zacros executable digest differs")
    if set(plan["bound_artifacts_sha256"]) != {"native/input_manifest.json", "control.json", "numerical_reference.json"}:
        raise ValueError("Incomplete plan bindings")
    for name, digest in plan["bound_artifacts_sha256"].items():
        if sha256_file(stage / name) != digest:
            raise ValueError(f"Plan binding differs: {name}")

    members, manifest = render(stage / "control.json", root)
    native = stage / "native"
    if set(p.name for p in native.iterdir()) != {*members, "input_manifest.json"}:
        raise ValueError("Unexpected native directory contents")
    if (manifest != json.loads((native / "input_manifest.json").read_bytes(), object_pairs_hook=_unique_keys)
            or manifest["structural_manifest_sha256"] != plan["structural_manifest_sha256"]
            or manifest["dataset_id"] != plan["dataset_id"] or manifest["files_sha256"] != plan["input_files_sha256"]):
        raise ValueError("Execution manifest differs from the verified structure or dataset")
    for name, expected in members.items():
        if (native / name).read_bytes() != expected:
            raise ValueError(f"Native input differs: {name}")

    return {"format": "zacros-zero-event-approval-request/1", "question_id": plan["question_id"],
            "dataset_id": plan["dataset_id"], "requested_action": ACTION,
            "question": "Approve one serial native initialization of this exact synthetic dataset at zero executed events?",
            "choices": ["approve", "reject"], "DECISION": "pending", "ALLOWED_ACTIONS": [],
            "state_sha256": sha256_bytes(raw), "digest_basis": "exact execution_plan.json bytes",
            "engine": plan["engine"], "input_manifest_sha256": plan["bound_artifacts_sha256"]["native/input_manifest.json"],
            "input_files_sha256": manifest["files_sha256"], "limits": plan["limits"],
            "approval_scope": "Native software test only. State Handoff review has separate authority."}


def check_reviewed_action(stage, root, executable, decision, review_source):
    """Check an externally authenticated researcher decision against the current bytes."""
    request = prepare_request(stage, root, executable)
    if (decision.get("format") != "zacros-zero-event-approval/1" or decision.get("DECISION") != "approve"
            or decision.get("ALLOWED_ACTIONS") != [ACTION] or decision.get("question_id") != request["question_id"]
            or decision.get("dataset_id") != request["dataset_id"] or not (decision.get("reviewer") or "").strip()
            or decision.get("source_sha256") != sha256_file(review_source)):
        raise PermissionError("A separate, attributable zero-event execution approval is required")
    return require_bound_action(decision, ACTION, request["state_sha256"], {ACTION})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(prepare_request(args.stage, args.root, args.executable), indent=2))
