"""Network construction, scientific checks and immutable publication. Synthetic except the Fe(110) regression."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_json
from scripts.reaction_network.__main__ import publish
from scripts.reaction_network.builder import artifact_hashes, build_network, from_registry_mapping
from scripts.reaction_network.thermodynamics import check_cycles
from test_multiphase_contracts import reviewed_example

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/multiphase"


def bundle():
    return json.loads((ROOT / "tests/fixtures/multiphase/valid.json").read_bytes())


def native():
    data = bundle()
    data["format"] = "network-definition/1"
    return data


def snapshot(data, **kwargs):
    return build_network(data, **kwargs)["reactions"][0]


def test_phase1_bundle_site_stoichiometry_and_coverage():
    n = build_network(bundle())
    r = n["reactions"][0]
    assert r["level"] == "THERMODYNAMICALLY_VALID" and r["mkm_status"] == "blocked"
    assert r["site_balance"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert r["direction"]["reverse"]["sites_released"] == r["definition"]["sites_consumed"]
    assert len(set(n["species_fingerprints"].values())) == 3
    assert n["parameter_sets"][0]["coverage_terms"] == bundle()["parameter_sets"][0]["coverage_terms"]


def test_species_fingerprint_catalog_phase_facet_and_configuration():
    b = bundle()
    before = build_network(b)["species_fingerprints"]
    b["surfaces"][0]["miller_indices"] = [1, 0, 0]
    after = build_network(b)["species_fingerprints"]
    assert before["H2-g"] == after["H2-g"] and before["H2-top"] != after["H2-top"]
    b["phases"][0]["phase_id"] = b["surfaces"][0]["phase_id"] = "other-Ni"
    b["reactions"][0]["phase_ids"][0] = "other-Ni"
    assert build_network(b)["species_fingerprints"]["H2-top"] != after["H2-top"]


@pytest.mark.parametrize("change,reason", [("id", "Duplicate"), ("species", "Duplicate species fingerprint"),
                                            ("reaction", "Duplicate elementary reaction"), ("dangling", "unknown species"),
                                            ("atom", "element conservation"), ("charge", "charge conservation"),
                                            ("site", "site conservation"), ("surface", "surface domain"),
                                            ("interface", "different interface"), ("phase", "phases differ")])
def test_invalid_native_network(change, reason):
    d = native()
    r = d["reactions"][0]
    if change in ("id", "species"):
        replica = copy.deepcopy(d["species"][0])
        if change == "species":
            replica["species_id"] = "alias"
        d["species"].append(replica)
    elif change == "reaction":
        replica = copy.deepcopy(r)
        replica.update(reaction_id="backwards", reactants=r["products"], products=r["reactants"],
                       sites_consumed=r["sites_released"], sites_released=r["sites_consumed"])
        d["reactions"].append(replica)
    elif change == "dangling":
        r["products"] = {"absent": 1}
    elif change in ("atom", "charge"):
        d["species"][0].update({"composition": {"H": 1}} if change == "atom" else {"charge": -1})
    elif change == "site":
        r["sites_consumed"]["top-Ni"] = 2
    elif change == "surface":
        r["sites_released"] = {"fake": 1}
    elif change == "interface":
        d["interfaces"].append(dict(d["interfaces"][0], interface_id="other"))
        d["species"][1]["interface_id"] = "other"
    else:
        r["phase_ids"] = []
    with pytest.raises(ValueError, match=reason):
        build_network(d)


@pytest.mark.parametrize("kind", ["adsorption", "desorption", "dissociation", "hydrogenation", "dehydrogenation",
                                  "c_c_coupling", "c_o_cleavage", "diffusion", "multi_site", "interfacial"])
def test_endpoint_candidate_preserves_supplied_classification(kind):
    d = native()
    r = d["reactions"].pop()
    d["parameter_sets"] = []
    d["endpoint_candidates"] = [{"reaction_id": "candidate", "reaction_type": kind, "surface_ids": r["surface_ids"],
                                  "interface_id": "junction", "initial": {"structure_id": "A", "species_ids": ["H2-g"]},
                                  "final": {"structure_id": "B", "species_ids": ["H2-bridge"]}}]
    candidate = snapshot(d)
    assert candidate["origin"] == "geometric_inference" and candidate["level"] == "DRAFT"
    assert candidate["definition"]["reaction_type"] == kind
    assert candidate["direction"]["status"] == "unknown" and candidate["direction"]["reverse"] is None
    assert candidate["energies"]["electronic_ev"]["reverse"] is None


def test_irreversible_uses_no_reverse_law():
    d = native()
    d["reactions"][0]["reversible"] = False
    with pytest.raises(ValueError, match="Irreversible"):
        build_network(d)
    d["parameter_sets"][0]["reverse"] = None
    r = snapshot(d)
    assert r["direction"]["status"] == "irreversible" and r["direction"]["reverse"] is None
    assert r["energies"]["electronic_ev"]["reverse"] is not None


@pytest.mark.parametrize("kind", ["electronic_energies", "free_energies"])
def test_independent_forward_reverse_closure(kind):
    d = native()
    triple = d["reactions"][0][kind]
    if kind == "free_energies":
        triple = triple["values"]
    triple["reverse"]["value"] += 0.1
    with pytest.raises(ValueError, match="closure"):
        build_network(d)


def test_incompatible_reference_and_missing_thermochemistry():
    d = native()
    r = d["reactions"][0]
    r["free_energies"] = None
    assert snapshot(d)["level"] == "STRUCTURALLY_VALID"
    r["electronic_energies"]["forward"]["reference_id"] = "other"
    with pytest.raises(ValueError, match="reference"):
        build_network(d)


def test_thermodynamic_cycle_uses_stoichiometry_and_conditions():
    def edge(a, b, energy):
        return {"definition": {"energy_reference_id": "common"}, "site_balance": {}, "net_stoichiometry": {a: -1, b: 1},
                "energies": {"electronic_ev": {"reaction": None}, "gibbs_ev": {"reaction": energy},
                             "temperature_k": 400, "standard_state": "example"}}
    rows = [edge("a", "b", 1), edge("b", "c", 2), edge("a", "c", 3)]
    assert check_cycles(rows) == 1
    rows[-1]["energies"]["gibbs_ev"]["reaction"] = 3.3
    with pytest.raises(ValueError, match="cycle"):
        check_cycles(rows)
    rows[-1]["energies"]["temperature_k"] = 500
    assert check_cycles(rows) == 0


def test_confirmed_mapping_retains_inference_and_scoped_decision():
    d = native()
    d["species"][1]["site_occupancy"] = None
    r = d["reactions"][0]
    r["sites_consumed"] = r["sites_released"] = None
    record = {"id": "map", "state": "reaction", "kind": "site_mapping", "mode": "USER_PROVIDED",
              "validation": {"validation_status": "unreviewed", "validated_properties": [], "compatibility_status": "unknown",
                             "limitations": ["Scoped mapping test"]},
              "acceptance": {"acceptance_status": "accepted", "acceptance_scope": ["site_mapping"], "accepted_by": "fixture",
                             "acceptance_reason": "test", "acceptance_timestamp": "2026-11-19T12:00:00Z"},
              "value": {"occupancies": [{"species": "H2-bridge", "site_type": s, "multiplicity": 1}
                                        for s in ("top-Ni", "bridge-Cu")],
                        "sites_consumed": [{"site_type": s, "count": 1} for s in ("top-Ni", "bridge-Cu")],
                        "sites_released": [], "interface_assignment": "junction", "reaction_classification": "adsorption"}}
    doc = {"schema_version": 1, "reaction_id": "ads", "records": [record]}
    n = build_network(d, intakes=[doc])
    assert n["species"][1]["adsorption_geometry"] == d["species"][1]["adsorption_geometry"]
    assert n["species"][1]["site_occupancy"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert n["reactions"][0]["user_confirmation"]["acceptance"] == record["acceptance"]
    assert d["species"][1]["site_occupancy"] is None
    record["acceptance"] = {"acceptance_status": "pending"}
    assert snapshot(d, intakes=[doc])["site_balance"] is None


def test_external_user_definition_preserves_decision_and_source():
    d = native()
    r = d["reactions"][0]
    r["provenance"].append({"source_type": "literature", "source_reference": "synthetic bibliographic example"})
    r["user_confirmation"] = {"definition_sha256": sha256_json(r), "acceptance_status": "accepted",
                              "acceptance_scope": ["reaction_definition"], "accepted_by": "example",
                              "acceptance_reason": "reviewed definition", "acceptance_timestamp": "2026-11-19T12:00:00Z"}
    assert snapshot(d)["user_confirmation"]["accepted_by"] == "example"
    r["reaction_type"] = "adsorption"
    with pytest.raises(ValueError, match="different reaction"):
        build_network(d)


def test_explicit_scientific_and_kinetic_reviews_are_separate():
    d = bundle()
    reaction, param = reviewed_example(d)
    hashes = set(artifact_hashes(d))
    ts = [{"grade": "A", "review_reference": "fixture-assignment", "assignment": "fixture motion",
           "reaction_id": "ads", "structure_identity": reaction["ts_id"]}]
    r = snapshot(d, verified_hashes=hashes, ts_reviews=ts)
    assert r["level"] == "THERMODYNAMICALLY_VALID"
    def decision(r):
        return dict(reaction_id="ads", subject_sha256=r["subject_sha256"], decision="accepted", reviewer="fixture",
                    reason="synthetic gate test", reviewed_at="2026-11-19T10:00:00Z")
    assert snapshot(d, decisions=[decision(r)], ts_reviews=ts)["level"] == "THERMODYNAMICALLY_VALID"
    without_ts = snapshot(d)
    assert snapshot(d, decisions=[decision(without_ts)], verified_hashes=hashes)["level"] == "THERMODYNAMICALLY_VALID"
    assert snapshot(d, decisions=[decision(r)], verified_hashes=hashes, ts_reviews=ts)["level"] == "KINETICALLY_ELIGIBLE"
    param["eligibility"] = "draft"
    with pytest.raises(ValueError, match="Stale network review"):
        build_network(d, decisions=[decision(r)], verified_hashes=hashes, ts_reviews=ts)
    pending = snapshot(d, ts_reviews=ts)
    assert snapshot(d, decisions=[decision(pending)], verified_hashes=hashes, ts_reviews=ts)["level"] == "SCIENTIFICALLY_ACCEPTED"


def test_immutable_versions_and_collision_marker(tmp_path):
    d = bundle()
    a = build_network(d)
    path = publish(a, tmp_path)
    assert publish(a, tmp_path) == path
    d["species"][2]["adsorption_geometry"] = "different configuration"
    b = build_network(d)
    assert publish(b, tmp_path) != path and json.loads(path.read_bytes()) == a
    path.write_text("{}")
    with pytest.raises(ValueError, match="differs"):
        publish(a, tmp_path)
    assert path.read_text() == "{}"


def test_fe110_draft_matches_archived_scientific_evidence():
    m = json.loads((REPORTS / "ch_co_registry_mapping_20261119.json").read_bytes())
    t = json.loads((REPORTS / "phase2_2_chco_validation.json").read_bytes())["calculation"]
    intake = json.loads((REPORTS / "ch_co_intake_20261119.json").read_bytes())
    d = from_registry_mapping(m, "sbq123")
    r = snapshot(d, thermochemistry=[t], intakes=[intake])
    assert r["definition"]["source_states"] == m["source_states"]
    assert r["energies"]["electronic_ev"] == pytest.approx(dict(forward=.97360174, reverse=.31429371, reaction=.65930803))
    assert r["thermochemistry"]["states"]["TS"]["zpe_ev"] == pytest.approx(.51405165)
    assert r["site_balance"] is None and r["direction"]["status"] == "unknown"
    assert all(v is None for v in r["energies"]["gibbs_ev"].values())
    assert r["level"] == "DRAFT" and r["mkm_status"] == "blocked"
    t["states"]["TS"]["structure_identity"] = "wrong"
    with pytest.raises(ValueError, match="thermal structure"):
        snapshot(d, thermochemistry=[t])


def synthetic_thermal_network():
    d = native()
    d["parameter_sets"] = []
    r = d["reactions"][0]
    r["free_energies"] = None
    energies = {"IS": 0.0, "TS": 0.5, "FS": -0.1}
    corrections = {"IS": 0.1, "TS": 0.2, "FS": 0.05}
    ids = {"IS": r["initial_structure_id"], "TS": r["ts_id"], "FS": r["final_structure_id"]}
    electronic = {"forward": 0.5, "reverse": 0.6, "reaction": -0.1}
    for k, term in r["electronic_energies"].items():
        term["value"] = electronic[k]
    states = {s: dict(temperature_k=400, standard_state="example", thermal_basis="sample",
                      gibbs_correction_ev=corrections[s], structure_identity=ids[s]) for s in ids}
    calc = dict(reaction_id="ads", states=states, status="complete", issues=[],
                electronic_sources={s: {"value": dict(value_ev=energies[s], structure_identity=ids[s],
                                                      energy_reference=r["energy_reference_id"])} for s in ids},
                condition_values={"temperature_k": 400, "standard_state": "example"}, electronic_ev=electronic,
                state_free_energy_ev={s: energies[s] + corrections[s] for s in ids},
                reaction=dict(electronic_ev=electronic, thermal_ev=dict(forward=.1, reverse=.15, reaction=-.05),
                              free_energy_ev=dict(forward=.6, reverse=.75, reaction=-.15)))
    return d, calc


def test_bound_thermochemistry_populates_missing_free_energies():
    d, calc = synthetic_thermal_network()
    r = snapshot(d, thermochemistry=[calc])
    assert r["level"] == "THERMODYNAMICALLY_VALID" and r["energies"]["gibbs_ev"]["reaction"] == -.15


@pytest.mark.parametrize("field,value", [("temperature_k", 300), ("standard_state", "other"),
                                          ("thermal_basis", "other"), ("structure_identity", "wrong"),
                                          ("gibbs_correction_ev", 1.2)])
def test_bound_thermochemistry_rejects_mismatches(field, value):
    d, calc = synthetic_thermal_network()
    calc["states"]["TS"][field] = value
    with pytest.raises(ValueError):
        snapshot(d, thermochemistry=[calc])


def test_missing_rate_direction_reported_for_draft():
    d = native()
    d["parameter_sets"][0]["reverse"] = None
    assert any("missing reverse" in x for x in snapshot(d)["gaps"])


def test_native_parameter_conditions_and_barrier_must_match():
    d = native()
    p = d["parameter_sets"][0]
    p["temperature_K"] = 399
    with pytest.raises(ValueError, match="Gibbs convention"):
        build_network(d)
    p["temperature_K"] = 400
    p["forward"]["activation_energy"]["value"] += .2
    with pytest.raises(ValueError, match="activation energy"):
        build_network(d)


def test_partial_external_electronic_intake_only_derives_supported_differences():
    d = native()
    r = d["reactions"][0]
    r.update(electronic_energies=None, free_energies=None, reversible=None, provenance=[])
    records = []
    for state, identity, energy in (("IS", r["initial_structure_id"], -2), ("FS", r["final_structure_id"], -1.7)):
        for kind, value in (("structure", {"identity": identity, "reference": "fixture structure"}),
                            ("electronic_energy", {"structure_identity": identity, "value_ev": energy,
                                                   "energy_reference": r["energy_reference_id"]})):
            records.append(dict(id=f"{state}-{kind}", kind=kind, value=value, state=state, mode="LITERATURE_EXTERNAL",
                                validation=dict(validation_status="validated", validation_method="fixture",
                                                validated_properties=[kind], compatibility_status="compatible", limitations=[]),
                                provenance={"source_type": "literature", "source_reference": "fixture table"},
                                acceptance={"acceptance_status": "pending"}))
    doc = {"schema_version": 1, "reaction_id": "ads", "records": records}
    result = snapshot(d, intakes=[doc])
    assert result["energies"]["electronic_ev"] == {"forward": None, "reverse": None, "reaction": pytest.approx(.3)}
    assert result["direction"]["status"] == "unknown" and result["direction"]["reverse"] is None
    assert result["level"] == "STRUCTURALLY_VALID"


def test_cli_reproduces_versioned_fe110_artifact(tmp_path):
    args = [sys.executable, "-m", "scripts.reaction_network", str(REPORTS / "ch_co_registry_mapping_20261119.json"),
            "--project-id", "sbq123", "--intake", str(REPORTS / "ch_co_intake_20261119.json"),
            "--thermochemistry", str(REPORTS / "phase2_2_chco_validation.json"), "--output-dir", str(tmp_path)]
    path = Path(subprocess.check_output(args, text=True).strip())
    expected = json.loads((REPORTS / "phase2_3_chco_network_validation.json").read_bytes())
    assert path.read_bytes() == (REPORTS / "networks" / path.name).read_bytes()
    n = json.loads(path.read_bytes())
    assert expected["network_version"] == n["network_version"] and expected["validation_report"] == n["validation_report"]
