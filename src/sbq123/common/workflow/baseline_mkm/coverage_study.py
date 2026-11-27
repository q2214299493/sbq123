"""Bounded external coverage iteration around the approved fixed-parameter CATKINAS point."""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.coverage_energy import ExcessGibbs
from scripts.baseline_mkm.coverage_ts import validate_record
from scripts.baseline_mkm.coverage_feedback import assess_step, compare_roots
from scripts.baseline_mkm.normalization import normalization
from scripts.baseline_mkm.steady_states import check_policy, observe
from scripts.multiphase_contracts import decode_unique_json, read_unique_json as read
from scripts.scientific_validation import finite_number


def check_request(request, model):
    validate_record(request, "coverage_study_request")
    check_policy(request["root_tolerances"])
    policy = request["iteration"]
    for key, value in policy.items():
        finite_number(value, key, positive=True)
    branches = request["branches"]
    if len({tuple(model.coordinates(b["initial"])) for b in branches}) != len(branches):
        raise ValueError("Supply distinct initial branches")
    for b in branches:
        if type(b["max_calls"]) is not int:
            raise ValueError("Invalid branch budget")
    if type(request["max_total_calls"]) is not int or sum(b["max_calls"] for b in branches) > request["max_total_calls"]:
        raise ValueError("Independent branch reservations exceed total call budget")


def create(root, request, network, dataset, configuration, fit, tickets, ticket_id, matlab, profile=None):
    sources = dict(network=network, dataset=dataset, configuration=configuration, fit=fit)
    raw = {k: p.read_bytes() for k, p in sources.items()}
    n, d, c = [decode_unique_json(raw[k]) for k in ("network", "dataset", "configuration")]
    model = ExcessGibbs(n, d, raw["fit"].decode("utf-8"))
    spec = read(request)
    check_request(spec, model)
    if c["dataset_version"] != d["dataset_version"]:
        raise ValueError("Configuration does not bind parent kinetic dataset")
    for branch in spec["branches"]:
        initial = branch["initial"]
        child = model.child(initial)
        point.qualify(n, child, config_at(c, child, initial))
    rt = point.tools_for_run(matlab)
    ticket = point.ticket_binding(tickets, ticket_id)
    ref = normalization(profile, n, c)
    check_reference(model, ref)
    root.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for k, content in raw.items():
        path = root / (k + ".json")
        with path.open("xb") as stream:
            stream.write(content)
        hashes[k] = sha256_file(path)
    manifest = dict(
        format="mkm-coverage-manifest/1",
        request=spec,
        hashes=hashes,
        ticket=ticket,
        maximum_native_seconds=point.LIMIT * sum(b["max_calls"] for b in spec["branches"]),
        tickets=str(tickets.resolve()),
        runtime=rt,
        matlab=str(matlab.resolve()),
        normalization=ref,
        profile=str(profile.resolve()) if profile else None,
        profile_sha256=sha256_file(profile) if profile else None,
    )
    path = write_json_exclusive(root / "study.json", manifest)
    return dict(study=str(path), sha256=sha256_file(path))


def check_reference(model, reference):
    if reference and reference["reference_id"] == model.fit["reference_id"]:
        if reference["sites_per_reference"] != model.fit["capacities"]:
            raise ValueError("One reference identity cannot have two inventory capacities")
        scale = 1 / reference["denominator_value"]
        for row in model.fit["reactions"].values():
            factor = row["native_events_per_reference"]
            if factor is not None and not math.isclose(factor, scale, rel_tol=1e-12):
                raise ValueError("Native extent conversion conflicts with reviewed normalization")


def config_at(parent, child, initial):
    config = deepcopy(parent)
    config["dataset_version"] = child["dataset_version"]
    config["catkinas"]["initial_coverages"] = initial.copy()
    return config


def immutable_record(path, value):
    try:
        write_json_exclusive(path, value)
    except FileExistsError:
        if read(path) != value:
            raise ValueError(f"Changed immutable record {path.name}") from None
    return path


def checked_point(plan, manifest, run, model, child, config):
    if (
        plan["runtime"] != manifest["runtime"]
        or plan["normalization"] != manifest["normalization"]
        or plan["normalization_profile_sha256"] != manifest["profile_sha256"]
        or plan["ticket_id"] != manifest["ticket"]["ticket_id"]
        or plan["question_id"] != manifest["ticket"]["question_id"]
        or plan["run_directory"] != str(run.resolve())
        or plan["run_id"] != run.name
    ):
        raise ValueError("Point identity differs from study")
    for name, expected in (("network", model.network), ("dataset", child), ("configuration", config)):
        path = run / (name + ".json")
        if sha256_file(path) != plan["input_hashes"][name] or read(path) != expected:
            raise ValueError(f"Point {name} differs from reproduced branch")


def member(root, manifest, model, config, name, child, mode, decision):
    run = root / name
    profile = Path(manifest["profile"]) if manifest["profile"] else None
    if not run.exists():
        if mode != "prepare":
            return "NOT_PREPARED", None
        d = immutable_record(root / (name + "-dataset.json"), child)
        c = immutable_record(root / (name + "-configuration.json"), config)
        point.prepare(
            run, root / "network.json", d, c, Path(manifest["tickets"]), manifest["ticket"]["ticket_id"], Path(manifest["matlab"]), profile
        )
    if not (run / "CREATED.json").is_file():
        return "PARTIAL", None
    stage = point.status(run)["stage"]
    if stage not in ("ACCEPTED", "AWAITING_APPROVAL"):
        return stage, None
    plan = read(run / "plan.json")
    checked_point(plan, manifest, run, model, child, config)
    if stage == "AWAITING_APPROVAL" and mode == "execute":
        if decision is None:
            raise ValueError("Supply the independent decision for this point")
        stage = point.execute(run, decision)["stage"]
    if stage != "ACCEPTED":
        return stage, None
    return stage, observe(run, profile)


def evaluate_observation(model, child, obs, config, history, policy):
    try:
        return assess_step(model, child, obs, config, history, policy)
    except (ValueError, KeyError, ArithmeticError) as exc:
        return dict(status="INCONCLUSIVE", reason=str(exc), stability=dict(status="UNKNOWN", reason=str(exc)))


def branch_state(root, manifest, model, config, index, mode, decision, digest):
    spec = manifest["request"]
    branch = spec["branches"][index - 1]
    theta = initial = branch["initial"]
    previous, history = None, []
    for iteration in range(1, branch["max_calls"] + 1):
        name = f"branch-{index:03d}-point-{iteration:03d}"
        try:
            child = model.child(theta, previous, study_sha256=digest)
            run_config = config_at(config, child, initial)
            already_accepted = (root / name / "ACCEPTED.json").is_file()
            stage, obs = member(root, manifest, model, run_config, name, child, mode, decision)
            if stage != "ACCEPTED":
                pending = dict(status=stage, member=name, history=history)
                if stage == "REJECTED":
                    receipt = root / name / "REJECTED.json"
                    pending.update(receipt_sha256=sha256_file(receipt), rejection=read(receipt))
                return pending
            step = evaluate_observation(model, child, obs, config, history, spec["iteration"])
            record = dict(
                format="mkm-coverage-step/1",
                iteration=iteration,
                member=name,
                evaluation_coverage=theta,
                native_initial=initial,
                native_final=obs["coverage"],
                dataset_version=child["dataset_version"],
                fit_sha256=model.digest,
                previous_receipt_sha256=previous,
                observation=obs,
                **step,
            )
            path = root / (name + "-assessment.json")
            if mode != "inspect":
                immutable_record(path, record)
            elif path.exists() and read(path) != record:
                raise ValueError("Stored assessment differs from replay")
            history.append(record)
            if step["status"] != "CONTINUE":
                return dict(status=step["status"], history=history)
            previous, initial, theta = obs["receipt_sha256"], obs["coverage"], step["next_coverage"]
            if mode == "execute" and not already_accepted:
                mode = "inspect"  # one user invocation can consume at most one approved call
        except (ValueError, KeyError, OSError, ArithmeticError) as exc:
            return dict(status="INCONCLUSIVE", member=name, reason=str(exc), history=history)
    return dict(status="BUDGET_EXHAUSTED", history=history)


def advance(path, digest, mode="inspect", branch=None, decision=None):
    if mode not in ("inspect", "prepare", "execute") or sha256_file(path) != digest:
        raise ValueError("Invalid action or study manifest SHA-256")
    manifest = read(path)
    if manifest["format"] != "mkm-coverage-manifest/1":
        raise ValueError("Unknown manifest")
    root = path.parent
    for k in ("network", "dataset", "configuration", "fit"):
        if sha256_file(root / (k + ".json")) != manifest["hashes"][k]:
            raise ValueError(f"Changed study input {k}")
    model = ExcessGibbs(read(root / "network.json"), read(root / "dataset.json"), (root / "fit.json").read_bytes().decode())
    spec, config = manifest["request"], read(root / "configuration.json")
    check_request(spec, model)
    count = len(spec["branches"])
    if mode != "inspect" and (type(branch) is not int or not 1 <= branch <= count):
        raise ValueError("Select exactly one reserved branch")
    states = [
        branch_state(root, manifest, model, config, i, mode if i == branch else "inspect", decision, digest) for i in range(1, count + 1)
    ]
    return dict(
        format="mkm-coverage-assessment/1",
        study_sha256=digest,
        branches=states,
        roots=compare_roots(states, spec["root_tolerances"], model),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("create")
    for k in ("root", "request", "network", "dataset", "configuration", "fit", "tickets", "ticket_id", "matlab"):
        p.add_argument(k, type=str if k == "ticket_id" else Path)
    p.add_argument("--profile", type=Path)
    for action in ("inspect", "prepare", "execute"):
        p = sub.add_parser(action)
        p.add_argument("study", type=Path)
        p.add_argument("sha256")
        if action != "inspect":
            p.add_argument("branch", type=int)
        if action == "execute":
            p.add_argument("decision", type=Path)
    args = vars(parser.parse_args())
    action = args.pop("action")
    result = (
        create(**args) if action == "create" else advance(args["study"], args["sha256"], action, args.get("branch"), args.get("decision"))
    )
    print(json.dumps(result, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
