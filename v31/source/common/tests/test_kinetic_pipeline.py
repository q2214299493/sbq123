"""Offline reaction-to-model tests with archive values and independent input mutations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.artifact_io import sha256_json
from scripts.kinetic_data.project_inspection import inspect_project
from test_kinetic_parameters import FIX, case, dataset, signed
from test_thermochemistry import case as thermal_case, correction_review, synthetic_upload

ROOT = Path(__file__).resolve().parents[1]
F12 = ROOT / "reports/workflow_design/stage_f1_2"
V21 = ROOT / "reports/workflow_development/stage_v2_1"
MP = ROOT / "reports/multiphase"
RID = "fe110_ch_co_to_chco_20261109"


def read(path):
    return json.loads(path.read_bytes())


def run_case(name):
    folder = F12 / name
    p = V21 / "fe110_project.yaml" if name == "fe110" else folder / "project.yaml"
    result = subprocess.run([sys.executable, "-m", "scripts.scientific_intake", "--kinetic-readiness",
                             p, folder / "task.yaml"], cwd=ROOT, capture_output=True, check=True)
    doc = json.loads(result.stdout)
    assert doc["execution_authorized"] is False
    return doc["contexts"][0]


def test_nicu_model_and_archived_result():
    ctx = run_case("nicu")
    pipe = ctx["kinetic_readiness"]
    assert set(pipe["reactions"]) == {"ads", "transfer", "hydrogenate", "desorb"}
    row = pipe["reactions"]["ads"]
    assert all(r["status"] == "qualified" for r in pipe["reactions"].values())
    assert row["thermochemistry"]["energies"]["gibbs_ev"] == dict(forward=0.4, reverse=0.5, reaction=-0.1)
    assert row["thermochemistry"]["closure_checked"] and row["kinetics"]["detailed_balance_established"]
    assert row["kinetics"]["rates"]["forward"]["activity_coefficient_s^-1"] == pytest.approx(1062.50433251)
    assert row["kinetics"]["rates"]["reverse"]["activity_coefficient_s^-1"] == pytest.approx(58.39641191)
    assert row["native_normalization"]["basis_kind"] == "reference_site_pair"
    assert ctx["observables"]["tof"]["value"]["value"] == pytest.approx(81.5127701616477, abs=1e-12, rel=0)
    assert [r["reaction_id"] for r in ctx["observables"]["stable_drc"]["value"]] == ["hydrogenate", "transfer"]
    mkm = ctx["engines"]["mkm"]
    assert row["engines"]["mkm"]["status"] == mkm["status"] == "input_eligible"
    assert ctx["engines"]["kmc"]["status"] == "blocked"
    assert mkm["archived_input_hashes_match"] and not mkm["execution_authorized"]
    assert mkm["files"]["INPUT_phase25.m"].encode() == (MP / "phase2_5_2/catkinas_closed_cycle_input.m").read_bytes()


def test_fe_partial_states_and_unknown_reverse():
    ctx = run_case("fe110")
    row = ctx["kinetic_readiness"]["reactions"][RID]
    t = row["thermochemistry"]
    assert row["status"] == "blocked" and t["route"] == "state_intake"
    assert [t["electronic_sources"][state]["value"]["value_ev"] for state in ("IS", "TS", "FS")] == [
        -385.14767079, -384.17406905, -384.48836276]
    assert t["energies"]["electronic_ev"] == pytest.approx(dict(forward=0.97360174, reverse=0.31429371, reaction=0.65930803))
    assert t["states"]["TS"]["zpe_ev"] == pytest.approx(0.51405165)
    assert t["states"]["TS"]["excluded_reaction_coordinate_one_based"] == 12
    assert t["states"]["IS"] is t["states"]["FS"] is None
    assert t["energies"]["gibbs_ev"] == dict(forward=None, reverse=None, reaction=None)
    assert not t["closure_checked"]
    assert row["kinetics"]["directions"]["reverse"]["status"] == "unknown"
    assert row["kinetics"]["rates"] == {"forward": None, "reverse": None}
    assert all(row["engines"][e]["status"] == "blocked" for e in ("mkm", "kmc"))


def test_oxide_mapping_and_failed_initialization():
    ctx = run_case("oxide")
    obs = ctx["observables"]
    graph = obs["lattice"]["value"]
    assert graph["classification"] == "synthetic_test_assumption" and len(graph["matrix_node_order"]) == 7
    assert len(graph["initial_bridges"]) == 2
    assert graph["inventories"] == {"acid-A": {"capacity": 4, "occupied": 2, "vacant": 2},
                                   "oxygen-B": {"capacity": 3, "occupied": 2, "vacant": 1}}
    assert obs["native_initialization"]["value"]["fatal"]["code"] == 1002
    assert obs["candidate_input"]["value"]["native_qualified"] is None
    row = ctx["kinetic_readiness"]["reactions"]["fixture-adsorption"]
    assert row["engines"]["kmc"]["usable_outputs"] == ["lattice"]
    assert ctx["engines"]["kmc"]["status"] == "blocked"


def local_run(directory, network, *, refs=None, version=None, change=None, phase=None):
    sources = {}
    for role, data in dict(network=network, **(refs or {})).items():
        path = directory / (role + ".json")
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        sources[role] = {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
    if change:
        path = directory / sources[change]["path"]
        path.write_bytes(path.read_bytes() + b" ")
    task = dict(task_id="offline", sources=sources, network_version=version or network["network_version"], thermal_phase=phase)
    project = dict(project_id=network["project_id"], version=1, evidence_base=".")
    for name, obj in (("project", project), ("task", task)):
        (directory / (name + ".yaml")).write_text(yaml.safe_dump(obj), encoding="utf8")
    return inspect_project(directory / "project.yaml", directory / "task.yaml", kinetic_readiness=True)["contexts"][0]


def test_one_missing_binding_preserves_independent_reactions(tmp_path):
    network = read(MP / "phase3_0/closed_cycle_network.json")
    data = read(MP / "phase2_5_2/cycle_dataset.json")
    models = {"network_version": network["network_version"],
              "models": [r["model"] for r in data["reactions"] if r["reaction_id"] != "ads"]}
    ctx = local_run(tmp_path, network, refs={"models": models})
    rows = ctx["kinetic_readiness"]["reactions"]
    assert rows["ads"]["kinetics"]["rates"]["forward"] is None
    assert rows["ads"]["status"] == "blocked"
    assert rows["transfer"]["status"] == "qualified"
    assert rows["transfer"]["kinetics"]["rates"]["forward"]["activity_coefficient_s^-1"] > 0
    assert rows["transfer"]["engines"]["mkm"]["status"] == "parameters_qualified"
    assert ctx["engines"]["mkm"]["status"] == "blocked"


def test_binding_and_evidence_failure(tmp_path):
    n = read(MP / "phase3_0/closed_cycle_network.json")
    wrong = local_run(tmp_path, n, version="0" * 64)
    assert wrong["kinetic_readiness"]["reactions"] == {} and wrong["kinetic_readiness"]["issues"]
    assert wrong["evidence"]["network"]["status"] == "invalid_reference"
    d = read(MP / "phase2_5_2/cycle_dataset.json")
    changed = local_run(tmp_path, n, refs={"dataset": d}, change="dataset")
    assert changed["evidence"]["dataset"]["status"] == "hash_mismatch"
    assert all(r["kinetics"] is None for r in changed["kinetic_readiness"]["reactions"].values())
    assert "files" not in changed["engines"]["mkm"]


def test_one_invalid_inventory_is_local(tmp_path):
    n = read(MP / "phase3_0/closed_cycle_network.json")
    n["reactions"][0]["definition"]["sites_consumed"]["top-Ni"] = 2
    n["network_version"] = sha256_json({k: v for k, v in n.items() if k != "network_version"})
    ctx = local_run(tmp_path, n)
    rows = ctx["kinetic_readiness"]["reactions"]
    assert rows["ads"]["status"] == "invalid_input"
    assert "conservation failed" in rows["ads"]["conservation"]["invalid"]
    assert rows["transfer"]["thermochemistry"]["closure_checked"]


@pytest.mark.parametrize("bad_link", [False, True])
def test_kmc_input_generation_and_unsupported_topology(tmp_path, bad_link):
    n, model = case(system="interface", gas="dissociative")
    c = read(FIX / "native_interface_config.json")
    c["dataset_version"] = dataset(n, model)["dataset_version"]
    if bad_link:
        c["zacros"]["links"][0][2] = "unsupported-direction"
    ctx = local_run(tmp_path, n, refs={"models": signed(n, model), "kmc_configuration": c})
    kmc = ctx["engines"]["kmc"]
    assert kmc["status"] == ("blocked" if bad_link else "input_eligible")
    assert ctx["engines"]["mkm"]["status"] == "blocked"
    if bad_link:
        assert "unsupported-direction" in kmc["missing"][0]
    else:
        assert {"simulation_input.dat", "mechanism_input.dat", "lattice_input.dat", "energetics_input.dat"} <= kmc["files"].keys()
        assert not kmc["execution_authorized"]


@pytest.mark.parametrize("absent", [None, "IS", "FS"])
def test_three_state_thermal_handoff_and_missing_endpoints(tmp_path, absent):
    # Isolated analytical fixture: identical 0.15 eV state corrections cancel exactly.
    n = read(next((MP / "networks").glob("network-2a*.json")))
    intake = thermal_case()
    extra = synthetic_upload(intake, ("IS", "TS", "FS"))["records"]
    intake["records"] = [r for r in intake["records"] if r["kind"] != "spectrum"] + [r for r in extra if r["state"] != absent]
    ts = extra[1]
    review = {"grade": "A", "review_reference": "synthetic unit test", "assignment": "synthetic coordinate",
              "structure_identity": ts["value"]["structure_identity"], "correction_review": correction_review(ts)}
    ctx = local_run(tmp_path, n, refs={"intake": intake, "ts_review": review})
    row = ctx["kinetic_readiness"]["reactions"][RID]
    t = row["thermochemistry"]
    if absent:
        assert t["states"][absent] is None
        assert f"{absent}.corrections" in t["issues"]
        assert t["closure_residual_ev"] is None
    else:
        assert t["energies"]["gibbs_ev"] == pytest.approx(dict(forward=0.97360174, reverse=0.31429371, reaction=0.65930803))
        assert t["closure_residual_ev"] == pytest.approx(0, abs=1e-9)
        assert "bind a new snapshot" in row["missing"][0]
    assert ctx["engines"]["mkm"]["status"] == "blocked"


def test_changed_spectrum_without_observable_selection(tmp_path):
    n = read(next((MP / "networks").glob("network-2a*.json")))
    intake = thermal_case()
    source = next(r["provenance"]["source_reference"] for r in intake["records"] if r["kind"] == "spectrum")
    local = tmp_path / source
    local.parent.mkdir(parents=True)
    local.write_bytes(b"modified frequency output")
    ctx = local_run(tmp_path, n, refs={"intake": intake})
    row = ctx["kinetic_readiness"]["reactions"][RID]
    assert row["status"] == "invalid_input" and row["thermochemistry"] is None
    assert row["kinetics"] is None and "hash_mismatch" in row["missing"][0]


def test_conflicting_archive_and_models_preserves_unaffected_rows(tmp_path):
    n = read(MP / "phase3_0/closed_cycle_network.json")
    d = read(MP / "phase2_5_2/cycle_dataset.json")
    models = {"network_version": n["network_version"],
              "models": [r["model"] for r in d["reactions"] if r["reaction_id"] != "ads"]}
    ctx = local_run(tmp_path, n, refs={"models": models, "dataset": d})
    rows = ctx["kinetic_readiness"]["reactions"]
    assert rows["ads"]["status"] == "invalid_input" and rows["ads"]["kinetics"] is None
    assert rows["transfer"]["status"] == "qualified"
    assert ctx["engines"]["mkm"]["status"] == "blocked"
