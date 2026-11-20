"""Reconstruct the constrained-composition response from the native MAT samples."""

import argparse
from datetime import datetime
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_json
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_report import archive_members, directional_audit, evidence
from scripts.baseline_mkm.pressure_perturbation import checked_feed, log_order
from scripts.baseline_mkm.reaction_order import LABEL, LIMITS
from scripts.baseline_mkm.results import read_single_point
from scripts.baseline_mkm.sensitivity_report import response, step_comparison
from scripts.baseline_mkm.single_point_result import check_close


def native_feed(run):
    directory = run / "runtime/result_phase25"
    raw = read_single_point(directory / "data1.mat", directory / "log1")
    return {s.removeprefix("P_") + "-g": v for s, v in raw["partial_pressures_bar"].items()}


def publish(root, base, output):
    study = read(root / "study.json")
    parent, analysis = pair.baseline(base)
    if study["observable"] != LABEL or study["limits"] != LIMITS or parent["result_sha256"] != study["baseline_sha256"]:
        raise ValueError("Changed baseline or recovery scope")
    complete = (root / "finished.json").exists()
    if not complete and not any(root.glob("*/failed.json")):
        raise ValueError("Study has no terminal receipt")
    original = evidence(base, parent, analysis)
    reference = native_feed(base)
    records = {}
    runtimes = []
    for name, job in study["jobs"].items():
        directory = root / name
        plan = read(directory / "pair.json")
        if sha256_json(plan) != job["pair_sha256"]:
            raise ValueError("Changed recovery pair")
        rows, stages = {}, {}
        for label, sign in pair.SIGNS:
            run = pair.check_member(directory, base, label, sign)
            stages[label] = pair.point.status(run)["stage"]
            if (run / "COLLECTING.json").exists():
                start, end = (datetime.fromisoformat(read(run / (s + ".json"))["timestamp"]) for s in ("RUNNING", "COLLECTING"))
                runtimes.append((end - start).total_seconds())
            if stages[label] != "ACCEPTED":
                continue
            receipt, a = pair.accepted(run)
            data = read(run / "dataset.json")
            applied = native_feed(run)
            x = checked_feed(reference, applied, "NO-g", 1.6)
            planned = receipt["composition_review"]["predicted_native_bar"]
            if applied != planned or a["partial_pressures_bar"] != applied or sign * x <= 0:
                raise ValueError("Native feed differs from the approved branch")
            case = evidence(run, receipt, a)
            case.update(actual_pressures_bar=applied, actual_log_step=x, total_bar=1.6, H2_HNO_ratio=applied["H2-g"]/applied["HNO-g"],
                        pressure_residuals_bar={s: applied[s] - planned[s] for s in applied},
                        directions={rid: directional_audit(data, a, rid) for rid in case["rates"]},
                        response=response(original, case))
            rows[label] = case
        estimates = independent = None
        if (directory / "finished.json").exists():
            pair.verified_finish(directory, plan)
            m, p = rows["minus"], rows["plus"]
            pressures = [m["actual_pressures_bar"]["NO-g"], reference["NO-g"], p["actual_pressures_bar"]["NO-g"]]
            def derivative(key):
                return log_order(pressures, [m[key], original[key], p[key]])
            estimates = derivative("net_tof_per_site_pair_s")
            independent = derivative("product_based_tof_per_site_pair_s")
            for k in estimates:
                check_close(estimates[k], independent[k], "independent " + k)
            (output / name).mkdir(parents=True, exist_ok=True)
            archive_members(directory, base, output / name, "composition")
        records[name] = dict(cases=rows, stages=stages, estimates=estimates, independent=independent)
    finish = read(root / "finished.json") if complete else None
    if complete and (len(runtimes) != 4 or finish["pairs_sha256"] != sha256_json(study)
                     or not 0 < finish["elapsed_s"] <= LIMITS["wall_s"] or any(r["estimates"] is None for r in records.values())):
        raise ValueError("Missing completed pairs or invalid wall-clock receipt")
    if any(not 0 < t <= LIMITS["per_run_s"] for t in runtimes) or sum(runtimes) > LIMITS["native_s"]:
        raise ValueError("Recovery native budget exceeded")
    comparison = step_comparison(*(records[n]["estimates"] and records[n]["estimates"]["quadratic_at_zero"] for n in ("coarse", "fine")))
    result = dict(format="mkm-composition-order/1", observable=LABEL, complete=complete, pairs=records,
                  baseline=original, baseline_actual_bar=reference, step_comparison=comparison, study_sha256=sha256_json(study),
                  native_s=sum(runtimes), wall_s=finish["elapsed_s"] if finish else None)
    pair.put(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "baseline", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    publish(args.root.resolve(), args.baseline.resolve(), args.output.resolve())
