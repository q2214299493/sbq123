"""Read a receipt-bound CATKINAS single point and emit native-basis V2 or its qualification."""
import argparse
import json
import math
from pathlib import Path

from scripts.baseline_mkm.normalization import individual_rate, read_profile, reference_rate
from scripts.baseline_mkm.results import read_single_point, result_quality
from scripts.baseline_mkm.single_point_result import check_steady_state, reconstruct, species_and_sites, validate_result
from scripts.kinetic_data.native_rate_output import artifact, build_output, conditions_pa, require
from scripts.baseline_mkm.parameter_table import catkinas
from scripts.multiphase_contracts import read_unique_json
from scripts.native_model import assemble


def _coefficients(dataset, native_rows, reference):
    pairs = []
    for model in dataset["reactions"]:
        rid = model["reaction_id"]
        measured = native_rows[rid]
        pair = dict(reaction_id=rid)
        for direction, key in (("forward", "kf"), ("reverse", "kr")):
            rate = model["rates"][direction]
            order = sum(rate["gas_orders"].values())
            coverage = sum(rate["activity_orders"]["species"].values()) - order + sum(rate["activity_orders"]["vacant_sites"].values())
            pair[direction] = dict(value=measured[key], unit=measured[direction + "_unit"],
                                   activity_orders={"pressure": order, "fractional_coverage": coverage},
                                   rate_law_id=rate["method"], native_reference=f"CATKINAS native mass action on the declared {reference}")
        pairs.append(pair)
    return pairs


def adapt(receipt_path, *, network_path, dataset_path, config_path, input_path, normalization_path, root):
    """Read the archived closed-cycle or single-point receipt. All supplied paths bind actual bytes."""
    receipt_path = Path(receipt_path)
    folder = receipt_path.parent
    live = receipt_path.name == "ACCEPTED.json"
    mat, log = folder / "data1.mat", folder / "native_log_extract.txt"
    if live:
        from scripts.baseline_mkm.single_point import accepted_receipt

        receipt = accepted_receipt(folder)
        mat, log = (folder / "runtime/result_phase25" / name for name in ("data1.mat", "log1"))
        hashes = {p.name: receipt["output_hashes"][p.relative_to(folder).as_posix()] for p in (mat, log)}
        hashes["result.json"] = receipt["result_sha256"]
    else:
        receipt = read_unique_json(receipt_path)
    phase3 = receipt.get("format") == "mkm-single-point-plan/1"
    if phase3:
        require(receipt["stage"] == "ACCEPTED", "Receipt lacks an accepted native result")
        if not live:
            hashes = receipt["published_evidence_sha256"]
        parents = receipt["input_hashes"]
        input_hash = receipt["native_input_hashes"]["INPUT_phase25.m"]
        version, run_id = receipt["catkinas_version"], receipt["run_id"]
    else:
        closed = receipt["closed_cycle"]
        require(closed["exit_code"] == 0 and not closed["timed_out"], "Incomplete native closed cycle")
        require(closed["binary_sha256"] == receipt["environment"]["sha256"], "Executable binding differs")
        hashes = receipt["source_sha256"]
        parents = {"dataset": hashes[Path(dataset_path).name], "configuration": hashes[Path(config_path).name]}
        input_hash = closed["source_sha256"]
        version = receipt["environment"]["reported_version"]
        run_id = Path(closed["raw_local_directory"]).name
    network_ref = artifact(network_path, root, parents.get("network"))
    dataset_ref = artifact(dataset_path, root, parents["dataset"])
    config_ref = artifact(config_path, root, parents["configuration"])
    input_ref = artifact(input_path, root, input_hash)
    mat_ref = artifact(mat, root, hashes[mat.name])
    log_ref = artifact(log, root, hashes[log.name])
    dataset, network, config = map(read_unique_json, map(Path, (dataset_path, network_path, config_path)))
    files, manifest = assemble("catkinas", dataset, config)
    require(manifest["files"]["INPUT_phase25.m"] == input_hash, "Native input differs from the bound model")
    mapping = manifest["validation"]
    normal, contract = read_profile(normalization_path, network, config)
    require(contract is not None, "Physical rate export requires verified normalization; raw rates remain in the single-point result")
    native = read_single_point(mat, log)
    temperature = mapping["fixed_temperature_K"]
    if phase3:
        result_ref = artifact(folder / "result.json", root, receipt["result_sha256"])
        reviewed = read_unique_json(folder / "result.json")
        require(result_ref["sha256"] == hashes["result.json"] and reviewed["plan_sha256"] == receipt["raw_plan_sha256"]
                and reviewed["output_hashes"] == receipt["output_hashes"], "Archived result provenance differs")
        if live:
            from scripts.baseline_mkm.analysis import verify_receipt

            verify_receipt(receipt, reviewed, result_ref["sha256"], parents, network, dataset, config)
        native_log = log.read_bytes().decode("ascii", errors="replace")
        input_text = files["INPUT_phase25.m"]
        bound = reviewed.get("normalization")
        require(bound == receipt.get("normalization") and (not bound or bound == contract),
                "Result, plan and supplied normalization differ")
        result = validate_result(dataset, config, mapping, native, native_log, input_text,
                                 reference=bound, legacy_replay="normalization" not in reviewed)
        if "normalization" in reviewed:
            result["quality"] = result_quality(mat, native_log, mapping, result, input_text)
        require(all(reviewed[k] == v for k, v in result.items()) and reviewed["run_id"] == run_id
                and receipt["temperature_K"] == temperature and receipt["kinetic_dataset_version"] == dataset["dataset_version"]
                and receipt["network_version_id"] == network["network_version"], "Native replay differs from run receipt")
        require(receipt["output_hashes"]["runtime/result_phase25/data1.mat"] == mat_ref["sha256"], "MAT output binding differs")
    else:
        require(native == receipt["native_single_point"] and closed["input_echo_sha256"] == input_hash
                and closed["result_sha256"]["result_closed_cycle/data1.mat"] == mat_ref["sha256"], "Closed-cycle observation differs")
        require(mapping["reaction_indices"] == {r["reaction_id"]: r["native_index"] for r in receipt["independent_comparison"]}
                and receipt["checks"]["T_K"] == temperature, "Closed-cycle reaction map or temperature differs")
        table = catkinas(dataset)
        by_id, sites, vacant, activities, gas, species, inventories = species_and_sites(table, mapping, native, config)
        source, reactions, _ = reconstruct(table, mapping, native, temperature, by_id, sites, vacant, activities)
        residual, tolerance = check_steady_state(source, reactions, gas, by_id)
        result = dict(reactions=reactions, species=species, sites=inventories, steady_state_residual=residual,
                      validation={"steady_state_absolute_tolerance": tolerance})
        result_ref = artifact(receipt_path, root)
    source_path = (Path(normalization_path).parent / normal["source"]["path"]).resolve()
    reference = artifact(source_path, root, contract["evidence_sha256"])
    sites = contract["sites_per_reference"]
    require(set(sites) <= set(mapping["site_indices"]), "Native and reviewed inventories differ")
    original = read_unique_json(source_path)
    rows = {r["reaction_id"]: r for r in result["reactions"]}
    extent = result.get("overall_rate")
    if "turnover_stoichiometry" in original:
        weights = original["turnover_stoichiometry"]
        require(set(rows) == set(weights) and all(n > 0 for n in weights.values()), "Overall extent definition differs")
        extents = [rows[r]["net_flux"] / n for r, n in weights.items()]
        require(all(math.isclose(v, extents[0], rel_tol=1e-9) for v in extents), "No common overall extent")
        require(extent is None or math.isclose(extent, extents[0], rel_tol=1e-9), "Gas and reaction turnovers disagree")
        extent = extents[0]
    per_reference = reference_rate(extent, contract)
    partials = config["partial_pressure_bar"]
    total = dataset["reactions"][0]["parameter_set"]["pressure_Pa"] / 100000
    if phase3:
        require(receipt["total_pressure_bar"] == total and receipt["partial_pressures_bar"] == partials,
                "Operating conditions differ from the run receipt")
    obs = {rid: {k: r[k + "_flux"] for k in ("forward", "reverse", "net")} for rid, r in rows.items()}
    basis = dict(basis_kind=contract["reference_basis"], denominator_unit=contract["denominator_unit"], inventory_ids=contract["inventory_ids"],
                 reference_id=contract["reference_id"], denominator_value=contract["denominator_value"],
                 definition=original.get("scope") or f"Reviewed native reference {contract['reference_id']} with counts {sites}")
    if contract["reference_basis"] == "other":
        basis["basis_evidence"] = reference
    pair = contract["reference_basis"] == "reference_site_pair"
    payload = build_output(dataset, network, engine=dict(name="CATKINAS", version=str(version)), run_id=run_id,
                           conditions=conditions_pa(temperature, total, partials), basis=basis, inputs=[input_ref],
                           provenance=dict(network=network_ref, dataset=dataset_ref, native_output=mat_ref),
                           observations=obs, coefficients=_coefficients(dataset, rows, "reference pair" if pair else contract["reference_id"]))
    residual_lines = [s.split("return with the residue ", 1)[1].split(". Succeed!!")[0]
                      for s in log.read_bytes().decode("ascii", errors="replace").splitlines() if "return with the residue " in s]
    qualification = dict(native_residue_text=residual_lines,
                         executable_sha256=receipt["runtime"]["catkinas"]["sha256"] if phase3 else closed["binary_sha256"],
                         receipt=artifact(receipt_path, root), native_log=log_ref, configuration=config_ref,
                         result_record=result_ref, normalization=artifact(normalization_path, root), reference=reference,
                         distribution_label=receipt["runtime"]["catkinas"]["download_label"] if phase3 else receipt["environment"]["distribution_label"],
                         native_convergence="converged",
                         species=result["species"], site_inventories=result["sites"], sites_per_reference=sites,
                         mean_turnover_per_individual_site_s=individual_rate(per_reference, contract),
                         native_gas_rates=native["net_gas_flux_per_reference_site_s"], statistical_uncertainty=None,
                         scope=("Accepted single point. Rate uncertainty was not measured." if live else
                                "Archived synthetic single point. Rate uncertainty was not measured."))
    values = dict(residual=reference_rate(result["steady_state_residual"], contract),
                  residual_tolerance=reference_rate(result["validation"]["steady_state_absolute_tolerance"], contract),
                  overall_turnover=per_reference)
    suffix = "_per_pair_s" if pair else "_per_reference_s"
    qualification.update({key + suffix: value for key, value in values.items()})
    if live:
        corrected = result if bound else validate_result(dataset, config, mapping, native, native_log, input_text, reference=contract)
        qualification["single_point_replay"] = corrected
        qualification["quality"] = result["quality"] if bound else result_quality(mat, native_log, mapping, corrected, input_text)
    return payload, qualification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    for key in ("network", "dataset", "config", "input", "normalization"):
        parser.add_argument("--" + key, required=True, type=Path, dest=key + "_path")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--qualification", action="store_true")
    options = vars(parser.parse_args())
    index = int(options.pop("qualification"))
    print(json.dumps(adapt(options.pop("receipt"), **options)[index], indent=2, allow_nan=False))
