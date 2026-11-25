"""Structural transfer tests. All populations, species and contacts here are synthetic."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis
from scripts.kinetic_data.stoichiometric_sources import build_matrices, conservation_residuals, project_progress
from scripts.multiphase_contracts import validate_bundle
from scripts.reaction_network.builder import build_network

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/multiphase"


def read(name):
    return json.loads((FIX / name).read_bytes())


@pytest.fixture
def data():
    return read("synthetic_interphase_transfer.json")


def entry(data):
    return build_network(data)["reactions"][0]


def test_identity_and_structural_qualification(data):
    original = deepcopy(data)
    snapshot = build_network(data)
    r = snapshot["reactions"][0]
    t = r["interphase_transfer"]
    assert data == original and t["stoichiometrically_valid"] is True
    assert [s["composition"] for s in snapshot["species"]] == [{"Ar": 1}, {"Ar": 1}]
    assert len(set(snapshot["species_fingerprints"].values())) == 2
    assert [(t[k]["phase_id"], t[k]["species_id"]) for k in ("source", "destination")] == [
        ("phase-a", "x-a"), ("phase-b", "x-b")]
    assert t["interface_id"] == "contact" and t["element_balanced"] and t["charge_balanced"]
    assert t["source"]["inventories"]["pool-a"] == dict(occupied_change=-1, vacancy_change=1, capacity_change=0)
    assert t["destination"]["inventories"]["pool-b"] == dict(occupied_change=1, vacancy_change=-1, capacity_change=0)
    assert t["molecule_change"] == 0
    ref = t["operating_conditions_ref"]
    assert sha256_file(ROOT / ref["path"]) == ref["sha256"] and ref == r["definition"]["provenance"][0]["artifact"]
    assert r["level"] == "STRUCTURALLY_VALID" and r["network_review"] is None
    assert set(r["gaps"]) == {"Missing compatible free energies", "Missing kinetic parameters or rate law",
                              "Unresolved transition-state treatment"}
    assert all(v is None for v in r["energies"]["gibbs_ev"].values())
    assert r["parameter_set_ids"] == [] and r["definition"]["ts_id"] is None
    assert snapshot["validation_report"]["mkm_status"] == "blocked"
    assert snapshot["validation_report"]["execution_authorized"] is False


@pytest.mark.parametrize("reverse", [True, False, None])
def test_reverse_requires_declaration(data, reverse):
    data["reactions"][0]["reversible"] = reverse
    direction = entry(data)["direction"]
    if reverse is not True:
        assert direction["reverse"] is None
        assert direction["status"] == ("unknown" if reverse is None else "irreversible")
    else:
        assert direction["reverse"] == dict(reactants={"x-b": 1}, products={"x-a": 1},
                                            sites_consumed={"pool-a": 1}, sites_released={"pool-b": 1})


@pytest.mark.parametrize(("which", "vac", "endpoint", "site"), [
    (0, "sites_released", "source", "pool-a"), (1, "sites_consumed", "destination", "pool-b")])
@pytest.mark.parametrize("missing", ["footprint", "vacancy", "both"])
def test_missing_bindings_are_local(data, which, vac, endpoint, site, missing):
    if missing in ("footprint", "both"):
        data["species"][which]["site_occupancy"] = None
    if missing in ("vacancy", "both"):
        data["reactions"][0][vac] = None
    r = entry(data)
    t = r["interphase_transfer"]
    assert r["level"] == "DRAFT" and t["stoichiometrically_valid"] is None
    assert t["charge_balanced"] and t["element_balanced"] and t["molecule_change"] == 0
    assert t["destination" if which == 0 else "source"]["inventories"]["pool-b" if which == 0 else "pool-a"]["capacity_change"] == 0
    if missing == "both":
        assert t[endpoint]["site_occupancy"] is t[endpoint]["vacancies"] is None
        assert t[endpoint]["inventories"] == {}
    else:
        changes = t[endpoint]["inventories"][site]
        assert changes["capacity_change"] is None
        assert (changes["occupied_change"] is None) == (missing == "footprint")
        assert (changes["vacancy_change"] is None) == (missing == "vacancy")
        assert r["net_stoichiometry"]["site:" + site] == changes["vacancy_change"]


def test_malformed_evidence_binding_is_rejected_and_absent_evidence_blocks_execution(data):
    r = data["reactions"][0]
    del r["provenance"][0]["artifact"]["sha256"]
    with pytest.raises(ValueError, match="provenance"):
        entry(data)
    r["provenance"] = []
    assert entry(data)["mkm_status"] == "blocked"


def test_unknown_interface_and_conditions_stay_local(data):
    data["interfaces"].append(dict(data["interfaces"][0], interface_id="another-contact"))
    data["reactions"][0].update(interface_id=None, operating_conditions_ref=None)
    r = entry(data)
    t = r["interphase_transfer"]
    assert t["interface_id"] is t["operating_conditions_ref"] is None
    assert r["level"] == "DRAFT" and t["stoichiometrically_valid"] is True
    assert "Transfer interface unconfirmed" in r["gaps"]
    data["reactions"][0]["interface_id"] = "absent"
    with pytest.raises(ValueError, match="Interface"):
        entry(data)


def test_charge_unknown_preserves_inventory_proof(data):
    data["species"][0]["charge"] = None
    t = entry(data)["interphase_transfer"]
    assert t["charge_balanced"] is t["stoichiometrically_valid"] is None
    assert t["destination"]["inventories"]["pool-b"]["capacity_change"] == 0


@pytest.mark.parametrize(("field", "bad", "reason"), [("composition", {"N": 1}, "element conservation"),
                                                      ("charge", 1, "charge conservation")])
def test_element_or_charge_conflict(data, field, bad, reason):
    data["species"][1][field] = bad
    with pytest.raises(ValueError, match=reason):
        entry(data)


def test_atom_and_charge_conservation_do_not_prove_molecular_count(data):
    data["species"][0]["composition"] = {"Ar": 2}
    data["reactions"][0].update(products={"x-b": 2}, sites_consumed={"pool-b": 2},
                                required_sites={"pool-a": 1, "pool-b": 2})
    with pytest.raises(ValueError, match="molecular count"):
        entry(data)


def test_extra_vacancies_on_both_sides_preserve_net_but_fail_gross(data):
    data["reactions"][0].update(sites_consumed={"pool-b": 1, "pool-a": 1},
                                sites_released={"pool-a": 2}, required_sites={"pool-a": 2, "pool-b": 1})
    with pytest.raises(ValueError, match="sites_released: transfer inventory mismatch for pool-a"):
        entry(data)


def test_partial_mapping_cannot_hide_other_endpoint_contradiction(data):
    data["species"][1]["site_occupancy"] = None
    data["reactions"][0]["sites_released"] = {"pool-a": 2}
    with pytest.raises(ValueError, match="sites_released: transfer inventory mismatch"):
        entry(data)


def test_vacancies_on_wrong_domain_fail_with_unknown_footprint(data):
    data["species"][1]["site_occupancy"] = None
    data["reactions"][0].update(sites_consumed={"pool-a": 1}, required_sites={"pool-a": 2, "pool-b": 1})
    with pytest.raises(ValueError, match="sites_consumed outside transfer endpoint"):
        entry(data)


def test_missing_destination_cannot_hide_insufficient_source_footprint(data):
    data["species"][1]["site_occupancy"] = None
    data["reactions"][0].update(sites_consumed=None, required_sites={"pool-b": 1})
    with pytest.raises(ValueError, match="required site footprint"):
        entry(data)


def test_private_contact_binding_cannot_be_swapped(data):
    data["interfaces"].append(dict(data["interfaces"][0], interface_id="other"))
    data["sites"][0]["interface_id"] = "contact"
    data["species"][0]["interface_id"] = "contact"
    data["reactions"][0]["interface_id"] = "other"
    with pytest.raises(ValueError, match="different interface"):
        entry(data)


def test_same_phase_fails_even_with_different_surfaces(data):
    data["surfaces"][1]["phase_id"] = "phase-a"
    data["reactions"][0].update(interface_id=None, phase_ids=["phase-a"])
    with pytest.raises(ValueError, match="distinct catalyst phases"):
        entry(data)


def test_partial_phase_ownership_cannot_hide_known_same_phase_overlap(data):
    data["surfaces"].append({"surface_id": "unassigned", "phase_id": None})
    source = data["species"][0]
    source.update(surface_ids=["face-a", "unassigned"], site_occupancy=None, interface_id="contact")
    data["surfaces"][1]["phase_id"] = "phase-a"
    # Multiple facets of one declared contact may include an unassigned facet.
    data["interfaces"][0]["surface_ids"].append("unassigned")
    data["reactions"][0]["surface_ids"].append("unassigned")
    with pytest.raises(ValueError, match="distinct catalyst phases"):
        entry(data)


def test_other_reaction_types_and_coexistence_do_not_create_transfers(data):
    with pytest.raises(ValueError, match="at least one reaction"):
        build_network(dict(data, reactions=[]))
    r = data["reactions"][0]
    r["reaction_type"] = "interfacial"
    with pytest.raises(ValueError, match="requires a declared"):
        entry(data)
    del r["operating_conditions_ref"]
    assert "interphase_transfer" not in entry(data)


def test_multidentate_and_scaled_coefficients(data):
    data["species"][0]["site_occupancy"] = {"pool-a": 2}
    data["reactions"][0].update(reactants={"x-a": 2}, products={"x-b": 2}, sites_consumed={"pool-b": 2},
                                sites_released={"pool-a": 4}, required_sites={"pool-a": 4, "pool-b": 2})
    t = entry(data)["interphase_transfer"]
    assert t["source"]["inventories"]["pool-a"]["occupied_change"] == -4
    assert t["destination"]["inventories"]["pool-b"]["occupied_change"] == 2
    assert t["source"]["molecules"] == t["destination"]["molecules"] == 2


def test_independent_site_capacity_and_source_reconstruction(data):
    net = build_network(data)
    r = data["reactions"][0]
    ctx = read("synthetic_transfer_context.json")
    m = build_matrices([r])
    assert conservation_residuals(m, data["species"])["move"] == {
        "elements": {"Ar": 0}, "charge": 0, "inventories": {"pool-a": 0, "pool-b": 0}}
    # Unit reaction extent, used only for the stoichiometric column.
    species, vacancies = project_progress(m, {"move": 1})
    assert species == {"x-a": -1, "x-b": 1} and vacancies == {"pool-a": 1, "pool-b": -1}
    by_state = []
    for state in ("populations_before", "populations_after"):
        pops = ctx[state]
        ref = ctx["inventory_reference"]
        obs = dict(inventory_reference=ref, sites=ctx["sites"],
                   species=[dict(species_id=s, molecular_reference=ref, coverage=n) for s, n in pops.items()])
        inventory = coverage_analysis(net, obs, {})["sites"]
        by_state.append({s: tuple(v["site_counts"][k] for k in ("occupied", "vacant", "capacity"))
                         for s, v in inventory.items()})
    assert by_state == [{"pool-a": (2, 1, 3), "pool-b": (1, 4, 5)}, {"pool-a": (1, 2, 3), "pool-b": (2, 3, 5)}]
    for site, change in vacancies.items():
        assert by_state[1][site][1] - by_state[0][site][1] == change
    for s, change in species.items():
        assert ctx["populations_after"][s] - ctx["populations_before"][s] == change


def relabel(value, labels):
    if isinstance(value, dict):
        return {labels.get(k, k): relabel(v, labels) for k, v in value.items()}
    if isinstance(value, list):
        return [relabel(v, labels) for v in value]
    return labels.get(value, value)


def test_consistent_renaming_and_order(data):
    labels = {key: "renamed-" + key for key in ["phase-a", "phase-b", "pool-a", "pool-b", "face-a", "face-b",
                                                 "x-a", "x-b", "move", "contact"]}
    other = relabel(data, labels)
    for key in ("phases", "surfaces", "species", "sites"):
        other[key].reverse()
    mapped = entry(other)
    original = entry(data)
    for field in ("direction", "interphase_transfer"):
        assert mapped[field] == relabel(original[field], labels)
    assert original["level"] == mapped["level"]


@pytest.fixture
def bundle():
    base = read("valid.json")
    src = base["species"][-1]
    dst = dict(src, species_id="H2-on-other", material_ids=["Cu"], surface_ids=["facet-Cu"],
               structure_id="synthetic-other", site_occupancy={"bridge-Cu": 1})
    base["species"].append(dst)
    base["reactions"][0].update(reaction_type="interphase_transfer", reactants={src["species_id"]: 1},
                                products={dst["species_id"]: 1}, sites_released=src["site_occupancy"],
                                sites_consumed=dst["site_occupancy"], operating_conditions_ref=None,
                                ts_treatment="unresolved", ts_id=None, rate_law_id=None, free_energies=None,
                                electronic_energies=dict.fromkeys(("reaction", "forward", "reverse")))
    return dict(base, parameter_sets=[], runs=[])


@pytest.mark.parametrize("status", ["draft", "blocked"])
def test_exchange_and_partial_paths_agree(bundle, status):
    bundle["reactions"][0].update(eligibility=status, interface_id=None)
    validate_bundle(bundle)
    strict = entry(bundle)
    partial = entry(dict(bundle, format="network-definition/1"))
    assert strict["interphase_transfer"] == partial["interphase_transfer"]
    assert strict["level"] == partial["level"] == "DRAFT"
    bundle["reactions"][0]["interface_id"] = "junction"
    validate_bundle(bundle)
    assert entry(bundle)["level"] == "STRUCTURALLY_VALID"


def test_exchange_rejects_gross_conflict_and_bad_bindings(bundle):
    r = bundle["reactions"][0]
    r.update(sites_consumed={"top-Ni": 1, "bridge-Cu": 1}, sites_released={"top-Ni": 2},
             required_sites={"top-Ni": 2, "bridge-Cu": 1})
    with pytest.raises(ValueError, match="sites_released: transfer inventory mismatch for top-Ni"):
        validate_bundle(bundle)
    r["operating_conditions_ref"] = {"path": "missing-hash.json"}
    with pytest.raises(ValueError, match="sha256"):
        validate_bundle(bundle)
    with pytest.raises(ValueError, match="operating_conditions_ref"):
        entry(dict(bundle, format="network-definition/1"))
