"""Scoped researcher site decisions; synthetic interfaces and the archived Fe(110) draft."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_json
from scripts.reaction_network.__main__ import publish, read_source
from scripts.reaction_network.builder import build_network, from_registry_mapping

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/multiphase"


def documents():
    data = json.loads((ROOT / "tests/fixtures/multiphase/valid.json").read_bytes())
    data["format"] = "network-definition/1"
    data["parameter_sets"] = []
    rx = data["reactions"][0]
    rx.update(reactants={"H2-g": 2}, products={"H2-bridge": 2}, sites_consumed=None,
              sites_released=None, reversible=None, required_sites=None, free_energies=None)
    data["species"][1]["site_occupancy"] = None
    proposal = {"format": "site-mapping-proposal/1", "parent_network_version": build_network(data)["network_version"],
                "reaction_id": "ads"}
    mapping = {"site_definitions": [], "surface_ids": rx["surface_ids"], "interface_id": "junction",
               "occupancies": {"H2-g": {}, "H2-bridge": {"top-Ni": 1, "bridge-Cu": 2}},
               "sites_consumed": {"top-Ni": 2, "bridge-Cu": 5}, "sites_released": {"bridge-Cu": 1},
               "reaction_type": "interfacial", "reversible": True}
    decision = {"scope": "site_mapping", "decision": "confirmed", "reviewer": "fixture researcher",
                "reason": "synthetic decision", "source_reference": "external site inventory, fixture",
                "reviewed_at": "2026-11-19T12:00:00Z", "proposal_sha256": sha256_json(proposal), "mapping": mapping}
    return data, proposal, decision


def reviewed(data, p, d):
    return build_network(data, site_proposal=p, site_confirmation=d)


def test_coefficients_ensembles_types_domains_and_reverse(tmp_path):
    data, p, d = documents()
    original = build_network(data)
    old = publish(original, tmp_path)
    original_bytes = old.read_bytes()
    network = reviewed(data, p, d)
    rx = network["reactions"][0]
    copper = rx["site_balance_by_domain"]["facet-Cu"]
    assert copper["reactants"] == {"occupied": {}, "vacant": {"bridge-Cu": 5}, "total": {"bridge-Cu": 5}}
    assert copper["products"] == {"occupied": {"bridge-Cu": 4}, "vacant": {"bridge-Cu": 1}, "total": {"bridge-Cu": 5}}
    assert rx["site_balance_by_domain"]["facet-Ni"]["products"]["total"] == {"top-Ni": 2}
    assert rx["direction"]["reverse"] == {"reactants": {"H2-bridge": 2}, "products": {"H2-g": 2},
                                          "sites_consumed": {"bridge-Cu": 1}, "sites_released": d["mapping"]["sites_consumed"]}
    assert rx["level"] == "STRUCTURALLY_VALID" and rx["mkm_status"] == "blocked"
    assert old != publish(network, tmp_path) and old.read_bytes() == original_bytes
    assert build_network(data) == original


@pytest.mark.parametrize("value,balanced", [(None, None), ({}, True), ({"bridge-Cu": 0}, True)])
def test_unknown_vs_confirmed_zero(value, balanced):
    data, p, d = documents()
    d["mapping"].update(occupancies={"H2-g": {}, "H2-bridge": value}, sites_consumed={}, sites_released={}, reversible=None)
    rx = reviewed(data, p, d)["reactions"][0]
    assert rx["site_balance_by_domain"]["facet-Cu"]["balanced"] is balanced
    assert rx["site_review"]["confirmation"]["mapping"]["occupancies"]["H2-bridge"] == value
    assert rx["direction"]["reverse"] is None


@pytest.mark.parametrize("issue,match", [
    ("unbalanced", "conservation"), ("wrong_domain", "domain"), ("ambiguous_id", "Conflicting site identity"),
    ("stale", "stale"), ("changed_parent", "parent"), ("fraction", "multiplicity"),
    ("missing_species", "participating"), ("wrong_interface", "Interface"), ("blank_source", "source_reference"),
    ("pending", "confirmation"), ("conflicting_occupancy", "Conflicting confirmed"), ("unknown_site", "domain"),
])
def test_rejects_invalid_decisions(issue, match):
    data, p, d = documents()
    m = d["mapping"]
    if issue == "unbalanced":
        m["sites_consumed"] = {"top-Ni": 6, "bridge-Cu": 1}
    elif issue == "wrong_domain":
        m["site_definitions"] = [{"site_id": "x", "surface_id": "elsewhere", "site_type": "bridge", "local_geometry": "a-b"}]
    elif issue == "ambiguous_id":
        m["site_definitions"] = [dict(data["sites"][0], site_type="bridge")]
    elif issue == "stale":
        p["candidate_centers"] = ["changed"]
    elif issue == "changed_parent":
        data["species"][0]["configuration_id"] = "new"
    elif issue == "fraction":
        m["occupancies"]["H2-bridge"]["top-Ni"] = 0.5
    elif issue == "missing_species":
        del m["occupancies"]["H2-g"]
    elif issue == "wrong_interface":
        m["interface_id"] = None
    elif issue == "blank_source":
        d["source_reference"] = " "
    elif issue == "pending":
        d["decision"] = None
    elif issue == "conflicting_occupancy":
        data["species"][1]["site_occupancy"] = {"top-Ni": 1, "bridge-Cu": 1}
        p["parent_network_version"] = build_network(data)["network_version"]
        d["proposal_sha256"] = sha256_json(p)
    else:
        m["sites_released"] = {"undocumented": 0}
    with pytest.raises(ValueError, match=match):
        reviewed(data, p, d)


def test_external_researcher_can_define_different_ensemble():
    data, p, d = documents()
    m = d["mapping"]
    m["site_definitions"] = [{"site_id": "ensemble", "site_type": "pair", "surface_id": "facet-Cu",
                              "local_geometry": "Two adjacent Cu atoms in the external inventory."}]
    m["occupancies"]["H2-bridge"] = {"ensemble": 1, "top-Ni": 1}
    m.update(sites_consumed={"top-Ni": 2, "ensemble": 2}, sites_released={}, reversible=False)
    catalog = {"format": "surface-site-types/1", "project_id": data["projects"][0]["project_id"],
               "surface_site_types": {"facet-Cu": ["bridge", "pair"]}}
    with pytest.raises(ValueError, match="configured surface"):
        reviewed(data, p, d)
    d["site_catalog_sha256"] = sha256_json(catalog)
    rx = build_network(data, site_proposal=p, site_confirmation=d, site_catalog=catalog)["reactions"][0]
    assert rx["site_balance_by_domain"]["facet-Cu"]["balanced"]
    assert rx["direction"]["status"] == "irreversible"
    with pytest.raises(ValueError, match="bind the supplied"):
        build_network(data, site_proposal=p, site_confirmation=d,
                      site_catalog=dict(catalog, surface_site_types={"facet-Cu": ["bridge", "new-pair"]}))
    with pytest.raises(ValueError, match="different project"):
        build_network(data, site_proposal=p, site_confirmation=d, site_catalog=dict(catalog, project_id="elsewhere"))


def test_other_catalyst_from_project_configuration_through_cli():
    fixture = ROOT / "tests/fixtures/multiphase/synthetic_oxide_site_network.json"
    run = subprocess.run([sys.executable, "-m", "scripts.reaction_network", str(fixture)], capture_output=True, check=True)
    n = json.loads(run.stdout)
    assert n["catalog"]["surfaces"][0]["lattice_vectors_angstrom"][1] == [1.7, 5.2, 0]
    assert n["reactions"][0]["site_balance"] == {"acid-A": 1, "oxygen-B": 1}
    assert n["reactions"][0]["level"] == "STRUCTURALLY_VALID"
    assert n["reactions"][0]["direction"]["status"] == "unknown"
    modified = json.loads(fixture.read_bytes())
    modified["sites"][0]["site_type"] = "long_bridge"
    with pytest.raises(ValueError, match="configured surface"):
        build_network(modified)


def test_one_unmapped_domain_does_not_hide_other_domain_balance():
    data, _, _ = documents()
    data["species"][2]["site_occupancy"] = None  # Ni-only adsorbate
    data["reactions"][0].update(reactants={"H2-top": 2}, products={"H2-bridge": 2})
    p = {"format": "site-mapping-proposal/1", "parent_network_version": build_network(data)["network_version"],
         "reaction_id": "ads"}
    d = documents()[2]
    d["proposal_sha256"] = sha256_json(p)
    d["mapping"].update(occupancies={"H2-top": None, "H2-bridge": {"top-Ni": 1, "bridge-Cu": 1}},
                        sites_consumed={"bridge-Cu": 2}, sites_released={})
    rx = reviewed(data, p, d)["reactions"][0]
    assert rx["site_balance_by_domain"]["facet-Ni"]["balanced"] is None
    assert rx["site_balance_by_domain"]["facet-Cu"]["balanced"] is True
    assert rx["level"] == "DRAFT"
    d["mapping"]["sites_consumed"] = {"bridge-Cu": 1}
    with pytest.raises(ValueError, match="domain facet-Cu"):
        reviewed(data, p, d)


def test_fe110_archived_pending_report_and_sources():
    sources = []
    data = from_registry_mapping(read_source(REPORTS / "ch_co_registry_mapping_20261119.json", "definition", sources), "sbq123")
    intake = read_source(REPORTS / "ch_co_intake_20261119.json", "intake", sources)
    thermal = read_source(REPORTS / "phase2_2_chco_validation.json", "thermochemistry", sources)
    p = json.loads((REPORTS / "phase2_3_1_site_proposal.json").read_bytes())
    report = json.loads((REPORTS / "phase2_3_1_site_balance.json").read_bytes())
    n = build_network(data, intakes=[intake], thermochemistry=[thermal["calculation"]], sources=sources, site_proposal=p)
    assert n == json.loads((REPORTS / "networks" / f"network-{report['network_version']}.json").read_bytes())
    assert p["parent_network_version"] != n["network_version"]
    assert [(x["fragment_zero_based"], x["proposed_occupancy"]) for x in p["candidates"]] == [
        ([45, 48], None), ([46, 47], None), ([45, 46, 47, 48], None)]
    assert p["projections"]["FS"]["47"]["off_symmetry"]
    rx = n["reactions"][0]
    assert rx["level"] == "DRAFT" and rx["mkm_status"] == "blocked"
    assert report["site_balance_by_domain"] == rx["site_balance_by_domain"]
    assert report["site_balance_by_domain"]["fe110"]["balanced"] is None
    template = json.loads((REPORTS / "phase2_3_1_confirmation_template.json").read_bytes())
    assert template["proposal_sha256"] == sha256_json(p)
    assert template["site_catalog_sha256"] == sha256_json(json.loads((REPORTS / "phase2_3_1_fe110_site_types.json").read_bytes()))
    assert template["mapping"] == p["proposed_mapping"] and template["decision"] is None
    clone = deepcopy(p)
    clone["proposed_mapping"]["reversible"] = True
    assert sha256_json(clone) != template["proposal_sha256"]


def test_synthetic_confirmation_via_fe_cli_cannot_fill_charge_or_phase(tmp_path):
    def path(name):
        return str(REPORTS / name)

    d = json.loads((REPORTS / "phase2_3_1_confirmation_template.json").read_bytes())
    d.update(decision="confirmed", reviewer="test fixture only", reason="Synthetic coverage of CLI",
             source_reference="synthetic counting exercise", reviewed_at="2026-11-19T06:00:00Z")
    m = d["mapping"]
    # An intentionally specified ledger only for this temporary test file.
    ch, co, chco = m["occupancies"]
    bridge1, bridge2, hollow1, hollow2, _ = [x["site_id"] for x in m["site_definitions"]]
    m.update(occupancies={ch: {bridge1: 1}, co: {bridge2: 1}, chco: {hollow1: 1, hollow2: 1}},
             sites_consumed={hollow1: 1, hollow2: 1}, sites_released={bridge1: 1, bridge2: 1})
    f = tmp_path / "synthetic-confirmation.json"
    f.write_text(json.dumps(d), encoding="utf8")
    run = subprocess.run([sys.executable, "-m", "scripts.reaction_network", path("ch_co_registry_mapping_20261119.json"),
                          "--project-id", "sbq123", "--intake", path("ch_co_intake_20261119.json"),
                          "--thermochemistry", path("phase2_2_chco_validation.json"),
                          "--site-proposal", path("phase2_3_1_site_proposal.json"),
                          "--site-catalog", path("phase2_3_1_fe110_site_types.json"),
                          "--site-confirmation", str(f)], capture_output=True, check=True)
    rx = json.loads(run.stdout)["reactions"][0]
    assert rx["site_balance_by_domain"]["fe110"]["balanced"] is True
    assert {"Unknown charge balance", "Catalyst phase unconfirmed"} <= set(rx["gaps"])
    assert rx["level"] == "DRAFT" and rx["mkm_status"] == "blocked" and rx["direction"]["reverse"] is None
