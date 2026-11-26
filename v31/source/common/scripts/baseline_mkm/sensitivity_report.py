"""Report independent native TOF derivatives and response matrices, retaining unknowns on partial studies."""

from datetime import datetime
from math import log

from scripts.artifact_io import load_json_object as read, sha256_json
from scripts.baseline_mkm import drc_pair_records as pair
from scripts.baseline_mkm.drc_report import archive_members, directional_audit, evidence, write_once
from scripts.baseline_mkm.drc_step_size import project_tolerance
from scripts.baseline_mkm.sensitivity_plan import LIMITS, specifications
from scripts.baseline_mkm.single_point_result import check_close
from scripts.scientific_validation import finite_number
from scripts.physical_constants import KB


def estimates(baseline, plus, minus, spec, temperature):
    r0, rp, rm = (log(finite_number(v, "positive overall TOF", positive=True)) for v in (baseline, plus, minus))
    step = finite_number(spec["step"], "positive step", positive=True)
    if spec["kind"] not in ("intermediate_G", "gas_order"):
        raise ValueError("Unknown observable")
    scale = KB * finite_number(temperature, "temperature", positive=True) if spec["kind"] == "intermediate_G" else 1.0
    return dict(central=scale * (rp - rm) / (2 * step), positive_side=scale * (rp - r0) / step, negative_side=scale * (r0 - rm) / step)


def step_comparison(coarse, fine):
    if coarse is None or fine is None:
        return dict(status="unavailable", absolute_change=None, tolerance=None)
    difference = abs(coarse - fine)
    tolerance = project_tolerance(fine)
    return dict(status="stable" if difference <= tolerance else "unstable", absolute_change=difference, tolerance=tolerance)


def response(base, case):
    return dict(
        coverage={k: v - base["coverage"][k] for k, v in case["coverage"].items()},
        vacancy={k: v - base["vacancies"][k] for k, v in case["vacancies"].items()},
        flux={
            rid: {k: row[k] - base["rates"][rid][k] for k in ("forward_flux", "reverse_flux", "net_flux")}
            for rid, row in case["rates"].items()
        },
    )


def case_record(run, baseline, spec):
    receipt, a = pair.accepted(run)
    data = read(run / "dataset.json")
    info = data["sensitivity_perturbation"]
    if (a.get("native_reference", a["normalization"]) != baseline.get("native_reference", baseline["normalization"])
            or a["tof"]["overall_stoichiometry"] != baseline["tof"]["overall_stoichiometry"]):
        raise ValueError("Changed turnover normalization")
    case = evidence(run, receipt, a)
    case.update(perturbation=info, partial_pressures_bar=a["partial_pressures_bar"], total_pressure_bar=receipt["total_pressure_bar"])
    case["elementary_rate_laws"] = {row["reaction_id"]: directional_audit(data, a, row["reaction_id"]) for row in data["reactions"]}
    if spec["kind"] == "gas_order":
        sid = spec["species_id"]
        actual = log(case["partial_pressures_bar"][sid] / baseline["partial_pressures_bar"][sid])
        check_close(actual, info["sign"] * spec["step"], "selected log pressure displacement")
    return case


def pair_result(directory, base, baseline, original, job, output):
    manifest = read(directory / "pair.json")
    if sha256_json(manifest) != job["pair_sha256"] or manifest["sensitivity"] != job["spec"]:
        raise ValueError("Stale sensitivity pair binding")
    spec = job["spec"]
    runs, stages = {}, {}
    for label, sign in pair.SIGNS:
        run = pair.check_member(directory, base, label, sign)
        runs[label] = run
        stage = pair.point.status(run)["stage"]
        seconds = None
        if (run / "COLLECTING.json").exists():
            start, end = (datetime.fromisoformat(read(run / (k + ".json"))["timestamp"]) for k in ("RUNNING", "COLLECTING"))
            seconds = (end - start).total_seconds()
        stages[label] = dict(stage=stage, attempted=(run / "RUNNING.json").exists(), native_s=seconds)
    if (directory / "failed.json").exists() or not (directory / "finished.json").exists():
        return dict(
            spec=spec,
            stages=stages,
            estimates=None,
            failure=read(directory / "failed.json") if (directory / "failed.json").exists() else None,
        )
    finish = pair.verified_finish(directory, manifest)
    cases = {label: case_record(run, baseline, spec) for label, run in runs.items()}
    values = {}
    for k in ("net_tof_per_site_pair_s", "product_based_tof_per_site_pair_s"):
        values[k] = estimates(original[k], cases["plus"][k], cases["minus"][k], spec, baseline["temperature_K"])
    calc, independent = values.values()
    for k in calc:
        check_close(calc[k], independent[k], "independent " + k)
    output.mkdir(parents=True, exist_ok=True)
    archive_members(directory, base, output, "sensitivity")
    return dict(
        spec=spec,
        stages=stages,
        cases=cases,
        estimates=calc,
        product_based_estimates=independent,
        budget=finish,
        response_matrix={label: response(original, c) for label, c in cases.items()},
    )


def render(result):
    lines = [
        "# Sensitivity and reaction-order comparison",
        "",
        "TOF is the positive net overall turnover per reference Ni/Cu site pair per second.",
        f"Baseline TOF: {result['baseline']['net_tof_per_site_pair_s']:.10g}.",
        "",
        "| Observable | Species | Step | Raised TOF | Lowered TOF | Central | Positive side | Negative side |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["pairs"].items():
        calc = row["estimates"]
        spec = row["spec"]
        if calc is None:
            lines.append(f"| {name} | {spec['species_id']} | {spec['step']} | — | — | unavailable | — | — |")
            continue
        p, m = (row["cases"][k]["net_tof_per_site_pair_s"] for k in ("plus", "minus"))
        lines.append(
            f"| {name} | {spec['species_id']} | {spec['step']} | {p:.9g} | {m:.9g} | "
            f"{calc['central']:.9g} | {calc['positive_side']:.9g} | {calc['negative_side']:.9g} |"
        )
    lines.extend(["", "## Step convergence", ""])
    for kind, item in result["step_comparison"].items():
        lines.append(f"- {kind}: {item['status']}; absolute change {item['absolute_change']}, tolerance {item['tolerance']}.")
    lines += ["", "## Coverage response", "", "| Pair | Sign | Species | Coverage change |", "|---|---|---|---:|"]
    for name, row in result["pairs"].items():
        for label, response_row in row.get("response_matrix", {}).items():
            for sid, value in response_row["coverage"].items():
                lines.append(f"| {name} | {label} | {sid} | {value:.9g} |")
    lines.extend(["", "## Thermodynamic and pressure perturbations", ""])
    for name, row in result["pairs"].items():
        for label, c in row.get("cases", {}).items():
            p = c["perturbation"]
            if "affected" in p:
                lines.append(
                    f"- {name} {label}: G changes from {p['identity']['formation_G_eV']:.6g} to {p['derived_formation_G_eV']:.6g} eV."
                )
                for rid, change in p["affected"].items():
                    g = change["derived_gibbs_eV"]
                    lines.append(
                        f"  - {rid}: reaction {g['reaction']:.6g}, forward {g['forward']:.6g}, reverse {g['reverse']:.6g}, absolute TS {change['absolute_TS_G_eV']:.6g} eV."
                    )
            else:
                feed = ", ".join(f"{k}={v:.8g}" for k, v in p["feed_bar"].items())
                lines.append(f"- {name} {label}: {p['constraint']}, {feed} bar, total {p['total_bar']:.8g} bar.")
    lines.extend(
        [
            "",
            "Per-sign elementary pressure orders, forward and reverse fluxes, site balances and native detailed-balance residuals are stored with the corresponding case in [result.json](result.json).",
        ]
    )
    return "\n".join(lines) + "\n"


def publish(root, base, output):
    manifest = read(root / "study.json")
    receipt, baseline = pair.baseline(base)
    if (
        manifest["baseline_hashes"] != baseline["source_hashes"]
        or manifest["limits"] != LIMITS
        or dict(specifications(manifest["experiments"])) != {k: j["spec"] for k, j in manifest["jobs"].items()}
    ):
        raise ValueError("Changed study scope, baseline or budget")
    original = evidence(base, receipt, baseline)
    output.mkdir(exist_ok=True, parents=True)
    pairs = {k: pair_result(root / k, base, baseline, original, j, output / k) for k, j in manifest["jobs"].items()}
    comparisons = {}
    for kind in manifest["experiments"]:
        coarse, fine = (pairs[kind + "-" + size]["estimates"] for size in ("coarse", "fine"))
        comparisons[kind] = step_comparison(coarse and coarse["central"], fine and fine["central"])
    finish = read(root / "finished.json") if (root / "finished.json").exists() else None
    stages = [v for p in pairs.values() for v in p["stages"].values() if v["attempted"]]
    times = [v["native_s"] for v in stages if v["native_s"] is not None]
    if len(stages) > 8 or sum(times) > LIMITS["native_s"] or any(not 0 <= v <= LIMITS["per_run_s"] for v in times):
        raise ValueError("Native budget exceeded")
    if finish and (
        finish["pairs_sha256"] != sha256_json(manifest)
        or not 0 < finish["elapsed_s"] <= LIMITS["wall_s"]
        or any(p["estimates"] is None for p in pairs.values())
    ):
        raise ValueError("Invalid sensitivity completion")
    result = dict(
        format="mkm-sensitivity-result/1",
        complete=bool(finish),
        scope="synthetic_benchmark",
        study_sha256=sha256_json(manifest),
        temperature_K=baseline["temperature_K"],
        baseline=original,
        normalization=baseline["normalization"],
        pairs=pairs,
        step_comparison=comparisons,
        attempted_runs=len(stages),
        native_s=sum(times) if len(stages) == len(times) else None,
        wall_s=finish["elapsed_s"] if finish else None,
    )
    pair.put(output / "result.json", result)
    write_once(output / "comparison.md", render(result).encode())
    write_once(output / "study.json", (root / "study.json").read_bytes())
    return result
