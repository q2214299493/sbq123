"""Prepare independent CATKINAS points and compare receipt-verified steady states offline."""
import argparse
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import re

import numpy as np

from scripts.kinetic_data.stoichiometric_sources import build_matrices
from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.analysis import analyze
from scripts.baseline_mkm.normalization import normalization
from scripts.baseline_mkm.results import read_initial_coverages, read_single_point
from scripts.multiphase_contracts import decode_unique_json, read_unique_json as read
from scripts.scientific_validation import finite_number

GROUPS = ("coverage", "vacancy", "net_rate", "tof")
SINGLE = "SINGLE_STEADY_STATE_OBSERVED"
MULTIPLE = "MULTIPLE_STEADY_STATES_OBSERVED"
UNKNOWN = "INCONCLUSIVE"


def fixed_config(config):
    fixed = deepcopy(config)
    del fixed["catkinas"]["initial_coverages"]
    return sha256_json(fixed)


def check_policy(policy):
    fields = {*GROUPS, "relative", "max_residual", "separation_factor"}
    if set(policy) != fields | {"format"} or policy["format"] != "mkm-steady-tolerances/1":
        raise ValueError("Expected explicit mkm-steady-tolerances/1 thresholds")
    for key in fields:
        if type(policy[key]) not in (int, float):
            raise ValueError(f"Expected numeric tolerance for {key}")
        finite_number(policy[key], key, nonnegative=True)
    if policy["separation_factor"] <= 1 or policy["relative"] >= 1:
        raise ValueError("Require separation_factor > 1 and relative < 1")


def prepare(root, request, network, dataset, configuration, tickets, ticket_id, matlab, profile=None):
    network_bytes, dataset_bytes = network.read_bytes(), dataset.read_bytes()
    n, d = map(decode_unique_json, (network_bytes, dataset_bytes))
    spec, c = map(read, (request, configuration))
    if spec["format"] != "mkm-initial-states/1" or (spec["network_version"], spec["dataset_version"]) != (
        n["network_version"], d["dataset_version"]
    ):
        raise ValueError("Initial-state request differs from model versions")
    check_policy(spec["tolerances"])
    states = spec["initial_coverages"]
    if not isinstance(states, list) or len(states) < 2:
        raise ValueError("Supply at least two explicit initial coverage maps")
    ref = normalization(profile, n, c)
    configs, members, seen = [], [], set()
    for index, state in enumerate(states, 1):
        if not isinstance(state, dict) or any(type(x) not in (int, float) for x in state.values()):
            raise ValueError("Supply a numeric fraction for each surface species")
        cfg = deepcopy(c)
        cfg["catkinas"]["initial_coverages"] = state
        # The existing renderer validates species, inventory, fixed coverage and native footprint support.
        _, adapter = point.qualify(n, d, cfg)
        native_hash = adapter["files"][point.INPUT]
        key = tuple(sorted(state.items()))
        if key in seen:
            raise ValueError("Repeated initial state")
        seen.add(key)
        members.append(dict(run=f"point-{index:03d}", initial_coverages=state, native_input_sha256=native_hash))
        configs.append(cfg)
    root.mkdir(parents=True, exist_ok=False)
    network, dataset = root / "network.json", root / "dataset.json"
    for path, raw in ((network, network_bytes), (dataset, dataset_bytes)):
        with path.open("xb") as stream:
            stream.write(raw)
    manifest = dict(format="mkm-steady-study/1", network_sha256=sha256_file(network), dataset_sha256=sha256_file(dataset),
                    fixed_config_sha256=fixed_config(c), normalization=ref, tolerances=spec["tolerances"], members=members)
    path = save(root / "study.json", manifest)
    stages = {}
    for member, cfg in zip(members, configs, strict=True):
        name = member["run"]
        cfg_path = save(root / (name + ".json"), cfg)
        stages[name] = point.prepare(root / name, network, dataset, cfg_path, tickets, ticket_id, matlab, profile)["stage"]
    return dict(study=str(path), study_sha256=sha256_file(path), stages=stages)


def observe(run, profile=None):
    receipt = point.accepted_receipt(run)
    if receipt["exit_code"] != 0 or not set(point.NATIVE_OUTPUTS) <= receipt["output_hashes"].keys():
        raise ValueError("Incomplete native process or output evidence")
    n, d, c, result = [run / (key + ".json") for key in ("network", "dataset", "configuration", "result")]
    config, dataset, recorded = map(read, (c, d, result))
    files, adapter = point.qualify(read(n), dataset, config)
    native_text = files[point.INPUT]
    input_hash = sha256_bytes(native_text.encode())
    directory = run / "runtime/result_phase25"
    if not (input_hash == receipt["native_input_hashes"][point.INPUT] == sha256_file(run / "input" / point.INPUT)
            == receipt["output_hashes"]["runtime/result_phase25/Input_phase25_1"]
            == sha256_file(directory / "Input_phase25_1")):
        raise ValueError("Native input or echo differs from reconstructed model")
    log = (directory / "log1").read_bytes().decode("ascii", errors="replace")
    mat = directory / "data1.mat"
    actual = read_initial_coverages(mat, log)
    expected = {s: float(v) for s, v in re.findall(r"^(Q\w+)_INIT = ([^;]+);$", native_text, re.M)}
    if not expected or actual != expected:
        raise ValueError("Native MAT yInits differs from approved initial coverages or vacancies")
    replay = point.validate_result(dataset, config, adapter["validation"], read_single_point(mat, directory / "log1"),
                                   log, native_text, reference=recorded.get("normalization"),
                                   legacy_replay="normalization" not in recorded)
    if any(recorded[k] != v for k, v in replay.items()):
        raise ValueError("Recorded observables differ from native MAT replay")
    a = analyze(n, d, c, result, receipt, profile)
    tof = a["tof"]["extent_per_reference_s"]
    if config.get("turnover_basis") and (a["native_reference"] is None or tof is None):
        raise ValueError("Requested TOF lacks a qualified reference or overall extent")
    return dict(execution_id=receipt["raw_plan_sha256"],
                mat_sha256=receipt["output_hashes"]["runtime/result_phase25/data1.mat"],
                log_sha256=receipt["output_hashes"]["runtime/result_phase25/log1"],
                run=receipt["run_id"], plan_sha256=receipt["raw_plan_sha256"], receipt_sha256=sha256_file(run / "ACCEPTED.json"),
                result_sha256=receipt["result_sha256"], native_input_sha256=input_hash, initial_coverages=config["catkinas"]["initial_coverages"],
                native_initial=actual, network_sha256=sha256_file(n), dataset_sha256=sha256_file(d),
                fixed_config_sha256=fixed_config(config), normalization=a["native_reference"],
                runtime=[receipt["runtime"]["catkinas"]["sha256"], receipt["runtime"]["matlab_sha256"],
                         receipt["catkinas_version"], receipt["matlab_version"]],
                residual=max(replay["steady_state_residual"], a["rates"]["steady_state_residual"]),
                single_point_residual=replay["steady_state_residual"], analysis_residual=a["rates"]["steady_state_residual"],
                coverage={s["species_id"]: s["coverage"] for s in replay["species"] if s["phase"] == "surface"},
                vacancy={s["site_id"]: s["vacancy_fraction"] for s in replay["sites"]},
                net_rate={s["reaction_id"]: s["net_flux"] for s in replay["reactions"]},
                tof={"per_reference_s": tof}, net_rate_unit=a["rates"]["reactions"][0]["flux_unit"])


def compare_pair(left, right, policy):
    """Compare every component symmetrically. Only resolved surface-state separation indicates different roots."""
    differences = []
    distinct = False
    for group in GROUPS:
        x, y = left[group], right[group]
        if not x or x.keys() != y.keys():
            raise ValueError(f"{group} identity set differs or is empty")
        for key, a in x.items():
            b = y[key]
            if group == "tof" and a is None and b is None:
                continue
            delta = finite_number(abs(a - b), group)
            limit = finite_number(policy[group] + policy["relative"] * max(abs(a), abs(b)), "comparison bound")
            if delta > limit:
                differences.append(dict(quantity=group, id=key, delta=delta, tolerance=limit))
                if group in ("coverage", "vacancy") and delta > policy["separation_factor"] * limit:
                    distinct = True
    return dict(runs=[left["run"], right["run"]], differences=differences,
                classification=MULTIPLE if distinct else UNKNOWN if differences else SINGLE)


def root_partition(runs, comparisons):
    """Deduplicate observations only when pairwise agreement is transitive.

    A tolerance chain A~B~C with A distinct from C has no unique partition.
    Different conserved totals cannot establish multiplicity within a class.
    """
    neighbors = {run: {run} for run in runs}
    for pair in comparisons:
        a, b = pair["runs"]
        if pair["classification"] == SINGLE:
            neighbors[a].add(b)
            neighbors[b].add(a)
    groups = sorted({tuple(sorted(group)) for group in neighbors.values()})
    complete = (bool(neighbors) and len(comparisons) == len(neighbors) * (len(neighbors) - 1) // 2
                and all(pair["classification"] in (SINGLE, MULTIPLE) for pair in comparisons)
                and sum(map(len, groups)) == len(neighbors))
    return {"groups": [list(g) for g in groups] if complete else None,
            "distinct_observed_roots": len(groups) if complete else None}


def surface_subspace(network):
    """Project molecular population changes onto the possible surface reaction extents."""
    st = build_matrices([r["definition"] for r in network["reactions"]])
    species = sorted(s["species_id"] for s in network["species"] if s["phase"] == "surface")
    matrix = np.array([[st.species.get(s, {}).get(r, 0) for r in st.reaction_ids] for s in species])
    return species, matrix


def conserved_residual(subspace, left, right):
    species, matrix = subspace
    delta = np.array([left[s] - right[s] for s in species])
    displacement = matrix @ np.linalg.lstsq(matrix, delta, rcond=None)[0]
    return float(np.max(abs(displacement - delta), initial=0))


def compare_starts(network, members, policy):
    subspace = surface_subspace(network)
    pairs = []
    for left, right in combinations(members, 2):
        if conserved_residual(subspace, left["initial_coverages"], right["initial_coverages"]) > 1e-12:
            raise ValueError(f"Different conserved surface totals: {left['run']}, {right['run']}")
        pairs.append(compare_pair(left, right, policy))
    return pairs


def check_independent_execution(member, previous):
    identity = member["execution_id"]
    if not isinstance(identity, str) or not identity.strip() or identity != identity.strip():
        raise ValueError("Invalid execution identity")
    for other in previous:
        if other["execution_id"] == identity:
            raise ValueError("Repeated execution identity")
        if (other["mat_sha256"], other["log_sha256"]) == (member["mat_sha256"], member["log_sha256"]):
            raise ValueError("Repeated MAT/log output pair across executions")


def check_member(member, study, planned):
    for key in ("network_sha256", "dataset_sha256", "fixed_config_sha256", "normalization"):
        if member[key] != study[key]:
            raise ValueError(f"Different {key}")
    for key in ("run", "initial_coverages", "native_input_sha256"):
        if member[key] != planned[key]:
            raise ValueError(f"Different planned {key}")


def assess(path, expected_sha256, profile=None):
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError("Study manifest SHA-256 differs")
    study = decode_unique_json(raw)
    if study["format"] != "mkm-steady-study/1":
        raise ValueError("Unknown study format")
    policy = study["tolerances"]
    check_policy(policy)
    members, gaps, comparisons = [], [], []
    runtime = None
    seen = set()
    for index, planned in enumerate(study["members"], 1):
        name = planned["run"]
        if name != f"point-{index:03d}":
            raise ValueError("Invalid study member identity")
        try:
            run = path.parent / name
            if not (run / "ACCEPTED.json").is_file():
                stage = point.status(run)["stage"] if (run / "CREATED.json").is_file() else "missing"
                raise ValueError(f"Expected ACCEPTED, found {stage}")
            member = observe(run, profile)
            check_member(member, study, planned)
            if runtime is not None and member["runtime"] != runtime:
                raise ValueError("Different solver runtime")
            runtime = member["runtime"]
            state = tuple(sorted(member["initial_coverages"].items()))
            if state in seen:
                raise ValueError("Repeated initial state")
            seen.add(state)
            if finite_number(member["residual"], "steady-state residual", nonnegative=True) > policy["max_residual"]:
                raise ValueError("Residual exceeds study tolerance")
            check_independent_execution(member, members)
            members.append(member)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            gaps.append(dict(run=name, reason=str(exc)))
    if not gaps and len(members) < 2:
        gaps.append(dict(run="comparison", reason="At least two different accepted starts required"))
    if not gaps:
        try:
            network = path.parent / "network.json"
            if sha256_file(network) != study["network_sha256"]:
                raise ValueError("Study network hash differs")
            comparisons = compare_starts(read(network), members, policy)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            gaps.append(dict(run="comparison", reason=str(exc)))
    classes = {p["classification"] for p in comparisons}
    verdict = MULTIPLE if MULTIPLE in classes else SINGLE if classes == {SINGLE} else UNKNOWN
    return dict(format="mkm-steady-state-assessment/1", study_sha256=expected_sha256, tolerances=policy,
                classification=verdict, members=members, blockers=gaps, comparisons=comparisons,
                root_partition=root_partition([m["run"] for m in members] if not gaps else [], comparisons))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for key in ("root", "request", "network", "dataset", "configuration", "tickets"):
        prep.add_argument(key, type=Path)
    prep.add_argument("ticket_id")
    prep.add_argument("matlab", type=Path)
    cmp = commands.add_parser("assess")
    cmp.add_argument("path", type=Path)
    cmp.add_argument("expected_sha256")
    cmp.add_argument("output", type=Path)
    for parser in (prep, cmp):
        parser.add_argument("--normalization", type=Path, dest="profile")
    args = vars(p.parse_args())
    command = args.pop("command")
    if command == "prepare":
        print(json.dumps(prepare(**args), allow_nan=False, indent=2))
    else:
        output = args.pop("output")
        report = assess(**args)
        save(output, report)
        print(report["classification"])


if __name__ == "__main__":
    main()
