"""Native-byte replay and negative controls; none of these tests launch a solver."""
from pathlib import Path

import pytest
from scipy.io import loadmat, savemat

from scripts.artifact_io import load_json_object as read, sha256_file, write_json_exclusive as save
from scripts.baseline_mkm import single_point as flow
from scripts.baseline_mkm.analysis import analyze
from scripts.baseline_mkm.normalization import normalization
from scripts.baseline_mkm.rate_adapter import adapt
from scripts.baseline_mkm.results import result_quality
from scripts.baseline_mkm.single_point_result import species_and_sites
from scripts.kinetic_parameters.export import catkinas
from scripts.native_model import assemble
from scripts.rate_output_v2 import validate_network_bound_rate_output
from test_mkm_single_point import OUT, PHASE, runtime  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
PROFILE = PHASE.parent / "phase3_1/benchmark_normalization.json"
RUN = ROOT / "archive/v221_catkinas/nicu-v221-400k-001"
MODES = "ThermoMode = 0;\nBarrierMode = -2;\nConsMode = 0;"
MAPPING = {"site_indices": {"top-Ni": 1, "bridge-Cu": 2}}
WARNINGS = ("Warning: find a undefined atom symbol : # in the molecule #1, please use the standard atom symbol !\n"
            "Warning: no thermodynamics data of HNO is found, use 0 as default value!")


@pytest.mark.parametrize("defect", ["absent", "swapped", "wrong_count", "fraction", "bad_config", "stale_source"])
def test_normalization_fails_closed(tmp_path, defect):
    net = read(PHASE / "closed_cycle_network.json")
    profile = read(PROFILE)
    profile["source"]["path"] = str((PROFILE.parent / profile["source"]["path"]).resolve())
    config = read(PHASE / "workflow_configuration.json")
    if defect == "swapped":
        profile["reference_basis"] = "reference_site"
    elif defect == "wrong_count":
        profile["sites_per_reference"]["bridge-Cu"] = 2
    elif defect == "fraction":
        profile["sites_per_reference"]["top-Ni"] = 1.0
    elif defect == "bad_config":
        config["turnover_basis"] = "individual_site"
    elif defect == "stale_source":
        profile["source"]["sha256"] = "0" * 64
    path = save(tmp_path / "norm.json", profile)
    with pytest.raises(ValueError):
        normalization(None if defect == "absent" else path, net, config)


def test_prepare_blocks_missing_profile(tmp_path, runtime):  # noqa: F811
    view = flow.prepare(tmp_path / "point", PHASE / "closed_cycle_network.json", OUT / "cycle_dataset.json",
                        PHASE / "workflow_configuration.json", *runtime, tmp_path / "inert")
    assert view["stage"] == "REJECTED" and view["execution"] == "not_started"
    assert "normalization" in view["missing_data"]


def test_thermal_and_marker_boundaries(tmp_path):
    reviewed = read(PHASE / "result.json")
    mat = PHASE / "data1.mat"
    log = MODES + "\n" + WARNINGS
    q = result_quality(mat, log, MAPPING, reviewed, MODES)
    assert q["species_with_default_zero"] == ["HNO"] and q["species_thermochemistry"] == "unqualified"
    assert [w["classification"] for w in q["warnings"]] == [
        "known_site_marker_warning", "unused_kinetic_thermochemistry_fallback"]
    for key, value in (("ThermoMode = 0", "ThermoMode = 1"), ("BarrierMode = -2", "BarrierMode = 0"),
                       ("molecule #1", "molecule #7"), ("symbol : #", "symbol : X")):
        with pytest.raises(ValueError):
            result_quality(mat, log.replace(key, value), MAPPING, reviewed, MODES)
    data = loadmat(mat, variable_names=["Eao", "Ean", "G0o", "G0n"])
    data["G0o"][0, 0] += 0.01
    fake = tmp_path / "changed.mat"
    savemat(fake, {k: v for k, v in data.items() if not k.startswith("_")})
    with pytest.raises(ValueError, match="G0o/G0n"):
        result_quality(fake, log, MAPPING, reviewed, MODES)
    dataset = read(OUT / "cycle_dataset.json")
    config = read(PHASE / "workflow_configuration.json")
    config["catkinas"]["ThermoMode"] = 1
    with pytest.raises(ValueError, match="reviewed species thermochemistry"):
        assemble("catkinas", dataset, config)
    table = catkinas(dataset)
    table["species"][0]["composition"]["#1"] = 1
    with pytest.raises(ValueError, match="chemical composition"):
        species_and_sites(table, MAPPING, {}, config)


@pytest.mark.skipif(not RUN.is_dir(), reason="requires local read-only copy of the complete accepted run")
def test_actual_accepted_native_replay():
    paths = {p: sha256_file(p) for p in RUN.rglob("*") if p.is_file()}
    network, dataset, config, result = [RUN / f"{k}.json" for k in ("network", "dataset", "configuration", "result")]
    old = read(result)
    payload, q = adapt(RUN / "ACCEPTED.json", network_path=network, dataset_path=dataset,
                       config_path=config, input_path=RUN / "input" / flow.INPUT, normalization_path=PROFILE, root=ROOT)
    validate_network_bound_rate_output(payload, network)
    corrected = q["single_point_replay"]
    assert corrected["reactions"] == old["reactions"] and len(corrected["reactions"]) == 4
    for field in ("species", "sites", "gas_net_production", "steady_state_residual", "overall_rate", "validation"):
        assert corrected[field] == old[field]
    a = analyze(network, dataset, config, result, flow.accepted_receipt(RUN), PROFILE)
    assert payload["native_normalization"]["basis_kind"] == corrected["turnover_basis"] == a["tof"]["reference_basis"]
    assert a["native_reference"] == corrected["normalization"]
    assert all(row["flux_unit"] == corrected["flux_unit"] for row in a["rates"]["reactions"])
    assert corrected["tof_s_inverse"] == a["tof"]["overall"]["per_site_pair_s"] == 81.5127701616477
    assert corrected["mean_tof_per_individual_site_s"] == a["tof"]["overall"]["per_site_s"] == 40.75638508082385
    assert all(abs(row["residual"]) <= 1e-12 for row in a["selectivity"]["element_balance"].values())
    log = (RUN / "runtime/result_phase25/log1").read_text(errors="replace")
    org = loadmat(RUN / "runtime/result_phase25/ORG1.mat", variable_names=["ORG"], simplify_cells=True)["ORG"]
    assert org["AtomList"].tolist() == ["H", "N", "O"]
    assert org["MrList0"][-2:].tolist() == [0.0, 0.0]
    assert "HNO" not in {entry["ChemForm"] for entry in org["Thermodynamics_data"]}
    assert all(org[k] == v for k, v in q["quality"]["modes"].items())
    assert "Thermodynamic summary:" in log and "dG =  -0.160 eV" in log
    assert q["quality"]["site_markers"] == {"#1": "top-Ni", "#2": "bridge-Cu"}
    assert q["quality"]["species_with_default_zero"] == ["HNO"]
    assert sum(w["classification"] == "known_site_marker_warning" for w in q["quality"]["warnings"]) == 2
    assert paths == {p: sha256_file(p) for p in RUN.rglob("*") if p.is_file()}
