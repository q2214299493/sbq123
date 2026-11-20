"""Run two preapproved step sizes for one selected synthetic reaction, with a shared clock."""

import argparse
from pathlib import Path
from time import monotonic

from scripts.artifact_io import load_json_object as read, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.ts_perturbation import DELTA_EV, HALF_STEP_EV
from scripts.scientific_validation import finite_number

STEPS = (("coarse", DELTA_EV), ("fine", HALF_STEP_EV))
TOTAL = 2 * pair.BUDGET


def verified_plans(root, base, reaction_id, decisions):
    parent, _ = pair.baseline(base)
    manifest = {}
    for name, step in STEPS:
        directory = root / name
        plan = read(directory / "pair.json")
        if (plan["reaction_id"], plan["delta_eV"], plan["baseline_result_sha256"]) != (
            reaction_id, step, parent["result_sha256"]
        ):
            raise ValueError("Mismatched reaction, step or baseline")
        if (directory / "failed.json").exists():
            raise ValueError(f"{name} pair previously failed")
        for label, sign in pair.SIGNS:
            member = pair.check_member(directory, base, label, sign)
            state = pair.point.status(member)["stage"]
            if state == "AWAITING_APPROVAL" and not (root / "finished.json").exists():
                pair.point.preflight(member, decisions[name][label])
            elif state == "ACCEPTED":
                pair.accepted(member)
            else:
                raise ValueError(f"{name}/{label}: retained {state}; no retry")
        manifest[name] = sha256_json(plan)
    return sha256_json(manifest)


def run(root, base, reaction_id, decisions):
    digest = verified_plans(root, base, reaction_id, decisions)
    start = root / "started.json"
    if not start.exists():
        if any((root / name / "started.json").exists() for name, _ in STEPS):
            raise ValueError("Existing pair lacks its cross-reaction budget clock")
        save(start, {"pairs_sha256": digest, "utc_epoch_s": pair.clock()})
    record = read(start)
    elapsed = pair.clock() - finite_number(record["utc_epoch_s"], "start epoch", positive=True)
    if elapsed < 0 or record["pairs_sha256"] != digest:
        raise ValueError("Stale cross-reaction clock or plan")
    finish = root / "finished.json"
    if finish.exists():
        result = read(finish)
        if result["pairs_sha256"] != digest or not 0 < result["elapsed_s"] <= TOTAL:
            raise ValueError("Invalid cross-reaction finish receipt")
        for name, _ in STEPS:
            pair.verified_finish(root / name, read(root / name / "pair.json"))
        return result
    deadline = monotonic() + TOTAL - elapsed
    for name, _ in STEPS:
        if monotonic() >= deadline:
            raise TimeoutError("Cross-reaction budget exhausted")
        pair.run_pair(root / name, base, decisions[name], campaign_deadline=deadline)
    elapsed = TOTAL - (deadline - monotonic())
    if elapsed > TOTAL:
        raise TimeoutError("Cross-reaction budget exceeded")
    result = dict(pairs_sha256=digest, elapsed_s=elapsed, total_budget_s=TOTAL)
    save(finish, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("root", "baseline"):
        parser.add_argument(field, type=Path)
    parser.add_argument("reaction_id")
    parser.add_argument("approvals", nargs=4, type=Path, help="coarse +, coarse -, fine +, fine -")
    args = parser.parse_args()
    approvals = iter(args.approvals)
    decisions = {name: {label: next(approvals) for label, _ in pair.SIGNS} for name, _ in STEPS}
    print(run(args.root.resolve(), args.baseline.resolve(), args.reaction_id, decisions))
