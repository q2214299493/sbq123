"""Plan and execute a bounded intermediate-energy and gas-order study on one accepted point."""

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_json
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_cross_reaction import run_verified, verify_members
from scripts.baseline_mkm.sensitivity_inputs import FIXED_OTHERS, FIXED_TOTAL
from scripts.scientific_validation import finite_number

LIMITS = dict(max_runs=8, per_run_s=210, native_s=1680, wall_s=1920, max_parallel=1, max_retries=0)


def specifications(experiments):
    if not experiments or experiments.keys() - {"intermediate_G", "gas_order"}:
        raise ValueError("Select one or both supported observables")
    for kind, experiment in experiments.items():
        coarse, fine = [finite_number(experiment[k], k, positive=True) for k in ("coarse", "fine")]
        if not fine < coarse:
            raise ValueError("Fine step must be smaller than coarse step")
        selected = dict(kind=kind, species_id=experiment["species_id"])
        if kind == "gas_order":
            if experiment.get("constraint") not in (FIXED_OTHERS, FIXED_TOTAL):
                raise ValueError("Explicit gas feed constraint required")
            selected["constraint"] = experiment["constraint"]
        for label, step in (("coarse", coarse), ("fine", fine)):
            yield kind + "-" + label, dict(selected, step=step)


def prepare(root, base, experiments):
    parent, analysis = pair.baseline(base)
    selections = dict(specifications(experiments))
    if 2 * len(selections) * pair.point.LIMIT > LIMITS["native_s"] or pair.point.LIMIT != LIMITS["per_run_s"]:
        raise ValueError("Study exceeds native budget")
    # Validate every condition before materializing any member of the requested study.
    for spec in selections.values():
        for _, sign in pair.SIGNS:
            pair.planned_inputs(base, sign, {"sensitivity": spec})
    jobs = {}
    for name, spec in selections.items():
        plan = pair.prepare_members(root / name, base, parent, {"sensitivity": spec})
        jobs[name] = dict(spec=spec, pair_sha256=sha256_json(plan), members=plan["members"])
    result = dict(
        format="mkm-sensitivity-plan/1",
        limits=LIMITS,
        experiments=experiments,
        jobs=jobs,
        baseline_hashes=analysis["source_hashes"],
        normalization=analysis["normalization"],
        temperature_K=analysis["temperature_K"],
        baseline_pressures_bar=analysis["partial_pressures_bar"],
    )
    pair.put(root / "study.json", result)
    return result


def execute(root, base, approvals):
    plan = read(root / "study.json")
    digest = sha256_json(plan)
    if approvals["plan_sha256"] != digest or set(approvals["decisions"]) != set(plan["jobs"]):
        raise ValueError("Incomplete or stale study approval index")
    prepare(root, base, plan["experiments"])
    decisions = {}
    for name, job in plan["jobs"].items():
        directory = root / name
        d = approvals["decisions"][name]
        if set(d) != {"plus", "minus"}:
            raise ValueError("Separate approval for every signed member required")
        decisions[name] = {k: Path(v) for k, v in d.items()}
        part = read(directory / "pair.json")
        if (
            part["sensitivity"] != job["spec"]
            or part["baseline_result_sha256"] != plan["baseline_hashes"]["result"]
            or sha256_json(part) != job["pair_sha256"]
        ):
            raise ValueError("Changed sensitivity pair")
        verify_members(directory, base, part, decisions[name], finished=(root / "finished.json").exists())
    if len({p.resolve() for v in decisions.values() for p in v.values()}) != 2 * len(decisions):
        raise ValueError("Duplicate single-point approval")
    return run_verified(root, base, digest, list(decisions), decisions, LIMITS["wall_s"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for name, field in (("prepare", "experiments"), ("execute", "approvals"), ("report", "output")):
        cmd = sub.add_parser(name)
        for key in ("root", "baseline", field):
            cmd.add_argument(key, type=Path)
    args = p.parse_args()
    root, base = args.root.resolve(), args.baseline.resolve()
    if args.action == "prepare":
        prepare(root, base, read(args.experiments))
    elif args.action == "execute":
        execute(root, base, read(args.approvals))
    else:
        from scripts.baseline_mkm.sensitivity_report import publish

        publish(root, base, args.output)


if __name__ == "__main__":
    main()
