"""Qualification and readback for the one frozen, synthetic bidentate experiment."""
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_bytes, sha256_file
from scripts.baseline_mkm.mapping_scope import MappingBlocked
from scripts.baseline_mkm.results import read_initial_coverages
from scripts.baseline_mkm.single_point_result import check_close

DESIGN = (Path(__file__).resolve().parents[2] / "reports/workflow_development"
          / "stage_v2_4_4_step3_topology_audit/one-inventory-bidentate")
DESIGN_SHA256 = "bc127a8de7c8e9b47adadb66180bee1dd705a671ccedfdc4b7bcd56c355a1055"


def qualification(network, dataset, config, inputs, normalization_path):
    from scripts.baseline_mkm.single_point import qualify

    design_path = DESIGN / "diagnostic-plan.json"
    if sha256_file(design_path) != DESIGN_SHA256 or normalization_path is not None:
        raise ValueError("Bidentate diagnostic requires its frozen design and model-reference basis")
    design = load_json_object(design_path)
    hashes = design["inputs"]
    for name, digest in hashes.items():
        if sha256_file(DESIGN / name) != digest:
            raise ValueError(f"Frozen bidentate evidence differs: {name}")
    for key, obj in (("network", network), ("dataset", dataset), ("configuration", config)):
        name = key + ".json"
        if inputs[key] != hashes[name] or obj != load_json_object(DESIGN / name):
            raise ValueError(f"Bidentate diagnostic input differs: {key}")
    try:
        qualify(network, dataset, config)
    except MappingBlocked as exc:
        if str(exc) != load_json_object(DESIGN / "default-qualifier.json")["message"]:
            raise ValueError("Production qualification differs from the reviewed footprint rejection") from exc
    else:
        raise ValueError("Production topology boundary changed; review the diagnostic again")

    files, adapter = qualify(network, dataset, config, general=True)
    if sha256_bytes(files["INPUT_phase25.m"].encode()) != hashes["INPUT_phase25.m"]:
        raise ValueError("Bidentate diagnostic native bytes differ")
    binding = dict(case=design["case"], design_sha256=DESIGN_SHA256, inputs=hashes,
                   expectations=load_json_object(DESIGN / "analytical-expectations.json"),
                   acceptance=design["acceptance"], runtime=design["reference_runtime"],
                   adapter_sha256={name: sha256_file(Path(__file__).with_name(name))
                                   for name in ("single_point.py", "bidentate_diagnostic.py")})
    return files, adapter, binding


def validate(binding, result, mat, log):
    expected = binding["expectations"]
    limits = binding["acceptance"]
    initial = read_initial_coverages(mat, log)
    if initial != {"Q1x1_H2": expected["initial"]["molecules_per_site"], "Q1_v": expected["initial"]["vacancies"]}:
        raise ValueError("Diagnostic MAT initial populations differ")
    resident = next(s for s in result["species"] if s["species_id"] == "H2-bound")
    site, = result["sites"]
    reaction, = result["reactions"]
    actual = dict(molecules_per_site=resident["molecules_per_reference"], occupied=site["occupied_fraction"],
                  vacancies=site["vacancy_fraction"], forward=reaction["forward_flux"], reverse=reaction["reverse_flux"])
    eq = expected["equilibrium"]
    for key in ("molecules_per_site", "occupied", "vacancies"):
        check_close(actual[key], eq[key], key, rel=0, absolute=limits["molecular_and_vacancy_final_abs"])
    check_close(2 * actual["molecules_per_site"] + actual["vacancies"], 1, "site inventory",
                rel=0, absolute=limits["inventory_balance_abs"])
    for key in ("forward", "reverse"):
        check_close(actual[key], eq[key], key, rel=limits["forward_reverse_and_exchange_flux_rel"], absolute=0)
    for key, target in (("kf", "kf_per_bar_s"), ("kr", "kr_per_s")):
        check_close(reaction[key], expected[target], key, rel=limits["forward_reverse_and_exchange_flux_rel"], absolute=0)
    ratio = reaction["kf"] * expected["P0_bar"] / reaction["kr"]
    check_close(ratio, expected["K_standard"], "standard-state ratio", rel=limits["standard_state_ratio_rel"], absolute=0)
    check_close(reaction["net_flux"], 0, "net equilibrium flux", rel=0, absolute=limits["abs_net_flux_per_reference_site_s"])
    return dict(case=binding["case"], initial=initial, final=actual, k_standard=ratio, net_flux=reaction["net_flux"])
