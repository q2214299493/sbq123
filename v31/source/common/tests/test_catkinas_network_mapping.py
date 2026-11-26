"""Offline mapping of real archived input bytes and deliberately unrepresentable synthetic networks."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.baseline_mkm.mapping_scope import topology
from scripts.baseline_mkm.network_mapping import EVIDENCE, map_network
from scripts.baseline_mkm.single_point import qualify
from scripts.kinetic_parameters.export import catkinas
from scripts.native_validation import cat_readback
from scripts.reaction_network.builder import build_network, directions
from test_catkinas_closed_cycle import cycle_model
from test_native_rate_adapters import cat_inputs

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/multiphase"


def read(path):
    return json.loads(path.read_bytes())


@pytest.fixture
def point():
    _, paths = cat_inputs("phase3_0")
    return tuple(read(paths[k]) for k in ("network_path", "dataset_path", "config_path")) + (paths["normalization_path"],)


def bind_version(n):
    n["network_version"] = sha256_json({k: v for k, v in n.items() if k != "network_version"})


def test_exact_native_bytes_and_identity_crosswalk(point):
    n, d, c, norm = point
    before = deepcopy((n, d, c))
    files, report = map_network(n, d, c, normalization_path=norm)
    assert (files, report) == map_network(n, d, c, normalization_path=str(norm))
    assert (n, d, c) == before
    receipt, paths = cat_inputs("phase3_0")
    assert sha256_file(receipt) == EVIDENCE["receipt_sha256"]
    assert sha256_file(paths["input_path"]) == EVIDENCE["input_sha256"]
    assert files["INPUT_phase25.m"].encode() == paths["input_path"].read_bytes()
    assert report["native_input_bytes_match_archive"] and not report["execution_authorized"]
    assert report["native_normalization"]["sites_per_reference"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert report["native_normalization"]["reference_basis"] == "reference_site_pair"
    assert report["conditions"]["partial_pressure_bar"] == c["partial_pressure_bar"]
    assert report["conditions"]["pressure_bar"] == 1.6 and report["conditions"]["temperature_K"] == 400
    assert report["observables"]["overall_stoichiometry"] == c["overall_stoichiometry"]
    m = report["mapping"]
    assert set(m["phases"]) == {"fcc-Ni", "fcc-Cu"}
    assert m["surfaces"] == {"facet-Ni": "fcc-Ni", "facet-Cu": "fcc-Cu"}
    assert m["interfaces"]["junction"]["participating_phase_ids"] == ["fcc-Cu", "fcc-Ni"]
    assert m["sites"]["top-Ni"]["native_index"] == 1 and m["sites"]["bridge-Cu"]["native_index"] == 2
    assert m["species"]["H2-top"]["native_token"] == "H#1"
    assert m["species"]["H2-bridge"]["native_token"] == "H#2"
    assert m["species"]["H2-bridge"]["composition"] == m["species"]["H2-top"]["composition"] == {"H": 1}
    for i, step in enumerate(n["reactions"], 1):
        rid = step["definition"]["reaction_id"]
        assert m["reactions"][rid]["native_index"] == i
        assert m["reactions"][rid]["direction"] == step["direction"]
        assert m["reactions"][rid]["provenance"]["parameter_set_id"] in step["parameter_set_ids"]
    ads = m["reactions"]["ads"]
    assert ads["forward"]["unit"] == "bar^-1 s^-1" and ads["reverse"]["unit"] == "s^-1"
    assert ads["forward"]["coefficient"] == pytest.approx(1062.5043325104702)
    assert ads["forward"]["gas_partial_pressure_orders"] == {"H2-g": 1}
    assert report["equation_forms"]["transfer"] == ["resident_transfer"]


def test_another_material_uses_project_sites_and_same_native_roles(tmp_path, point):
    n, d, c = cycle_model("oxide", with_network=True)
    norm = read(point[-1])
    norm["network_version"] = n["network_version"]
    norm["source"]["path"] = str(FIX / "closed_cycle_reference.json")
    path = tmp_path / "oxide-normalization.json"
    path.write_text(json.dumps(norm))
    files, report = map_network(n, d, c, normalization_path=path)
    assert files and report["issues"] == []
    sites = report["mapping"]["sites"].values()
    assert {r["site_type"] for r in sites} == {"acid", "basic-oxygen"}
    assert report["mapping"]["phases"] == ["solid"]
    assert not report["mapping"]["interfaces"]
    assert not report["execution_authorized"]


@pytest.mark.parametrize(("fixture", "entity", "identity", "status", "text"), [
    ("synthetic_oxide_site_network", "species", "co2-bound", "unsupported", "acid-A"),
    ("cross_phase_interface_product", "species", "contact-product", "unverified", "junction"),
    ("cross_phase_three_phase", "reaction", "combine", "unverified", "triple-junction"),
    ("cross_phase_three_phase", "reaction", "combine", "missing_evidence", "Reversibility unknown"),
    ("synthetic_interphase_transfer", "reaction", "move", "unverified", "operating-condition"),
    ("synthetic_interphase_transfer", "reaction", "move", "missing_evidence", "parameter binding"),
])
def test_draft_examples_keep_precise_issues_and_source(fixture, entity, identity, status, text):
    n = build_network(read(FIX / (fixture + ".json")))
    before = deepcopy(n)
    files, report = map_network(n)
    assert n == before and files == {} and report["native_input_hashes"] == {}
    assert report["status"] == "blocked" and report["execution_authorized"] is False
    assert any((i["entity"], i["id"], i["status"]) == (entity, identity, status) and text in i["reason"]
               for i in report["issues"])
    if fixture == "synthetic_interphase_transfer":
        assert report["equation_forms"]["move"] == ["resident_transfer"]


def test_equal_formulas_cannot_be_used_to_close_a_different_cycle(point):
    n, _, _, _ = point
    linked = next(s for s in n["species"] if s["species_id"] == "HNO-top")
    n["species"].append(dict(linked, species_id="other-resident", structure_id="other-isomer", configuration_id="isomer-b"))
    step = n["reactions"][-1]
    step["definition"]["reactants"] = {"other-resident": 1}
    step["direction"] = directions(step["definition"])
    bind_version(n)
    issues, forms = topology(n)
    assert all(forms.values())
    assert any(i["entity"] == "network" and "connected" in i["reason"] for i in issues)


def test_four_individually_matching_equations_can_have_incompatible_roles(point):
    # Two distinct synthetic feed states now have the same formula. All individual steps balance.
    n = point[0]
    species = {s["species_id"]: s for s in n["species"]}
    species["NO-g"].update(composition={"H": 2}, configuration_id="second-gas-state")
    for sid in ("HNO-top", "HNO-g"):
        species[sid]["composition"] = {"H": 3}
    step = n["reactions"][2]
    step["definition"]["reactants"] = {"H2-top": 1, "H2-g": 1}
    step["direction"] = directions(step["definition"])
    bind_version(n)
    issues, forms = topology(n)
    assert len(forms) == 4 and all(forms.values()) and len(n["species"]) == 6
    assert len(issues) == 1 and issues[0]["entity"] == "network" and "connected" in issues[0]["reason"]


@pytest.mark.parametrize("value", [False, None])
def test_no_manufactured_reverse(point, value):
    n = point[0]
    step = n["reactions"][1]
    step["definition"]["reversible"] = value
    step["direction"] = directions(step["definition"])
    bind_version(n)
    issues, _ = topology(n)
    expected = "missing_evidence" if value is None else "unsupported"
    assert any(i["id"] == "transfer" and i["status"] == expected for i in issues)


@pytest.mark.parametrize("bad", ["absent", "unequal", "wrong_source", "stale_network"])
def test_missing_or_conflicting_normalization_blocks_only_native_output(point, tmp_path, bad):
    n, d, c, orig = point
    opt = read(orig)
    opt["source"]["path"] = str(FIX / "closed_cycle_reference.json")
    if bad == "unequal":
        opt["sites_per_reference"]["top-Ni"] = 2
    elif bad == "wrong_source":
        opt["source"]["sha256"] = "0" * 64
    elif bad == "stale_network":
        opt["network_version"] = "0" * 64
    path = tmp_path / "normalization.json"
    path.write_text(json.dumps(opt))
    files, report = map_network(n, d, c, normalization_path=None if bad == "absent" else path)
    assert not files and [i["entity"] for i in report["issues"]] == ["normalization"]
    assert report["equation_forms"]["transfer"] == ["resident_transfer"]


@pytest.mark.parametrize(("change", "text"), [("dataset", "digest"), ("point", "reviewed condition"),
                                             ("setting", "Unmapped CATKINAS"), ("alias", "HNO-top")])
def test_fail_closed_on_binding_solver_or_identity_conflict(point, change, text):
    n, d, c, norm = point
    if change == "dataset":
        d["dataset_version"] = "0" * 64
    elif change == "point":
        c["temperature_K"] = 401
    elif change == "setting":
        c["catkinas"]["ThermoMode"] = 1
    else:
        c["catkinas"]["aliases"]["HNO-top"] = "H"
    files, report = map_network(n, d, c, normalization_path=norm)
    assert files == {} and any(text.lower() in i["reason"].lower() for i in report["issues"])


def test_isolated_parseable_step_is_not_a_validated_native_cycle(point):
    n = point[0]
    n["reactions"] = n["reactions"][:1]
    bind_version(n)
    files, report = map_network(n)
    assert not files and report["equation_forms"] == {"ads": ["dissociative_adsorption"]}
    assert report["native_execution_eligibility"] == "blocked"
    assert any(i["entity"] == "network" and "closed turnover" in i["reason"] for i in report["issues"])


def test_two_independent_contacts_are_not_one_native_interface(point):
    n = point[0]
    n["catalog"]["interfaces"].append(dict(n["catalog"]["interfaces"][0], interface_id="other-contact"))
    n["reactions"][1]["definition"]["interface_id"] = "other-contact"
    bind_version(n)
    issues, _ = topology(n)
    assert any(i["id"] == ["junction", "other-contact"] and "multiple contacts" in i["reason"] for i in issues)


def test_site_specific_initial_state_readback(point):
    n, d, c, _ = point
    c["catkinas"]["initial_coverages"].update({"H2-top": 0.25, "HNO-top": 0.125, "H2-bridge": 0.5})
    files, manifest = qualify(n, d, c)
    native = files["INPUT_phase25.m"]
    assert "Q1_v_INIT = 0.625;" in native and "Q2_v_INIT = 0.5;" in native
    files["INPUT_phase25.m"] = native.replace("Q1_v_INIT = 0.625;", "Q1_v_INIT = 0.5;")
    with pytest.raises(ValueError, match="vacancy"):
        cat_readback(files, catkinas(d), manifest["validation"], initial_coverages=c["catkinas"]["initial_coverages"])


def test_cli_blocked_does_not_write_a_native_model(tmp_path):
    source = tmp_path / "oxide.json"
    source.write_text(json.dumps(build_network(read(FIX / "synthetic_oxide_site_network.json"))))
    digest = sha256_file(source)
    target, report = tmp_path / "native", tmp_path / "report.json"
    proc = subprocess.run([sys.executable, "-m", "scripts.baseline_mkm.network_mapping", str(source),
                           "--output-dir", str(target), "--report", str(report)], cwd=ROOT, capture_output=True)
    assert proc.returncode == 2 and read(report)["status"] == "blocked"
    assert sha256_file(source) == digest and not target.exists()
