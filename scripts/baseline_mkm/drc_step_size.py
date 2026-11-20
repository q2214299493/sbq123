"""Compare two accepted perturbation pairs on the same baseline and physical observable."""

from math import log

from scripts.baseline_mkm.single_point_result import check_close
from scripts.baseline_mkm.ts_perturbation import DELTA_EV, HALF_STEP_EV, central_difference


def summarize(result):
    delta = result["delta_eV"]
    rates = [result["cases"][key]["net_tof_per_site_pair_s"] for key in ("baseline", "plus", "minus")]
    b, p, m = rates
    central = central_difference(*rates, result["temperature_K"], delta)
    check_close(central, result["drc"], "central estimate")
    check_close(central, result["independent_product_drc"], "independent estimate")
    scale = result["kBT_eV"] / delta
    residuals = {}
    for label in ("plus", "minus"):
        case = result["cases"][label]
        residuals[label] = dict(
            steady_state=case["steady_state_residual"],
            site_balance=case["site_residuals"],
            element_balance={e: v["residual"] for e, v in case["element_balance"].items()},
            detailed_balance={rid: v["native_log_balance_residual"] for rid, v in case["rates"].items()},
        )
    return dict(
        delta_eV=delta,
        central=central,
        positive_side=scale * log(b / p),
        negative_side=scale * log(m / b),
        changes_from_baseline=result["changes_from_baseline"],
        residuals=residuals,
    )


def validation(coarse, fine, reference_sha256):
    if (coarse["delta_eV"], fine["delta_eV"]) != (DELTA_EV, HALF_STEP_EV):
        raise ValueError("Expected distinct 0.01 and 0.005 eV pairs")
    for field in ("reaction_id", "scope", "temperature_K", "partial_pressures_bar", "normalization", "observable", "kBT_eV"):
        if coarse[field] != fine[field]:
            raise ValueError(f"Incompatible {field} in step-size comparison")
    if coarse["cases"]["baseline"] != fine["cases"]["baseline"]:
        raise ValueError("Step sizes require identical accepted baseline evidence")
    first, second = summarize(coarse), summarize(fine)
    difference = abs(second["central"] - first["central"])
    tolerance = max(0.002, 0.05 * abs(second["central"]))
    passed = difference <= tolerance
    return dict(
        coarse=first,
        fine=second,
        reference_result_sha256=reference_sha256,
        absolute_difference=difference,
        tolerance=tolerance,
        passed=passed,
        criterion="project tolerance: abs(X_fine - X_coarse) <= max(0.002, 0.05 * abs(X_fine))",
        next_pair_proposal=None
        if passed
        else dict(
            delta_eV=0.0025,
            signs=[1, -1],
            reaction_id=fine["reaction_id"],
            temperature_K=fine["temperature_K"],
            reason="Refine the same symmetric displacement to test finite-step error",
            approval="separate authorization required",
            execution="not_started",
        ),
    )


def comparison_lines(v):
    summaries = [v["coarse"], v["fine"]]
    lines = ["", "## Step-size convergence", "", "| Step (eV) | Central DRC | Positive side | Negative side |", "|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['delta_eV']} | {s['central']:.10g} | {s['positive_side']:.10g} | {s['negative_side']:.10g} |")
    verdict = "Stable within the project tolerance" if v["passed"] else "Outside the project tolerance"
    lines += [
        "",
        f"{verdict}. Absolute difference {v['absolute_difference']:.10g}, tolerance {v['tolerance']:.10g}.",
        "",
        "| Change from baseline or validation residual | +0.01 | -0.01 | +0.005 | -0.005 |",
        "|---|---:|---:|---:|---:|",
    ]

    def row(label, values):
        lines.append("| " + label + " | " + " | ".join(f"{x:.9g}" for x in values) + " |")

    changes = [s["changes_from_baseline"][sign] for s in summaries for sign in ("plus", "minus")]
    for key in ("coverage", "vacancies"):
        for sid in changes[0][key]:
            row(f"{key} / {sid} (fraction)", [c[key][sid] for c in changes])
    for rid, flux in changes[0]["flux"].items():
        for direction in flux:
            row(f"{rid} / {direction} (events/reference site/s)", [c["flux"][rid][direction] for c in changes])
    residuals = [s["residuals"][sign] for s in summaries for sign in ("plus", "minus")]
    row("Maximum surface steady-state residual", [r["steady_state"] for r in residuals])
    for key in ("site_balance", "element_balance", "detailed_balance"):
        for name in residuals[0][key]:
            row(f"{key} / {name}", [r[key][name] for r in residuals])
    return lines
