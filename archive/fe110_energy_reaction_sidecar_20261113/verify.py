"""Verify sidecar bindings and frozen inputs, writing only a new audit receipt."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect import BASE, OUT, ROOT

CANONICAL = [
    "energy_label_sidecar_final_v2.json", "energy_reuse_catalog_v2.json", "reaction_coverage_v2.json",
    "sidecar_summary_v2.json", "relative_energy_pair_candidates.json", "reaction_source_sidecar.json",
    "near_energy_source_sidecar.json", "single_point_gap_proposals.json", "cell_precision_review_note.json",
]


def run():
    context = load_json_object(OUT / "request_context.json")
    after = frozen_hashes()
    guards = {"frozen_12_inputs_unchanged": after == context["frozen_hashes_before"]}
    for name, path, key in [
        ("current_task_unchanged", ROOT / "tasks/current_task.md", "current_task_sha256"),
        ("backend_policy_unchanged", ROOT / "configs/execution_backends.yaml", "backend_policy_sha256"),
        ("training536_request_unchanged", BASE / "training536_smoke_20261113_v1/package/control/training_request.json", "training_request_sha256"),
    ]:
        guards[name] = sha256_file(path) == context[key]
    queue = deque(OUT / name for name in CANONICAL)
    seen, digests, failures = set(), {}, []
    edges = 0
    while queue:
        artifact = queue.popleft()
        if artifact in seen:
            continue
        seen.add(artifact)
        for item in load_json_object(artifact).get("source_files", []):
            source = Path(item["path"])
            edges += 1
            if source not in digests:
                digests[source] = sha256_file(source) if source.is_file() else None
            if digests[source] != item["sha256"]:
                failures.append({"artifact": str(artifact), "source": str(source),
                                 "expected_sha256": item["sha256"], "actual_sha256": digests[source]})
            if source.parent == OUT and source.suffix == ".json" and source not in seen:
                queue.append(source)
    reactions = load_json_object(OUT / "reaction_source_sidecar.json")
    protected = [r for r in reactions["C_H_static_labels"] if r["protected_TS_validation"]]
    catalog = load_json_object(OUT / "energy_reuse_catalog_v2.json")["records"]
    guards["six_TS_validation_labels_stay_reserved"] = len(protected) == 6 and all(
        r["new_energy_training_admission"] is False for r in protected)
    guards["no_train_protected_label_overlap"] = not any(r["train_and_protected_conflict"] for r in catalog)
    guards["no_energy_training_admission"] = not any(r["training_admission"] for r in catalog)
    passed = all(guards.values()) and not failures
    receipt = {"status": "PASS" if passed else "FAIL", "guards": guards,
               "binding_artifacts": len(seen), "binding_edges": edges, "unique_source_files_hashed": len(digests),
               "binding_failures": failures, "frozen_hashes_after": after,
               "new_training_DFT_optimization_or_scheduler_actions": 0,
               "source_files": source_file_manifest([OUT / name for name in [*CANONICAL, "request_context.json"]] + [Path(__file__)])}
    write_json_exclusive(OUT / "final_verification.json", receipt)
    print({key: value for key, value in receipt.items() if key not in ("source_files", "frozen_hashes_after")})
    if not passed:
        raise RuntimeError("read-only audit verification failed; inspect receipt without changing frozen inputs")


if __name__ == "__main__":
    run()
