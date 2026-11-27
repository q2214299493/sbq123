"""Offline, evidence-scoped mapping from a reaction-network/1 snapshot to CATKINAS."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import canonical_json, sha256_file, sha256_json, write_json_exclusive
from scripts.baseline_mkm.normalization import normalization as normalization, read_profile
from scripts.baseline_mkm.mapping_scope import MappingBlocked, issue, topology
from scripts.baseline_mkm.single_point import qualify
from scripts.kinetic_parameters.engine import check_version
from scripts.baseline_mkm.parameter_table import catkinas
from scripts.multiphase_contracts import read_unique_json
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


def map_network(network, dataset=None, configuration=None, *, normalization_path=None):
    """Return (files, report). A blocked or invalid mapping returns an empty file dictionary."""
    version = network.get("network_version") if isinstance(network, dict) else None
    report = {"format": "catkinas-network-mapping/1", "project_id": network.get("project_id") if isinstance(network, dict) else None,
              "network_version": version, "status": "blocked", "execution_authorized": False,
              "native_execution_eligibility": "blocked", "capability_evidence": dict(EVIDENCE), "issues": [], "native_input_hashes": {}}
    issues = report["issues"]
    try:
        if not isinstance(network, dict):
            raise ValueError("Expected a reaction-network/1 snapshot object")
        gaps, forms = topology(network)
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
        report["native_normalization"] = dict(contract, source=profile["source"],
                                               profile_sha256=sha256_file(Path(normalization_path))) if contract else None
        report["physical_tof_eligibility"] = "eligible" if contract else "unavailable"
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report["physical_tof_eligibility"] = "unqualified"
        issues.append(issue("missing_evidence" if normalization_path is None else "invalid", "normalization", version, str(exc)))
    if any(item["entity"] != "normalization" for item in issues):
        return {}, report
    try:
        files, adapter = qualify(network, dataset, configuration)
        table = catkinas(dataset)
        report["mapping"] = identity_map(network, adapter, table)
    except MappingBlocked as exc:
        issues.extend(exc.issues)
        return {}, report
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        issues.append(issue("invalid", "kinetic_input", dataset.get("dataset_version"), str(exc)))
        return {}, report
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    for name in ("dataset", "configuration", "normalization", "report", "output-dir"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    files, report = map_network(read_unique_json(args.network),
                                read_unique_json(args.dataset) if args.dataset else None,
                                read_unique_json(args.configuration) if args.configuration else None,
                                normalization_path=args.normalization)
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
