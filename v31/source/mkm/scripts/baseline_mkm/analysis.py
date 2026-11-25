"""Read-only kinetic analysis of an accepted Phase 3.0 result or structural inspection of a draft."""

import argparse
import json
from pathlib import Path
import tempfile

from scripts.artifact_io import load_json_object as read, require_sha256, sha256_bytes, sha256_file, sha256_json
from scripts.baseline_mkm.normalization import flux_unit, individual_rate, read_profile, reference_rate, require_verified_source, validate_reference
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis, indexed, product_analysis, rate_analysis
from scripts.baseline_mkm.pathway_analysis import pathway_graph
from scripts.baseline_mkm.single_point import status
from scripts.baseline_mkm.single_point_result import check_close
from scripts.baseline_mkm.sensitivity_inputs import reproduce
from scripts.kinetic_parameters.engine import check_version
from scripts.kinetic_parameters.export import validate_export
from scripts.multiphase_contracts import _unique_keys
from scripts.registry_mutations import validate_registry_batch
from scripts.scientific_validation import validate_finite_tree


def read_bound(path):
    raw = path.read_bytes()
    data = json.loads(raw, object_pairs_hook=_unique_keys)
    validate_finite_tree(data)
    return data, sha256_bytes(raw)


def load_inputs(network, dataset):
    n, nh = read_bound(network)
    d, dh = read_bound(dataset)
    check_version(n, "network_version")
    check_version(d, "dataset_version")
    if d["network_version"] != n["network_version"]:
        raise ValueError("Network version mismatch")
    if reproduce(n, d) != d:
        raise ValueError("Dataset does not reproduce from reviewed network")
    return n, d, {"network": nh, "dataset": dh}


def verify_receipt(m, result, digest, hashes, n, d, c):
    if (m["stage"], m["execution"], m["approval"], m["convergence"], m["scientific_validity"]) != (
        "ACCEPTED",
        "exited_successfully",
        "approved",
        "converged",
        "validated_within_scope",
    ):
        raise ValueError("An accepted, approved and converged receipt is required")
    if result["format"] != "mkm-single-point-result/1" or result["validation"]["status"] != "passed":
        raise ValueError("Invalid normalized result")
    bound = result.get("normalization")
    if bound:
        validate_reference(bound, [s["site_id"] for s in n["catalog"]["sites"]], n["network_version"], c.get("turnover_basis"))
        require_verified_source(bound["evidence_sha256"], n)
        expected = reference_rate(result["overall_rate"], bound) if c.get("turnover_basis") else None
        if (result["tof_s_inverse"] != expected
                or result["mean_tof_per_individual_site_s"] != individual_rate(expected, bound)
                or result["turnover_basis"] != bound["reference_basis"]):
            raise ValueError("Accepted result has inconsistent native normalization")
    elif "normalization" in result and (result["tof_s_inverse"] is not None or result["turnover_basis"] is not None):
        raise ValueError("Physical turnover without reviewed normalization")
    bindings = [
        (m.get("normalization"), result.get("normalization")),
        (m["result_sha256"], digest),
        (m["input_hashes"], hashes),
        (m["configuration_hash"], sha256_json(c)),
        (m["network_version_id"], n["network_version"]),
        (m["kinetic_dataset_version"], d["dataset_version"]),
        (m["kinetic_dataset_version"], c["dataset_version"]),
        (m["catalyst_project_id"], n["project_id"]),
        (m["raw_plan_sha256"], result["plan_sha256"]),
        (m["run_id"], result["run_id"]),
        (m["question_id"], result["question_id"]),
        (m["output_hashes"], result["output_hashes"]),
        (m["use_scope"], result["scope"]),
        (m["validation"], result["validation"]),
        (result["total_reaction"], c.get("overall_stoichiometry")),
        (m["partial_pressures_bar"], c["partial_pressure_bar"]),
        (m["temperature_K"], d["reactions"][0]["parameter_set"]["temperature_K"]),
        (result["numerical_convergence"], m["convergence"]),
    ]
    if any(a != b for a, b in bindings):
        raise ValueError("Accepted result, conditions or source binding differs")
    if not all(row["model"].get("use_scope", "project") == result["scope"] for row in d["reactions"]):
        raise ValueError("Analysis scope differs from reviewed kinetic models")
    require_sha256(m["approval_reference"], label="approval")
    validate_export(d, fixed_mkm=True)


def analysis_options(options, network, config, point):
    bound = point.get("normalization")
    opt = {}
    if options:
        opt, verified = read_profile(options, network, config)
        if bound and verified != bound:
            raise ValueError("Analysis and plan normalization differ")
        bound = verified
    if config.get("turnover_basis") and not bound:
        raise ValueError("Verified normalization is required to qualify physical turnover")
    if bound:
        opt.update(reference_basis=bound["reference_basis"], sites_per_reference=bound["sites_per_reference"])
    return opt, bound


def analyze(network, dataset, configuration, result, receipt, options=None):
    n, d, hashes = load_inputs(network, dataset)
    c, hashes["configuration"] = read_bound(configuration)
    point, digest = read_bound(result)
    verify_receipt(receipt, point, digest, hashes, n, d, c)
    opt, bound = analysis_options(options, n, c, point)
    measured = indexed(point["species"], "species_id")
    for species in n["species"]:
        sid = species["species_id"]
        if measured[sid]["phase"] != species["phase"]:
            raise ValueError("Species phase differs from network")
        if species["phase"] == "gas":
            check_close(measured[sid]["pressure_bar"], c["partial_pressure_bar"][sid], "gas partial pressure")
    rates = rate_analysis(n, d, point)
    species_limits = rates.pop("species_tolerances")  # Keep the published historical analysis format.
    coverage_opt = dict(opt)
    if bound and set(bound["inventory_ids"]) != {s["site_id"] for s in n["catalog"]["sites"]}:
        coverage_opt.pop("sites_per_reference", None)
    coverage = coverage_analysis(n, point, coverage_opt, rates)
    species = indexed(n["species"], "species_id")
    tof, selectivity = product_analysis(c, rates["gas_net_production"], species, rates["tolerance"], opt, reference=bound,
                                       species_limits=species_limits)
    if point["overall_rate"] is not None:
        check_close(
            tof["model_native_extent"], point["overall_rate"], "overall rate", absolute=rates["tolerance"]
        )
    if point["tof_s_inverse"] is not None:
        check_close(
            tof["extent_per_reference_s"] if point.get("normalization") else tof["model_native_extent"],
            point["tof_s_inverse"],
            "reference turnover",
            absolute=rates["tolerance"],
        )
    if c.get("overall_stoichiometry") and point["molar_selectivity"] != selectivity["molar"]:
        old = point["molar_selectivity"] or {}
        new = selectivity["molar"] or {}
        if old.keys() != new.keys():
            raise ValueError("Product inventory differs from normalized result")
        for sid, value in old.items():
            check_close(value, new[sid], "molar selectivity")
    overall = c.get("overall_stoichiometry") or {}
    graph = pathway_graph(n, rates, [s for s, v in overall.items() if v < 0], c.get("selectivity_products") or [])
    extent = tof["model_native_extent"]
    if bound:
        del tof["model_native_extent"]
    else:
        tof["physical_tof_status"] = "unavailable"
    graph["net_events_per_overall_turnover"] = (
        {r["reaction_id"]: r["net_flux"] / extent for r in rates["reactions"]}
        if extent is not None and abs(extent) > rates["tolerance"]
        else None
    )
    report = dict(
        format="mkm-kinetic-analysis/2" if "format" in coverage else "mkm-kinetic-analysis/1",
        report_revision="native-reference/1",
        status="analyzed",
        scope=point["scope"],
        run_id=receipt["run_id"],
        question_id=receipt["question_id"],
        ticket_id=receipt["ticket_id"],
        project_id=n["project_id"],
        network_version=n["network_version"],
        dataset_version=d["dataset_version"],
        temperature_K=receipt["temperature_K"],
        partial_pressures_bar=c["partial_pressure_bar"],
        source_hashes=dict(
            hashes, result=digest, plan=point["plan_sha256"], approval=receipt["approval_reference"]
        ),
        normalization=opt,
        coverage=coverage["species"],
        utilization=coverage["sites"],
        phase_comparison=coverage["phase_comparison"],
        rates=rates,
        tof=tof,
        selectivity=selectivity,
        pathways=graph,
        validation=dict(
            status="passed",
            checks=[
                "source identities and eligibility",
                "directional and net flux",
                "gas source terms and elemental balance",
                "surface steady state",
                "separate site balances",
                "overall extent",
            ],
            rate_control_assessed=False,
            missing_normalization=[
                k
                for k in (
                    "site_density_mol_per_surface_m2",
                    "reference_mol_per_catalyst_m2",
                    "reference_mol_per_kg",
                    "reference_mol_per_reactor_m3",
                    "feed_inlet_per_reference_s",
                )
                if k not in opt
            ],
            physical_concentration_available=any(
                x.get("concentration_mol_per_surface_m2") is not None for x in coverage["species"]
            ),
        ),
    )
    apply_reference(report, bound)
    if "quality" in point:
        report["quality"] = point["quality"]
    if "format" in coverage:
        report["validation"]["coverage_status"] = coverage_status(coverage)
        if report["validation"]["coverage_status"] == "partial":
            report["validation"]["checks"].remove("separate site balances")
    return report


def apply_reference(report, reference):
    """Project the verified denominator onto every elementary flux in this analysis."""
    report["native_reference"] = reference
    unit = flux_unit(reference)
    for row in report["rates"]["reactions"]:
        row["flux_unit"] = unit


def coverage_status(coverage):
    missing = any(row["missing"] for row in coverage["species"]) or any(
        site.get("site_counts", {}).get("missing") for site in coverage["sites"].values()
    )
    return "partial" if missing else "complete"


def analyze_observations(network, observations):
    n, nh = read_bound(network)
    data, dh = read_bound(observations)
    check_version(n, "network_version")
    if data.get("format") != "mkm-coverage-observations/1" or data.get("network_version") != n["network_version"]:
        raise ValueError("Coverage observations require the matching versioned network")
    if not isinstance(data.get("source"), str) or not data["source"].strip():
        raise ValueError("Coverage observations require a source")
    analysis = coverage_analysis(n, data, {})
    return dict(**analysis, status=coverage_status(analysis), network_version=n["network_version"],
                source=data["source"], source_hashes={"network": nh, "observations": dh})


def inspect_draft(network, dataset):
    n, d, hashes = load_inputs(network, dataset)
    missing = {r["reaction_id"]: r["missing"] for r in d["reactions"] if r["missing"]}
    return dict(
        format="mkm-kinetic-analysis/1",
        status="structural_inspection_only",
        project_id=n["project_id"],
        network_version=n["network_version"],
        dataset_version=d["dataset_version"],
        source_hashes=hashes,
        missing=dict(reactions=missing, result="Accepted single-point result and matching receipt required"),
        coverage=None,
        rates=None,
        tof=None,
        selectivity=None,
        utilization=None,
        pathways=pathway_graph(n, None, [], []),
        validation={"status": "kinetic_analysis_blocked"},
    )


def registry_files(analysis, out, reviewer, timestamp):
    key = "mkm-" + analysis["source_hashes"]["plan"]
    digest = sha256_file(out / "analysis.json")
    batch_id = "mkm-analysis-" + digest
    return validate_registry_batch(
        dict(
            schema_version=1,
            document_kind="calculation_registry_batch",
            batch_id=batch_id,
            created_at=timestamp,
            reviewer=reviewer,
            reason="Attach derived analysis to the registered accepted point",
            rows={
                "files": [
                    dict(
                        file_id=batch_id,
                        calculation_id=key,
                        role="mkm_analysis",
                        filename="analysis.json",
                        local_path=str((out / "analysis.json").resolve()),
                        storage_mode="local",
                        existence_status="confirmed",
                        sha256=digest,
                    )
                ]
            },
        )
    )


def publish(out, report, registry_reviewer=None, timestamp=None):
    from scripts.baseline_mkm.analysis_report import markdown, pathway_diagram
    from scripts.artifact_io import write_json_exclusive

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        staged = Path(tmp) / "output"
        staged.mkdir()
        write_json_exclusive(staged / "analysis.json", report)
        (staged / "report.md").write_bytes(markdown(report).encode())
        (staged / "pathways.md").write_bytes(pathway_diagram(report).encode())
        if report["status"] == "analyzed":
            root = Path(__file__).resolve().parents[2]
            artifact = (
                (out / "analysis.json").relative_to(root).as_posix()
                if out.is_relative_to(root)
                else str(out / "analysis.json")
            )
            write_json_exclusive(
                staged / "ticket_handoff.json",
                dict(
                    ticket_id=report["ticket_id"],
                    status="READY_FOR_REVIEW",
                    note=f"MKM analysis {sha256_file(staged / 'analysis.json')}; question {report['question_id']}; evidence {artifact}"[
                        :1000
                    ],
                ),
            )
        if out.exists():
            if any(
                not (out / p.name).is_file() or sha256_file(out / p.name) != sha256_file(p)
                for p in staged.iterdir()
            ):
                raise ValueError("Output directory contains different analysis evidence")
        else:
            staged.rename(out)
    if registry_reviewer:
        batch = registry_files(report, out, registry_reviewer, timestamp)
        path = out / "registry_batch.json"
        if not path.exists():
            write_json_exclusive(path, batch)
        elif read(path) != batch:
            raise ValueError("Existing registry batch differs")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("replay", help="Copy a historical report verbatim after checking its reviewed digest")
    replay.add_argument("report", type=Path)
    replay.add_argument("sha256", help="Digest from the historical evidence handoff")
    replay.add_argument("output", type=Path)
    coverage = commands.add_parser("coverage", help="Analyze bound coverage observations offline")
    for name in ("network", "observations", "output"):
        coverage.add_argument(name, type=Path)
    for cmd in ("analyze", "run", "inspect"):
        sub = commands.add_parser(cmd)
        if cmd == "run":
            sub.add_argument("run_directory", type=Path)
        else:
            for k in ("network", "dataset"):
                sub.add_argument(k, type=Path)
        if cmd == "analyze":
            for k in ("configuration", "result", "receipt"):
                sub.add_argument(k, type=Path)
        if cmd != "inspect":
            sub.add_argument("--options", type=Path)
            sub.add_argument("--registry-reviewer")
        sub.add_argument("output", type=Path)
    a = p.parse_args(argv)
    if a.command == "replay":
        raw = a.report.read_bytes()
        if sha256_bytes(raw) != require_sha256(a.sha256, label="archived report"):
            raise ValueError("Archived report differs from the reviewed SHA-256")
        with a.output.open("xb") as target:
            target.write(raw)
        return
    if a.command == "coverage":
        from scripts.artifact_io import write_json_exclusive

        report = analyze_observations(a.network, a.observations)
        write_json_exclusive(a.output, report)
        print(f"{report['status']} {a.output}")
        return
    m = {}
    if a.command == "inspect":
        report = inspect_draft(a.network, a.dataset)
    elif a.command == "run":
        r = a.run_directory
        m = status(r)
        if m["stage"] != "ACCEPTED":
            p.error("Run requires an accepted receipt; use inspect for a draft network")
        m["raw_plan_sha256"] = sha256_json(read(r / "plan.json"))
        report = analyze(
            r / "network.json", r / "dataset.json", r / "configuration.json", r / "result.json", m, a.options
        )
    else:
        m = read(a.receipt)
        report = analyze(a.network, a.dataset, a.configuration, a.result, m, a.options)
    publish(a.output, report, getattr(a, "registry_reviewer", None), m.get("timestamp"))
    print(f"{report['status']} {a.output / 'analysis.json'}")


if __name__ == "__main__":
    main()
