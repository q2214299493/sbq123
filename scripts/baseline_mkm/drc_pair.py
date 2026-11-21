"""Prepare or execute exactly two approved synthetic TS displacements against an accepted baseline."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from scripts.artifact_io import load_json_object as read, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.drc_pair_records import (
    BUDGET as BUDGET,
    OPTIONS as OPTIONS,
    REPORTS as REPORTS,
    SIGNS as SIGNS,
    accepted as accepted,
    baseline as baseline,
    check_member as check_member,
    expected as expected,
    planned_inputs as planned_inputs,
    put as put,
    verified_finish as verified_finish,
)
from scripts.baseline_mkm.ts_perturbation import DELTA_EV, HALF_STEP_EV, REACTION
from scripts.scientific_validation import finite_number


def prepare(root, base, delta_eV=DELTA_EV, reaction_id=REACTION):
    parent, _ = baseline(base)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "pair.json").exists() and read(root / "pair.json")["delta_eV"] != delta_eV:
        raise ValueError("Pair directory already belongs to a different step size")
    if (root / "pair.json").exists() and read(root / "pair.json").get("reaction_id", REACTION) != reaction_id:
        raise ValueError("Pair directory already belongs to a different reaction")
    return prepare_members(root, base, parent, {"reaction_id": reaction_id, "delta_eV": delta_eV})


def prepare_members(root, base, parent, selection):
    root.mkdir(parents=True, exist_ok=True)
    members = {}
    for label, sign in SIGNS:
        d, c = planned_inputs(base, sign, selection)
        name = label + "-" + d["dataset_version"][:16]
        child, config = root / (name + ".json"), root / (name + "-configuration.json")
        put(child, d)
        put(config, c)
        run = root / name
        if not run.exists():
            point.prepare(
                run,
                base / "network.json",
                child,
                config,
                Path(parent["ticket_database"]),
                parent["ticket_id"],
                Path(parent["runtime"]["matlab_path"]),
            )
        state = point.status(run)
        if state["stage"] not in {"AWAITING_APPROVAL", "ACCEPTED"}:
            raise ValueError(f"{label}: {state['stage']}: {state.get('missing_data', state.get('reason'))}")
        members[label] = {"run_id": name, "plan_sha256": sha256_json(read(run / "plan.json"))}
    manifest = dict(
        format="sensitivity-pair-plan/1" if "sensitivity" in selection else "drc-pair-plan/1",
        baseline_result_sha256=parent["result_sha256"],
        **selection,
        members=members,
        per_run_timeout_s=point.LIMIT,
        total_budget_s=BUDGET,
        max_retries=0,
        max_parallel=1,
    )
    put(root / "pair.json", manifest)
    return manifest


def clock():
    return datetime.now(timezone.utc).timestamp()


def record_failure(path, label, reason, elapsed):
    put(path, dict(member=label, reason=reason, elapsed_s=elapsed, remaining_s=max(0, BUDGET - elapsed)))


def pair_deadline(root, manifest, runs):
    start = root / "started.json"
    if not start.exists():
        if any((r / "READY.json").exists() for r in runs.values()):
            raise ValueError("Previously claimed perturbation lacks its pair clock")
        save(start, {"utc_epoch_s": clock(), "pair_sha256": sha256_json(manifest)})
    record = read(start)
    started_at = finite_number(record["utc_epoch_s"], "pair start epoch", positive=True)
    elapsed = clock() - started_at
    if record["pair_sha256"] != sha256_json(manifest) or elapsed < 0:
        raise ValueError("Stale pair clock or plan")
    return started_at, monotonic() + BUDGET - elapsed


def run_pair(root, base, decisions, *, campaign_deadline=None):
    parent, _ = baseline(base)
    manifest = read(root / "pair.json")
    if "sensitivity" in manifest and campaign_deadline is None:
        raise ValueError("Sensitivity execution requires a bounded study")
    if manifest["baseline_result_sha256"] != parent["result_sha256"]:
        raise ValueError("Stale baseline binding")
    runs = {label: check_member(root, base, label, sign) for label, sign in SIGNS}
    failure = root / "failed.json"
    if failure.exists():
        raise ValueError(f"Pair previously failed: {read(failure)['reason']}")
    finish = root / "finished.json"
    if finish.exists():
        for run in runs.values():
            accepted(run)
        return verified_finish(root, manifest)
    # Validate both decisions before spending the first second of the execution budget.
    for label, run in runs.items():
        stage = point.status(run)["stage"]
        if stage == "AWAITING_APPROVAL":
            point.preflight(run, decisions[label])
        elif stage == "ACCEPTED":
            accepted(run)
        else:
            raise ValueError(f"{label}: retained {stage}; no retry")
    started_at, deadline = pair_deadline(root, manifest, runs)
    execution_deadline = deadline if campaign_deadline is None else min(deadline, campaign_deadline)
    for label, run in runs.items():
        if monotonic() >= execution_deadline:
            record_failure(failure, label, "total budget exhausted", clock() - started_at)
            raise TimeoutError("Total pair budget exhausted")
        if point.status(run)["stage"] == "AWAITING_APPROVAL":
            state = point.execute(run, decisions[label], deadline=execution_deadline)
            if state["stage"] != "ACCEPTED":
                record_failure(failure, label, state.get("reason", state["stage"]), clock() - started_at)
                raise ValueError(f"{label} failed: {read(failure)['reason']}")
        accepted(run)
    elapsed = BUDGET - (deadline - monotonic())
    if elapsed > BUDGET or (campaign_deadline is not None and monotonic() > campaign_deadline):
        record_failure(failure, "minus", "total budget exceeded", elapsed)
        raise TimeoutError("Total pair budget exceeded")
    completion = dict(elapsed_s=elapsed, remaining_s=BUDGET - elapsed, pair_sha256=sha256_json(manifest))
    put(finish, completion)
    return completion


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for name in ("prepare", "execute", "report"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
        cmd.add_argument("baseline", type=Path)
        if name == "prepare":
            cmd.add_argument("--reaction-id", default=REACTION)
            cmd.add_argument("--delta-eV", type=float, choices=(DELTA_EV, HALF_STEP_EV), default=DELTA_EV)
        if name == "execute":
            for label, _ in SIGNS:
                cmd.add_argument(label + "_approval", type=Path)
        if name == "report":
            cmd.add_argument("--reference-pair", type=Path)
            cmd.add_argument("--reference-result", type=Path)
            cmd.add_argument("output", type=Path)
    a = p.parse_args()
    if a.action == "prepare":
        print(prepare(a.root.resolve(), a.baseline.resolve(), a.delta_eV, a.reaction_id))
    elif a.action == "execute":
        print(run_pair(a.root.resolve(), a.baseline.resolve(), {"plus": a.plus_approval, "minus": a.minus_approval}))
    else:
        from scripts.baseline_mkm.drc_report import publish

        publish(a.root.resolve(), a.baseline.resolve(), a.output, reference_pair=a.reference_pair, reference_result=a.reference_result)


if __name__ == "__main__":
    main()
