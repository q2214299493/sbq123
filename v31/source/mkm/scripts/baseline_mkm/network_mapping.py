"""Offline, evidence-scoped mapping from a reaction-network/1 snapshot to CATKINAS."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import canonical_json, sha256_bytes, sha256_file, sha256_json, write_json_exclusive
from scripts.baseline_mkm.normalization import normalization as normalization, read_profile
from scripts.baseline_mkm.mapping_scope import MappingBlocked, issue, topology
from scripts.baseline_mkm.single_point import qualify
from scripts.kinetic_parameters.engine import check_version
from scripts.baseline_mkm.parameter_table import catkinas
from scripts.multiphase_contracts import decode_unique_json, read_unique_json
from scripts.native_model import publish

EVIDENCE = {
    "receipt": "reports/multiphase/phase3_0/benchmark_manifest.json",
    "receipt_sha256": "0773bdbbf0d3a2f7b8907ed271fdc1f0f725150c5e8c16ae77d10c37d389822d",
    "input_sha256": "b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8",
    "distribution": "20261106", "reported_version": "20230524",
}


def identity_map(network, adapter, table):
    native = adapter["validation"]
    catalog = network["catalog"]
    reactions = {r["definition"]["reaction_id"]: r["definition"] for r in network["reactions"]}
    owners = {r["surface_id"]: r.get("phase_id") for r in catalog["surfaces"]}
    return {
        "phases": [r["phase_id"] for r in catalog["phases"]],
        "surfaces": owners,
        "interfaces": {r["interface_id"]: {"surface_ids": r.get("surface_ids"), "phase_ids": r.get("phase_ids"),
                                           "participating_phase_ids": sorted(r.get("phase_ids") or {owners[s] for s in r["surface_ids"]})}
                       for r in catalog["interfaces"]},
        "sites": {s["site_id"]: {"surface_id": s["surface_id"], "interface_id": s.get("interface_id"),
                                 "site_type": s["site_type"], "native_index": native["site_indices"][s["site_id"]]}
                  for s in catalog["sites"]},
        "species": {s["species_id"]: {**{k: s.get(k) for k in ("phase", "material_ids", "surface_ids", "interface_id", "structure_id", "charge", "composition", "site_occupancy")},
                                      "native_token": native["species_tokens"][s["species_id"]]} for s in network["species"]},
        "reactions": {row["reaction_id"]: {
            **{k: reactions[row["reaction_id"]].get(k) for k in ("reaction_type", "phase_ids", "surface_ids", "interface_id", "ts_id", "ts_species_id", "required_sites", "operating_conditions_ref")},
            "native_index": native["reaction_indices"][row["reaction_id"]], "direction": row["directions"],
            "forward": row["forward"], "reverse": row["reverse"], "standard_states": row["standard_states"],
            "fixed_T_energy_input": row["fixed_T_energy_input"], "provenance": row["provenance"],
        } for row in table["rows"]},
    }


def kinetic_issues(network, dataset):
    if dataset is None:
        return [issue("missing_evidence", "network", network["network_version"], "Reviewed kinetic dataset required")]
    check_version(dataset, "dataset_version")
    if dataset.get("format") != "kinetic-dataset/1" or dataset.get("network_version") != network["network_version"]:
        raise ValueError("Kinetic dataset does not bind this reaction network")
    return [issue("missing_evidence", "reaction", row["reaction_id"], str(row.get("missing") or "Blocked kinetic export"))
            for row in dataset["reactions"] if not row.get("export_eligible")]


def map_network(network, dataset=None, configuration=None, *, normalization_path=None, general=False):
    """Return (files, report). A blocked or invalid mapping returns an empty file dictionary."""
    version = network.get("network_version") if isinstance(network, dict) else None
    report = {"format": "catkinas-network-mapping/1", "project_id": network.get("project_id") if isinstance(network, dict) else None,
              "network_version": version, "status": "blocked", "execution_authorized": False,
              "native_execution_eligibility": "blocked", "capability_evidence": dict(EVIDENCE), "issues": [], "native_input_hashes": {}}
    issues = report["issues"]
    try:
        if not isinstance(network, dict):
            raise ValueError("Expected a reaction-network/1 snapshot object")
        gaps, forms = topology(network, general=general)
    except (ValueError, TypeError, KeyError) as exc:
        issues.append(issue("invalid", "network", version, str(exc)))
        return {}, report
    issues.extend(gaps)
    report["equation_forms"] = forms
    for step in network["reactions"]:
        rid = step["definition"]["reaction_id"]
        if not step.get("parameter_set_ids"):
            issues.append(issue("missing_evidence", "reaction", rid, "Missing kinetic parameter binding"))
    try:
        report["dataset_version"] = None if dataset is None else dataset.get("dataset_version")
        issues.extend(kinetic_issues(network, dataset))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        issues.append(issue("invalid", "dataset", version, str(exc)))
    if configuration is None:
        issues.append(issue("missing_evidence", "network", version, "Operating conditions and native configuration required"))
    try:
        profile, contract = read_profile(normalization_path, network, configuration)
        if general and contract and contract["sites_per_reference"] != {s["site_id"]: 1 for s in network["catalog"]["sites"]}:
            raise ValueError("General native mapping requires one site of each inventory per model reference")
        report["native_normalization"] = dict(contract, source=profile["source"],
                                               profile_sha256=sha256_file(Path(normalization_path))) if contract else None
        report["physical_tof_eligibility"] = "eligible" if contract else "unavailable"
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report["physical_tof_eligibility"] = "unqualified"
        issues.append(issue("missing_evidence" if normalization_path is None else "invalid", "normalization", version, str(exc)))
    if (general and issues) or any(item["entity"] != "normalization" for item in issues):
        return {}, report
    try:
        files, adapter = qualify(network, dataset, configuration, general=general)
        table = catkinas(dataset)
        report["mapping"] = identity_map(network, adapter, table)
    except MappingBlocked as exc:
        issues.extend(exc.issues)
        return {}, report
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        issues.append(issue("invalid", "kinetic_input", dataset.get("dataset_version"), str(exc)))
        return {}, report
    if general:
        report["mapping_scope"] = "offline_general_equal_unit_inventories"
    report["native_input_eligibility"] = "eligible"
    report["native_execution_eligibility"] = "requires_separate_qualification_and_approval"
    if issues:
        return {}, report
    native = adapter["validation"]
    report.update(status="mapped_with_restrictions", native_input_hashes=adapter["files"],
                  native_input_bytes_match_archive=adapter["files"].get("INPUT_phase25.m") == EVIDENCE["input_sha256"],
                  configuration_sha256=sha256_json(configuration), source_artifacts=network["source_artifacts"],
                  conditions={"temperature_K": native["fixed_temperature_K"], "pressure_bar": table["rows"][0]["P_bar"],
                              "partial_pressure_bar": native["partial_pressure_bar"],
                              "initial_coverages": configuration["catkinas"]["initial_coverages"],
                              "MaxTime": configuration["catkinas"]["MaxTime"], "MaxOdeTime": configuration["catkinas"]["MaxOdeTime"]},
                  observables={k: configuration[k] for k in ("overall_stoichiometry", "selectivity_products", "turnover_basis") if k in configuration},
                  readback=native["native_text_readback"], adapter_manifest=adapter)
    if configuration.get("turnover_basis"):
        report["observables"]["turnover_basis"] = contract["reference_basis"]
    return files, report


def replay_general(network, dataset, configuration, mat, log, *, normalization_path=None, exact_initial=False):
    """Rebuild the bound input and compare raw MAT/log data to its independent balances."""
    from scripts.baseline_mkm.kinetic_analysis import coverage_analysis, rate_analysis
    from scripts.baseline_mkm.pathway_analysis import pathway_graph
    from scripts.baseline_mkm.steady_states import conserved_residual, surface_subspace
    from scripts.baseline_mkm.results import read_initial_coverages, read_single_point, result_quality
    from scripts.baseline_mkm.single_point_result import check_close, validate_result

    files, report = map_network(network, dataset, configuration, general=True, normalization_path=normalization_path)
    if not files:
        raise ValueError(f"Cannot reconstruct blocked mapping: {report['issues']}")
    mapping = report["adapter_manifest"]["validation"]
    input_text = files["INPUT_phase25.m"]
    mat_digest, log_digest = sha256_file(Path(mat)), sha256_file(Path(log))
    log_text = Path(log).read_bytes().decode("ascii", errors="replace")
    initial = read_initial_coverages(mat, log_text)
    wanted = {a.removesuffix("_INIT"): float(b.rstrip(";")) for line in input_text.splitlines()
              if "_INIT = " in line for a, b in [line.split(" = ")]}
    if initial.keys() != wanted.keys():
        raise ValueError("Unexpected initial MAT population symbols")
    for key, value in wanted.items():
        if exact_initial and initial[key] != value:
            raise ValueError(f"MAT initial population differs from serialized input: {key}")
        check_close(initial[key], value, "initial population", absolute=1e-12)
    native = read_single_point(mat, log, surface_only=not mapping["partial_pressure_bar"])
    reference = report["native_normalization"]
    result = validate_result(dataset, configuration, mapping, native, log_text, input_text, reference=reference)
    final = {s["species_id"]: s["coverage"] for s in result["species"] if s["phase"] == "surface"}
    residual = conserved_residual(surface_subspace(network), final, configuration["catkinas"]["initial_coverages"])
    check_close(residual, 0, "conserved molecular totals", absolute=1e-8)
    quality = result_quality(mat, log_text, mapping, result, input_text)
    quality["conserved_molecular_residual"] = residual
    rates = rate_analysis(network, dataset, result)
    coverages = coverage_analysis(network, result, reference or {}, rates)
    feeds = [s for s, v in (configuration.get("overall_stoichiometry") or {}).items() if v < 0]
    paths = pathway_graph(network, rates, feeds, configuration.get("selectivity_products") or [])
    if (mat_digest, log_digest) != (sha256_file(Path(mat)), sha256_file(Path(log))):
        raise ValueError("Native outputs changed during reconstruction")
    return dict(format="mkm-general-offline-reconstruction/1", execution_authorized=False,
                network_version=network["network_version"], dataset_version=dataset["dataset_version"],
                input_hashes=report["native_input_hashes"], mat_sha256=mat_digest,
                log_sha256=log_digest, model_basis=mapping["population_basis"],
                mapping=report["mapping"], result=result, quality=quality, rates=rates, coverages=coverages, pathways=paths)


def replay_starts(network, dataset, config, study_path, *, normalization_path=None):
    """Compare hash-specified outputs at one fixed model point, varying only initial populations."""
    from scripts.baseline_mkm import steady_states as ss

    study_bytes = Path(study_path).read_bytes()
    request = decode_unique_json(study_bytes)
    policy = request["tolerances"]
    ss.check_policy(policy)
    if request["dataset_version"] != dataset["dataset_version"] or request["fixed_config_sha256"] != ss.fixed_config(config):
        raise ValueError("General initial-state study belongs to another model point")
    members, starts, ids = [], set(), set()
    for step in request["members"]:
        name, initial = step["run"], step["initial_coverages"]
        start = tuple(sorted(initial.items()))
        if not isinstance(name, str) or not name or name in ids or start in starts:
            raise ValueError("Distinct named runs and initial populations required")
        ids.add(name)
        starts.add(start)
        if "execution_record" not in step or "execution_sha256" not in step:
            raise ValueError("Each start requires a hash-bound execution record")
        raw = (Path(study_path).parent / step["execution_record"]).read_bytes()
        if sha256_bytes(raw) != step["execution_sha256"]:
            raise ValueError("Execution record hash differs")
        execution = decode_unique_json(raw)
        if not isinstance(execution, dict):
            raise ValueError("Expected a trajectory execution record object")
        binding = dict(execution_id=execution.get("execution_id"), mat_sha256=step["mat_sha256"], log_sha256=step["log_sha256"])
        ss.check_independent_execution(binding, members)
        cfg = dict(config, catkinas=dict(config["catkinas"], initial_coverages=initial))
        mat, log = (Path(study_path).parent / step[key] for key in ("mat", "log"))
        record = replay_general(network, dataset, cfg, mat, log, normalization_path=normalization_path, exact_initial=True)
        if any(record[key] != step[key] for key in ("mat_sha256", "log_sha256")):
            raise ValueError("Study output hash differs")
        expected = dict(format="mkm-trajectory-execution/1", **binding, dataset_version=dataset["dataset_version"],
                        initial_coverages_sha256=sha256_json(initial), native_input_sha256=record["input_hashes"]["INPUT_phase25.m"])
        if execution != expected:
            raise ValueError("Execution record does not bind the starting condition, native input and outputs")
        result = record["result"]
        if max(result["steady_state_residual"], record["rates"]["steady_state_residual"]) > policy["max_residual"]:
            raise ValueError("Study residual exceeds comparison tolerance")
        members.append(dict(run=name, initial_coverages=initial, **binding, execution_sha256=step["execution_sha256"],
                            coverage={s["species_id"]: s["coverage"] for s in result["species"] if s["phase"] == "surface"},
                            vacancy={s["site_id"]: s["vacancy_fraction"] for s in result["sites"]},
                            net_rate={r["reaction_id"]: r["net_flux"] for r in result["reactions"]},
                            tof={"per_reference_s": result["tof_s_inverse"]}))
    if len(members) < 2:
        raise ValueError("At least two distinct initial populations required")
    comparisons = ss.compare_starts(network, members, policy)
    return dict(format="mkm-general-root-comparison/1", execution_authorized=False, study_sha256=sha256_bytes(study_bytes),
                dataset_version=dataset["dataset_version"], members=members, comparisons=comparisons,
                root_partition=ss.root_partition([m["run"] for m in members], comparisons))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--general", action="store_true", help="Offline general topology, one site of each inventory per model reference")
    parser.add_argument("network", type=Path)
    for name in ("dataset", "configuration", "normalization", "report", "output-dir"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--mat", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--study", type=Path, help="Offline multi-start MAT/log manifest")
    args = parser.parse_args()
    if args.study or args.mat or args.log:
        if (not all((args.general, args.dataset, args.configuration)) or args.output_dir
                or (bool(args.mat) != bool(args.log)) or bool(args.study) == bool(args.mat)):
            parser.error("Supply --general, --dataset, --configuration and either --study or the --mat/--log pair")
        inputs = [read_unique_json(p) for p in (args.network, args.dataset, args.configuration)]
        if args.study:
            report = replay_starts(*inputs, args.study, normalization_path=args.normalization)
        else:
            report = replay_general(*inputs, args.mat, args.log, normalization_path=args.normalization)
        if args.report:
            write_json_exclusive(args.report, report)
        else:
            print(json.dumps(report, indent=2, allow_nan=False))
        return 0
    files, report = map_network(read_unique_json(args.network),
                                read_unique_json(args.dataset) if args.dataset else None,
                                read_unique_json(args.configuration) if args.configuration else None,
                                normalization_path=args.normalization, general=args.general)
    # Network versions disregard JSON object key order. Use the same order for the published sidecar.
    report = json.loads(canonical_json(report))
    if files and args.output_dir:
        publish(args.output_dir, files, report)
    if args.report:
        write_json_exclusive(args.report, report)
    else:
        print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if files else 2


if __name__ == "__main__":
    raise SystemExit(main())
