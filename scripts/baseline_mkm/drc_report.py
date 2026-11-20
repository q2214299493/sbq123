"""Compare verified paired results using net overall turnover per reference site pair."""

from datetime import datetime
from math import log
from pathlib import Path
import re

from scripts.artifact_io import load_json_object as read, sha256_file
from scripts.baseline_mkm.drc_pair import BUDGET, SIGNS, REPORTS, accepted, baseline, check_member, put, verified_finish
from scripts.baseline_mkm.drc_step_size import comparison_lines, validation
from scripts.baseline_mkm.results import read_single_point
from scripts.baseline_mkm.single_point_result import check_close
from scripts.baseline_mkm.ts_perturbation import HALF_STEP_EV, REACTION, central_difference
from scripts.kinetic_parameters.export import catkinas
from scripts.thermochemistry.harmonic import KB


def directional_audit(dataset, analysis, reaction_id):
    """Replay the native coefficients, fixed-T energy input and both mass-action fluxes."""
    exported = next(row for row in catkinas(dataset)["rows"] if row["reaction_id"] == reaction_id)
    native = next(row for row in analysis["rates"]["reactions"] if row["reaction_id"] == reaction_id)
    energy_input = exported["fixed_T_energy_input"]
    check_close(native["applied_forward_barrier_eV"], energy_input["Ea_eV"], "native Ea")
    check_close(native["applied_reaction_energy_eV"], energy_input["G0_eV"], "native G0")
    audit = dict(native_index=native["index"], fixed_T_energy_input=energy_input)
    for side, key in (("forward", "kf"), ("reverse", "kr")):
        expected = exported[side]
        factors = native["activity_factors"][side]
        if native[side + "_unit"] != expected["unit"] or factors["gas_orders"] != expected["gas_partial_pressure_orders"]:
            raise ValueError(f"{reaction_id}: inconsistent {side} pressure orders or units")
        check_close(native[key], expected["coefficient"], "native " + key, rel=1e-4, absolute=0)
        flux = native[key] * factors["gas_pressure_factor"] * factors["adsorbate_factor"] * factors["vacancy_factor"]
        check_close(flux, native[side + "_flux"], "independent " + side + " flux")
        audit[side] = dict(**factors, coefficient_unit=expected["unit"], expected_coefficient=expected["coefficient"],
                           native_coefficient=native[key], reconstructed_flux=flux, native_flux=native[side + "_flux"])
    return audit


def evidence(run, receipt, a, *, pressure_reaction=None):
    r = read(run / "result.json")
    data = read(run / "dataset.json")
    native = run / "runtime/result_phase25"
    product_rate = read_single_point(native / "data1.mat", native / "log1")["net_gas_flux_per_reference_site_s"]["HNO"]
    tof = a["tof"]["overall"]["per_site_pair_s"]
    independent = product_rate / a["tof"]["overall_stoichiometry"]["HNO-g"]
    check_close(tof, independent, "independent product-based extent")
    rates = {}
    for model, row in zip(data["reactions"], a["rates"]["reactions"], strict=True):
        rid = row["reaction_id"]
        order = sum(model["rates"]["forward"]["gas_orders"].values()) - sum(model["rates"]["reverse"]["gas_orders"].values())
        p0 = model["parameter_set"]["standard_states"]["gas_pressure_Pa"] / 100000
        residual = log(row["kf"]) - log(row["kr"]) + order * log(p0) - model["equilibrium"]["ln_K_standard"]
        check_close(residual, 0, f"{rid} native detailed balance", absolute=1e-4)
        rates[rid] = {
            k: row[k]
            for k in (
                "kf",
                "kr",
                "forward_unit",
                "reverse_unit",
                "forward_flux",
                "reverse_flux",
                "net_flux",
                "flux_unit",
                "reaction_free_energy_eV",
                "forward_activation_free_energy_eV",
                "reverse_activation_free_energy_eV",
            )
        }
        rates[rid]["native_log_balance_residual"] = residual

    def timestamp(stage):
        return datetime.fromisoformat(read(run / (stage + ".json"))["timestamp"])

    return dict(
        **({"pressure_validation": directional_audit(data, a, pressure_reaction)} if pressure_reaction else {}),
        run_id=receipt["run_id"],
        run_receipt_sha256=sha256_file(run / "ACCEPTED.json"),
        network_version=a["network_version"],
        dataset_version=a["dataset_version"],
        source_hashes=a["source_hashes"],
        native_hashes=r["output_hashes"],
        perturbation=data.get("ts_perturbation"),
        convergence=receipt["convergence"],
        scientific_validation=receipt["scientific_validity"],
        validation=r["validation"],
        steady_state_residual=r["steady_state_residual"],
        runtime_s=(timestamp("COLLECTING") - timestamp("RUNNING")).total_seconds(),
        net_tof_per_site_pair_s=tof,
        product_based_tof_per_site_pair_s=independent,
        rates=rates,
        coverage={v["species_id"]: v["species_coverage"] for v in a["coverage"]},
        vacancies={k: v["vacancy_fraction"] for k, v in a["utilization"].items()},
        site_residuals={k: v["balance_residual"] for k, v in a["utilization"].items()},
        element_balance=a["selectivity"]["element_balance"],
    )


def compare(root, base):
    receipt, a = baseline(base)
    pair = read(root / "pair.json")
    finished = verified_finish(root, pair)
    if pair["baseline_result_sha256"] != receipt["result_sha256"]:
        raise ValueError("No valid completed pair within the budget")
    check_close(finished["remaining_s"] + finished["elapsed_s"], BUDGET, "remaining budget")
    pressure_reaction = pair["reaction_id"] if pair["reaction_id"] != REACTION else None
    cases = {"baseline": evidence(base, receipt, a, pressure_reaction=pressure_reaction)}
    changes = {}
    for label, sign in SIGNS:
        run = check_member(root, base, label, sign)
        state, member = accepted(run)
        if member["normalization"] != a["normalization"] or member["tof"]["overall_stoichiometry"] != a["tof"]["overall_stoichiometry"]:
            raise ValueError("Inconsistent turnover normalization")
        case = evidence(run, state, member, pressure_reaction=pressure_reaction)
        cases[label] = case
        diff = {k: {sid: v - cases["baseline"][k][sid] for sid, v in case[k].items()} for k in ("coverage", "vacancies")}
        diff["flux"] = {
            rid: {k: row[k] - cases["baseline"]["rates"][rid][k] for k in ("forward_flux", "reverse_flux", "net_flux")}
            for rid, row in case["rates"].items()
        }
        changes[label] = diff
    rates = [case["net_tof_per_site_pair_s"] for case in cases.values()]
    t = a["temperature_K"]
    delta = pair["delta_eV"]
    value = central_difference(*rates, t, delta)
    independent = (
        KB * t * log(cases["minus"]["product_based_tof_per_site_pair_s"] / cases["plus"]["product_based_tof_per_site_pair_s"]) / (2 * delta)
    )
    check_close(value, independent, "independent DRC")
    return dict(
        format="mkm-ts-drc/1",
        scope="synthetic_benchmark",
        reaction_id=pair["reaction_id"],
        temperature_K=t,
        partial_pressures_bar=a["partial_pressures_bar"],
        delta_eV=delta,
        kBT_eV=KB * t,
        convention="-kBT * (ln(net_TOF_plus) - ln(net_TOF_minus)) / (2 * delta_eV), fixed endpoints and prefactors",
        observable="positive net overall turnovers per reference site pair per second",
        normalization=a["normalization"],
        drc=value,
        dimensionless=True,
        independent_product_drc=independent,
        outside_zero_to_one=not 0 <= value <= 1,
        cases=cases,
        changes_from_baseline=changes,
        budget=dict(finished, per_run_s=210, total_s=BUDGET, max_retries=0, max_parallel=1),
        fe110=dict(
            drc=None,
            qualification_source="reports/multiphase/phase3_0/fe110_qualification.json",
            gaps=read(REPORTS / "phase3_0/fe110_qualification.json")["missing_data"],
        ),
    )


def cross_reaction_comparison(report_paths, dataset, analysis):
    """Bind independently verified step-size studies to one accepted baseline and observable."""
    studies = {}
    common = None
    for coarse_path, fine_path in report_paths:
        coarse, fine = read(coarse_path), read(fine_path)
        v = validation(coarse, fine, sha256_file(coarse_path))
        if v != fine["step_size_validation"]:
            raise ValueError("Changed convergence evidence")
        base = fine["cases"]["baseline"]
        binding = dict(baseline=base["source_hashes"], network=base["network_version"], dataset=base["dataset_version"],
                       normalization=fine["normalization"], observable=fine["observable"], temperature_K=fine["temperature_K"],
                       partial_pressures_bar=fine["partial_pressures_bar"])
        if common is not None and binding != common:
            raise ValueError("Different baseline or observable across reaction types")
        if dataset["dataset_version"] != binding["dataset"] or analysis["source_hashes"] != binding["baseline"]:
            raise ValueError("Rate-law analysis differs from the accepted baseline")
        common = binding
        rid = fine["reaction_id"]
        if rid in studies:
            raise ValueError("Duplicate cross-study reaction ID")
        audit = directional_audit(dataset, analysis, rid)
        studies[rid] = dict(
            coarse_result_sha256=sha256_file(coarse_path), fine_result_sha256=sha256_file(fine_path),
            rate_law={side: {k: audit[side][k] for k in ("gas_orders", "surface_orders", "vacant_site_orders", "coefficient_unit")}
                      for side in ("forward", "reverse")},
            estimates={k: {field: v[k][field] for field in ("delta_eV", "central", "positive_side", "negative_side")}
                       for k in ("coarse", "fine")},
            step_stable=v["passed"], absolute_difference=v["absolute_difference"], tolerance=v["tolerance"],
        )
    if len(studies) != 2:
        raise ValueError("Expected two distinct reaction studies")
    first, second = [s["rate_law"] for s in studies.values()]
    if all(first[side]["gas_orders"] == second[side]["gas_orders"] for side in ("forward", "reverse")):
        raise ValueError("Expected different pressure-order representations")
    return dict(format="mkm-cross-reaction-drc/1", scope="synthetic_benchmark", common=common, reactions=studies)


def render(result):
    cases = result["cases"]
    lines = [
        f"# {result['reaction_id'].capitalize()} TS sensitivity at {result['temperature_K']:g} K",
        "",
        "The symmetric displacement holds both endpoints, prefactors, pressures and normalization fixed.",
        "",
        f"| Observable | Baseline | +{result['delta_eV']:g} eV | -{result['delta_eV']:g} eV |",
        "|---|---:|---:|---:|",
    ]

    def row(label, values):
        lines.append("| " + label + " | " + " | ".join(f"{v:.10g}" for v in values) + " |")

    row("Net turnovers / (reference pair s)", [c["net_tof_per_site_pair_s"] for c in cases.values()])
    row("Native invocation (s)", [c["runtime_s"] for c in cases.values()])
    for k in ("coverage", "vacancies", "site_residuals"):
        for sid in cases["baseline"][k]:
            row(f"{k} / {sid}", [c[k][sid] for c in cases.values()])
    for rid, r in cases["baseline"]["rates"].items():
        for key, unit in (
            ("kf", r["forward_unit"]),
            ("kr", r["reverse_unit"]),
            ("forward_flux", r["flux_unit"]),
            ("reverse_flux", r["flux_unit"]),
            ("net_flux", r["flux_unit"]),
        ):
            row(f"{rid} {key} ({unit})", [c["rates"][rid][key] for c in cases.values()])
    lines.extend(
        [
            "",
            f"Central finite-difference DRC = {result['drc']:.10g} (dimensionless).",
            f"Independent product-based estimate = {result['independent_product_drc']:.10g}.",
            f"Pair elapsed {result['budget']['elapsed_s']:.2f} s of {BUDGET} s.",
            "",
            (
                "A finite displacement samples curvature; the estimates use a symmetric energy interval."
                if "step_size_validation" in result
                else "A finite displacement samples curvature. The local infinitesimal derivative and step-size convergence remain unmeasured."
            ),
        ]
    )
    if result["outside_zero_to_one"]:
        b, p, m = [cases[label]["net_tof_per_site_pair_s"] for label in ("baseline", "plus", "minus")]
        scale = result["kBT_eV"] / result["delta_eV"]
        lines.extend(
            [
                "",
                "### Signed response outside [0, 1]",
                "",
                f"One-sided slopes are {scale * log(b / p):.9g} on the raised-barrier side and "
                f"{scale * log(m / b):.9g} on the lowered-barrier side. Compare their asymmetry and the "
                "coverage/flux changes above when interpreting inhibition or amplification.",
            ]
        )
    if "step_size_validation" in result:
        lines.extend(comparison_lines(result["step_size_validation"]))
    return "\n".join(lines) + "\n"


def publish(root, base, output, *, reference_pair=None, reference_result=None):
    result = compare(root, base)
    if result["delta_eV"] == HALF_STEP_EV:
        if reference_pair is None:
            raise ValueError("The convergence report requires the original accepted pair directory")
        coarse = compare(reference_pair, base)
        original = REPORTS / "phase3_2_0/result.json" if result["reaction_id"] == REACTION else reference_result
        if original is None:
            raise ValueError("The selected reaction requires its accepted coarse result")
        if coarse != read(original):
            raise ValueError("Reconstructed reference differs from the accepted coarse result")
        result["step_size_validation"] = validation(coarse, result, sha256_file(original))
    output.mkdir(exist_ok=True, parents=True)
    put(output / "result.json", result)
    write_once(output / "comparison.md", render(result).encode())
    for label, sign in SIGNS:
        run = check_member(root, base, label, sign)
        target = output / label
        target.mkdir(exist_ok=True)
        native = run / "runtime/result_phase25"
        write_once(target / "data1.mat", (native / "data1.mat").read_bytes())
        write_once(target / "accepted.json", (run / "ACCEPTED.json").read_bytes())
        if result["reaction_id"] != REACTION:
            for name in ("plan.json", "approval.json"):
                write_once(target / name, (run / name).read_bytes())
            source = Path(read(run / "approval.json")["source"]["path"])
            write_once(target / "user-reply.json", source.read_bytes())
        # Retain the native symbol map, applied inputs, convergence and gas column order for offline replay.
        lines = (native / "log1").read_bytes().decode("ascii", errors="replace").splitlines()
        selected = [
            s.strip()
            for s in lines
            if re.match(
                r"^\s*(CATKINAS is running now on MATLAB|\(\d+\):|T\s*=|"
                r"\[\s*[xy]\(\d+\)|Species\s+.*\(gas\)|CATKINAS is finished now)",
                s,
            )
            or "Converged, return with the residue" in s
        ]
        write_once(target / "native_log_extract.txt", ("\n".join(selected) + "\n").encode())


def write_once(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Existing evidence differs: {path.name}")
    else:
        with path.open("xb") as f:
            f.write(content)
