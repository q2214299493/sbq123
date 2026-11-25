"""Bounded NO constrained-composition recovery for the reviewed synthetic Ni/Cu pilot."""

import argparse
from math import isclose
from pathlib import Path
import re

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_cross_reaction import run_verified, verify_members
from scripts.baseline_mkm.pressure_perturbation import checked_feed
from scripts.baseline_mkm.sensitivity_inputs import FIXED_TOTAL


PREVIOUS = pair.REPORTS / "phase3_2_2"
LABEL = "NO constrained-composition reaction order"
LIMITS = dict(max_runs=4, per_run_s=210, native_s=840, wall_s=960, max_parallel=1, max_retries=0)


def archived_grid():
    source = PREVIOUS / "completion.md"
    event = read(pair.REPORTS.parents[1] / "modules/state_handoff/events/history-phase322-native-checkpoint-20261120.json")
    saved = {r["locator"]: r["sha256"] for r in event["evidence"]}
    if sha256_file(source) != saved["reports/multiphase/phase3_2_2/completion.md"]:
        raise ValueError("Changed archived pressure candidates")
    rows = re.findall(r"^\| ([+−-]0\.0[24]) \| ([.\d]+) \| ([.\d]+) \| ([.\d]+) \|", source.read_text(encoding="utf-8"), re.M)
    grid = {float(step.replace("−", "-")): dict(zip(("H2-g", "HNO-g", "NO-g"), map(float, values), strict=True))
            for step, *values in rows}
    if len(rows) != 4 or set(grid) != {0.04, -0.04, 0.02, -0.02}:
        raise ValueError("Missing or ambiguous archived pressure pair")
    return grid, sha256_file(source)


def frozen_pressures(input_text):
    rows = re.findall(r"^P_(\w+)_FROZ\s*=\s*([\d.eE+-]+);\s*$", input_text, re.M)
    gases = {name + "-g": float(value) for name, value in rows}
    if not gases or len(gases) != len(rows):
        raise ValueError("Missing or duplicate native pressure assignments")
    return gases


def prepare(root, base):
    parent, _ = pair.baseline(base)
    baseline_feed = parent["partial_pressures_bar"]
    grid, source_hash = archived_grid()
    jobs = {}
    for name, step in (("coarse", 0.04), ("fine", 0.02)):
        targets = {label: grid[step * sign] for label, sign in pair.SIGNS}
        basis = dict(observable=LABEL, size=name, baseline_run_id=parent["run_id"],
                     baseline_result_sha256=parent["result_sha256"], parent_input_hashes=parent["input_hashes"],
                     archived_candidates_sha256=source_hash, remaining_H2_HNO_ratio=10, fixed_total_bar=1.6,
                     expected_validation="Positive MAT components exactly match grid, exact fixed total and proportional remainder",
                     budget=LIMITS)
        spec = dict(kind="gas_order", species_id="NO-g", constraint=FIXED_TOTAL, step=step,
                    composition_grid=targets, review_basis=basis)
        for label, sign in pair.SIGNS:
            feed = targets[label]
            actual = checked_feed(baseline_feed, feed, "NO-g", 1.6)
            if any(float(format(v, ".5g")) != v for v in feed.values()) or not isclose(actual, sign * step, rel_tol=0.005):
                raise ValueError("Candidate is outside the archived native precision or displacement")
        part = pair.prepare_members(root / name, base, parent, {"sensitivity": spec})
        for label, sign in pair.SIGNS:
            run = pair.check_member(root / name, base, label, sign)
            if frozen_pressures((run / "input" / pair.point.INPUT).read_text()) != targets[label]:
                raise ValueError("Generated native feed differs from archived target")
        jobs[name] = dict(pair_sha256=sha256_json(part), members=part["members"])
    study = dict(format="mkm-composition-recovery/1", observable=LABEL, limits=LIMITS, jobs=jobs,
                 baseline_sha256=parent["result_sha256"], archived_candidates_sha256=source_hash)
    pair.put(root / "study.json", study)
    return study


def execute(root, base, decisions):
    study = prepare(root, base)
    if decisions["study_sha256"] != sha256_json(study) or set(decisions["decisions"]) != set(study["jobs"]):
        raise ValueError("Recovery approvals do not match this study")
    approvals = {}
    for name in study["jobs"]:
        files = decisions["decisions"][name]
        if set(files) != {"plus", "minus"}:
            raise ValueError("Independent positive and negative approvals required")
        approvals[name] = {k: Path(v) for k, v in files.items()}
        verify_members(root / name, base, read(root / name / "pair.json"), approvals[name], finished=(root / "finished.json").exists())
    return run_verified(root, base, sha256_json(study), list(study["jobs"]), approvals, LIMITS["wall_s"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute"))
    parser.add_argument("root", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("approvals", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root.resolve(), args.baseline.resolve())
    elif args.approvals is None:
        parser.error("execute requires four individual approvals")
    else:
        execute(args.root.resolve(), args.baseline.resolve(), read(args.approvals))
