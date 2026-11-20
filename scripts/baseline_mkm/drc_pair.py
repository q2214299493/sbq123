"""Prepare or execute exactly two approved synthetic TS displacements against an accepted baseline."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import analysis, single_point as point
from scripts.baseline_mkm.ts_perturbation import DELTA_EV, HALF_STEP_EV, PARENT, REACTION, derivative
from scripts.baseline_mkm.sensitivity_inputs import derive
from scripts.execution_permission import require_bound_action
from scripts.scientific_validation import finite_number

REPORTS = Path(__file__).resolve().parents[2] / "reports/multiphase"
OPTIONS = REPORTS / "phase3_1/benchmark_normalization.json"
BUDGET = 480
SIGNS = (("plus", 1), ("minus", -1))


def accepted(run):
    receipt = point.status(run)
    if receipt["stage"] != "ACCEPTED":
        raise ValueError(f"{run.name}: expected accepted point, found {receipt['stage']}")
    plan = read(run / "plan.json")
    decision = read(run / "approval.json")
    receipt["raw_plan_sha256"] = sha256_json(plan)
    require_bound_action(decision, point.ACTION, receipt["raw_plan_sha256"], {point.ACTION})
    if (
        decision["DECISION"] != "approve"
        or decision["question_id"] != plan["question_id"]
        or not decision["reviewer"]
        or sha256_json(decision) != receipt["approval_reference"]
        or sha256_file(Path(decision["source"]["path"])) != decision["source"]["sha256"]
    ):
        raise ValueError("Changed approval binding")
    for path, digest in receipt["output_hashes"].items():
        if sha256_file(run / path) != digest:
            raise ValueError(f"Changed native evidence: {path}")
    a = analysis.analyze(*(run / (k + ".json") for k in ("network", "dataset", "configuration", "result")), receipt, OPTIONS)
    finite_number(a["tof"]["overall"]["per_site_pair_s"], "positive overall net TOF per site pair", positive=True)
    return receipt, a


def baseline(run):
    receipt, report = accepted(run)
    reference = read(REPORTS / "phase3_0/benchmark_manifest.json")
    for key in (
        "raw_plan_sha256",
        "result_sha256",
        "approval_reference",
        "network_version_id",
        "input_hashes",
        "kinetic_dataset_version",
        "run_id",
        "output_hashes",
    ):
        if receipt[key] != reference[key]:
            raise ValueError(f"Baseline differs from accepted benchmark: {key}")
    if receipt["kinetic_dataset_version"] != PARENT or report != read(REPORTS / "phase3_1/closed_cycle/analysis.json"):
        raise ValueError("Baseline kinetic analysis differs from accepted benchmark")
    return receipt, report


def expected(base, sign, delta_eV=DELTA_EV, reaction_id=REACTION):
    n, d, c = (read(base / (k + ".json")) for k in ("network", "dataset", "configuration"))
    child = derivative(n, d, sign, delta_eV, reaction_id)
    return child, dict(c, dataset_version=child["dataset_version"])


def put(path, data):
    if path.exists():
        if read(path) != data:
            raise ValueError(f"Conflicting immutable artifact: {path}")
    else:
        save(path, data)


def prepare(root, base, delta_eV=DELTA_EV, reaction_id=REACTION):
    parent, _ = baseline(base)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "pair.json").exists() and read(root / "pair.json")["delta_eV"] != delta_eV:
        raise ValueError("Pair directory already belongs to a different step size")
    if (root / "pair.json").exists() and read(root / "pair.json").get("reaction_id", REACTION) != reaction_id:
        raise ValueError("Pair directory already belongs to a different reaction")
    return prepare_members(root, base, parent, {"reaction_id": reaction_id, "delta_eV": delta_eV})


def planned_inputs(base, sign, selection):
    if "sensitivity" in selection:
        inputs = (read(base / (key + ".json")) for key in ("network", "dataset", "configuration"))
        return derive(*inputs, selection["sensitivity"], sign)
    return expected(base, sign, selection["delta_eV"], selection.get("reaction_id", REACTION))


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


def check_member(root, base, label, sign):
    pair = read(root / "pair.json")
    child, config = planned_inputs(base, sign, pair)
    run = root / (label + "-" + child["dataset_version"][:16])
    plan = read(run / "plan.json")
    member = pair["members"][label]
    if member != {"run_id": run.name, "plan_sha256": sha256_json(plan)}:
        raise ValueError("Changed perturbation plan identity")
    if read(run / "dataset.json") != child or read(run / "configuration.json") != config:
        raise ValueError("Changed perturbation dataset or conditions")
    original = read(base / "plan.json")
    if "sensitivity" in pair and pair["sensitivity"]["kind"] == "gas_order":
        original = dict(original, partial_pressures_bar=config["partial_pressure_bar"], total_pressure_bar=config["total_pressure_bar"])
    for key in (
        "question_id",
        "ticket_id",
        "runtime",
        "temperature_K",
        "partial_pressures_bar",
        "total_pressure_bar",
        "use_scope",
        "standard_states",
        "site_inventory",
        "initial_coverages",
        "solver_settings",
        "network_version_id",
    ):
        if plan[key] != original[key]:
            raise ValueError(f"Incompatible pair condition: {key}")
    if plan["input_hashes"]["network"] != original["input_hashes"]["network"]:
        raise ValueError("Changed original network bytes")
    return run


def clock():
    return datetime.now(timezone.utc).timestamp()


def verified_finish(root, manifest):
    finished = read(root / "finished.json")
    elapsed = finite_number(finished["elapsed_s"], "pair elapsed seconds", positive=True)
    remaining = finite_number(finished["remaining_s"], "remaining budget", nonnegative=True)
    if (
        (root / "failed.json").exists()
        or finished["pair_sha256"] != sha256_json(manifest)
        or elapsed > BUDGET
        or abs(remaining - (BUDGET - elapsed)) > 1e-6
    ):
        raise ValueError("No valid completed pair within the budget")
    return finished


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
