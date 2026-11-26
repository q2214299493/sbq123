"""Offline, evidence-bound evaluation of one coverage-dependent TS. No native execution entry point."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes, sha256_json, write_json_exclusive
from scripts.baseline_mkm.single_point_result import check_close
from scripts.baseline_mkm.ts_perturbation import reviewed_reaction
from scripts.kinetic_parameters.engine import calculate, generate
from scripts.kinetic_parameters.export import catkinas, catkinas_energy_pair, per_bar, validate_export
from scripts.kinetic_parameters.laws import activation_shift
from scripts.multiphase_contracts import _bundle_validator, _check_species_context, decode_unique_json, read_unique_json
from scripts.scientific_validation import validate_finite_tree

PARAMETER_SCHEMA = "https://schemas.sbq123.invalid/multiphase/1.0.0/kinetic_parameter.schema.json"


def validate_record(record, name):
    schema = {"$ref": f"{PARAMETER_SCHEMA}#/$defs/{name}_v1"}
    _bundle_validator().evolve(schema=schema).validate(record)
    validate_finite_tree(record)


def bound_parent(network, dataset, binding, fit, digest):
    validate_export(dataset)
    if (network["network_version"] != binding["network_version"] or dataset["dataset_version"] != binding["dataset_version"]
            or dataset["network_version"] != network["network_version"]):
        raise ValueError("Coverage model versions differ from the requested parent")
    if len(network["reactions"]) != 1 or len(dataset["reactions"]) != 1:
        raise ValueError("This contract requires one reversible reaction")
    model = dataset["reactions"][0]["model"]
    rebuilt = generate(network, {"network_version": network["network_version"], "models": [model]})
    if rebuilt != dataset:
        raise ValueError("Coverage baseline differs from the reproduced reviewed dataset")
    entry, row = reviewed_reaction(network, dataset, fit["reaction_id"])
    param = row["parameter_set"]
    verified = {s["sha256"] for s in network["source_artifacts"] if s["role"] == "verified_evidence"}
    coefficient = fit["term"]["coefficient"]
    if (digest not in verified or digest not in {s["sha256"] for s in model["sources"]}
            or coefficient["source"]["artifact"]["sha256"] not in verified):
        raise ValueError("Coverage fit or coefficient lacks network and kinetic review evidence")
    if coefficient["source"]["kind"] == "synthetic" and model.get("use_scope") != "synthetic_benchmark":
        raise ValueError("Synthetic slope evidence requires benchmark scope")
    if (fit["parameter_set_id"] != param["parameter_set_id"] or coefficient["reference_id"] != param["energy_reference_id"]
            or fit["reference_gibbs_eV"] != row["energies"]["gibbs_ev"]):
        raise ValueError("Reference barriers, energy convention or parameter identity differs")
    if fit["term"]["already_in_barrier"] or param["coverage_terms"] or model.get("coverage_fractions"):
        raise ValueError("A reference baseline without a previously applied coverage term is required")
    return entry, row


def displaced_gibbs(baseline, initial, transition, final):
    """Apply three absolute state shifts on one Gibbs reference (eV)."""
    return dict(forward=baseline["forward"] + (transition - initial),
                reverse=baseline["reverse"] + (transition - final),
                reaction=baseline["reaction"] + (final - initial))


def evaluate(network, dataset, binding, evidence_bytes, theta):
    """Evaluate a hypothetical solver state. The output cannot serve as a dataset or execution approval."""
    validate_record(binding, "coverage_ts_binding")
    digest = sha256_bytes(evidence_bytes)
    if binding["evidence"]["sha256"] != digest:
        raise ValueError("Coverage fit SHA-256 differs")
    fit = decode_unique_json(evidence_bytes)
    validate_record(fit, "coverage_ts_fit")
    entry, row = bound_parent(network, dataset, binding, fit, digest)
    term, param = fit["term"], row["parameter_set"]
    sid = term["species_id"]
    species = {s["species_id"]: s for s in network["species"]}
    surface = species.get(sid)
    catalog = network["catalog"]
    sites = {s["site_id"]: s["surface_id"] for s in catalog["sites"]}
    phases = {s["surface_id"]: s["phase_id"] for s in catalog["surfaces"]}
    if (surface is None or surface["phase"] != "surface" or surface["site_occupancy"] != {fit["site_inventory_id"]: 1}
            or surface["surface_ids"] != [fit["surface_id"]] or sites.get(fit["site_inventory_id"]) != fit["surface_id"]
            or phases.get(fit["surface_id"]) != fit["phase_id"] or fit["phase_id"] not in entry["definition"]["phase_ids"]):
        raise ValueError("Coverage variable must map to one matching phase, surface and monodentate site inventory")
    reaction = entry["definition"]
    _check_species_context(surface, reaction)
    if reaction["products"].get(sid, 0) == reaction["reactants"].get(sid, 0):
        raise ValueError("The selected coverage is conserved in this one-reaction network")
    for name in ("temperature_K", "pressure_Pa"):
        lo, hi = "min_" + name, "max_" + name
        vr, parent = fit["validity_range"], param["validity_range"]
        if not parent[lo] <= vr[lo] <= param[name] <= vr[hi] <= parent[hi]:
            raise ValueError(f"{name} outside compatible fit and parent applicability")
    if type(theta) not in (int, float):
        raise ValueError("Coverage must be a numeric site fraction")
    shift = activation_shift([term], {sid: theta}, param["energy_reference_id"],
                             reference_fractions={sid: fit["reference_coverage"]})
    gibbs = displaced_gibbs(fit["reference_gibbs_eV"], 0, shift, 0)
    displaced = dict(entry, energies=dict(entry["energies"], gibbs_ev=gibbs))
    try:
        rates, eq, _ = calculate(displaced, param, row["model"], species)
    except OverflowError as exc:
        raise ValueError("Coverage-dependent coefficient exceeds numerical range") from exc
    native_rates = {k: per_bar(v, param["standard_states"]["gas_pressure_Pa"]) for k, v in rates.items()}
    apparent = catkinas_energy_pair(native_rates["forward"], native_rates["reverse"], param["temperature_K"])
    base_encoding = catkinas(dataset)["rows"][0]["fixed_T_energy_input"]
    check_close(apparent["Ea_eV"], base_encoding["Ea_eV"] + shift, "Offline apparent TS shift")
    check_close(apparent["G0_eV"], base_encoding["G0_eV"], "Offline apparent reaction energy")
    contract = dict(fit, format="mkm-coverage-ts-contract/1", network_version=binding["network_version"], dataset_version=binding["dataset_version"],
                    source_evidence_sha256=digest, surface_species_id=sid, coefficient_w=term["coefficient"]["value"],
                    coefficient_unit="eV per unit site fraction", energy_reference=param["energy_reference_id"],
                    scientific_review=row["model"]["scientific_review"], use_scope=row["model"].get("use_scope", "project"))
    return dict(format="mkm-coverage-ts-evaluation/1", contract=contract, contract_sha256=sha256_json(contract),
                temperature_K=param["temperature_K"], pressure_Pa=param["pressure_Pa"], coverage=theta,
                delta_G_TS_eV=shift, physical_gibbs_eV=gibbs, equilibrium=eq,
                activity_coefficients_per_s={k: v["activity_coefficient_s^-1"] for k, v in rates.items()},
                expected_native_coefficients=native_rates,
                expected_native_apparent=apparent, tof_qualification="unavailable_no_native_result",
                evaluation="offline_supplied_coverage", native_feedback="BLOCKED", execution_authorized=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("network", "dataset", "binding"):
        parser.add_argument(name, type=Path)
    parser.add_argument("coverage", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    binding = read_unique_json(args.binding)
    validate_record(binding, "coverage_ts_binding")
    source = args.binding.parent / binding["evidence"]["path"]
    result = evaluate(read_unique_json(args.network), read_unique_json(args.dataset), binding, source.read_bytes(), args.coverage)
    if args.output:
        write_json_exclusive(args.output, result)
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
