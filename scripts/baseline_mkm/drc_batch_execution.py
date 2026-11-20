"""Bind the batch manifest to separate single-point approvals and reuse the bounded pair executor."""

from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_json
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_batch import LIMITS, prepare
from scripts.baseline_mkm.drc_cross_reaction import run_verified, verify_pair
from scripts.baseline_mkm.ts_perturbation import HALF_STEP_EV


def decisions_for_plan(manifest, approvals):
    if approvals.get("batch_plan_sha256") != sha256_json(manifest):
        raise ValueError("Approval index refers to a different batch")
    jobs = manifest["jobs"]
    if (
        manifest["limits"] != LIMITS
        or 2 * len(jobs) > LIMITS["max_runs"]
        or 2 * len(jobs) * pair.point.LIMIT > LIMITS["native_s"]
        or pair.point.LIMIT != LIMITS["per_run_s"]
    ):
        raise ValueError("Unbounded batch or native runtime")
    if set(approvals["decisions"]) != set(jobs):
        raise ValueError("Every scheduled pair requires separate approvals")
    decisions = {}
    for rid, job in jobs.items():
        paths = approvals["decisions"][rid]
        if set(paths) != {"plus", "minus"}:
            raise ValueError(f"{rid} requires both signed approvals")
        decisions[job["directory"]] = {label: Path(p) for label, p in paths.items()}
    if len({p.resolve() for row in decisions.values() for p in row.values()}) != 2 * len(jobs):
        raise ValueError("Duplicate approval paths")
    return decisions


def execute(root, base, approvals):
    manifest = read(root / "batch-plan.json")
    decisions = decisions_for_plan(manifest, approvals)
    if not decisions:
        return {"actual_new_runs": 0}
    # Regenerate from current baseline and verify every prior native receipt before using a plan.
    prepare(root, base, manifest["reuse_sources"])
    for rid, job in manifest["jobs"].items():
        directory = job["directory"]
        digest = verify_pair(
            root / directory,
            base,
            rid,
            HALF_STEP_EV,
            manifest["baseline_hashes"]["result"],
            decisions[directory],
            finished=(root / "finished.json").exists(),
        )
        if digest != job["pair_sha256"]:
            raise ValueError(f"{rid}: changed pair plan")
    return run_verified(root, base, sha256_json(manifest), list(decisions), decisions, LIMITS["wall_s"])
