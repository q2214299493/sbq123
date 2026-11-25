"""Synthetic cross-phase bookkeeping through the public network and exchange APIs."""
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis
from scripts.kinetic_data.stoichiometric_sources import build_matrices, conservation_residuals, project_progress
from scripts.multiphase_contracts import validate_bundle
from scripts.reaction_network.builder import LEVELS, build_network
from scripts.reaction_network.cross_phase import record_review_status

FIX = Path(__file__).parent / "fixtures/multiphase"


@pytest.fixture
def pair():
    return load_json_object(FIX / "cross_phase_interface_product.json")


@pytest.fixture
def triple():
    return load_json_object(FIX / "cross_phase_three_phase.json")


def inspect(data):
    return build_network(data)["reactions"][0]


def test_two_phase_product_and_independent_evidence_dimensions(pair):
    before = deepcopy(pair)
    r = inspect(pair)
    assert pair == before and r["level"] == "STRUCTURALLY_VALID"
    assert r["definition"]["reaction_type"] == "cross_phase_elementary"
    assert "interphase_transfer" not in r
    assert pair["species"][-1]["interface_id"] == r["definition"]["interface_id"] == "junction"
    assert r["direction"]["reverse"] == {
        "reactants": {"contact-product": 1}, "products": {"left-H": 2, "right-O": 1},
        "sites_consumed": {"A-pool": 1}, "sites_released": {"B-pool": 1}}
    assert r["cross_phase_qualification"] == {
        "structurally_represented": True, "interface_scope_verified": True, "stoichiometrically_valid": True,
        "electronic_evidence": "missing", "thermal_evidence": "missing", "kinetic_parameterization": "missing",
        "scientific_review": "unaccepted", "mkm_eligibility": "blocked", "kmc_eligibility": "blocked"}
    assert r["definition"]["ts_id"] is None and r["parameter_set_ids"] == []
    assert "Unresolved transition-state treatment" in r["gaps"]


def test_three_phases_product_on_third_surface_and_unknown_reversibility(triple):
    r = inspect(triple)
    assert r["level"] == "STRUCTURALLY_VALID"
    assert r["direction"]["status"] == "unknown" and r["direction"]["reverse"] is None
    assert r["definition"]["interface_id"] == "triple-junction"
    assert triple["species"][-1]["surface_ids"] == ["face-C"]
    assert r["site_balance_by_inventory"]["C-pool"]["products"]["occupied"] == {"C-pool": 2}
    assert "Reversibility unconfirmed" in r["gaps"]


def test_unassigned_contact_preserves_known_site_proof(triple):
    triple["reactions"][0]["interface_id"] = None
    r = inspect(triple)
    assert r["level"] == "DRAFT" and "Reaction interface unconfirmed" in r["gaps"]
    assert r["cross_phase_qualification"]["interface_scope_verified"] is None
    assert all(v["balanced"] for v in r["site_balance_by_inventory"].values())
    assert r["cross_phase_qualification"]["stoichiometrically_valid"] is True


@pytest.mark.parametrize("field", ["phase_ids", "surface_ids", "interface_id"])
def test_scope_must_be_explicit(triple, field):
    del triple["reactions"][0][field]
    with pytest.raises(ValueError, match="Missing explicit cross-phase scope"):
        inspect(triple)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("phase_ids", ["phase-A", "phase-B", "absent"], "Reaction phases differ"),
    ("phase_ids", ["phase-A", "phase-A"], "phase_ids"),
    ("surface_ids", ["face-A", "face-B", "absent"], "Unknown or repeated surface"),
    ("interface_id", "absent", "Interface and surface domains disagree"),
    ("sites_consumed", {"absent": 2}, "outside the surface domain"),
    ("interface_ids", ["ab", "bc"], "one declared contact"),
])
def test_unresolved_reference_or_unsupported_topology(triple, field, value, message):
    triple["reactions"][0][field] = value
    with pytest.raises(ValueError, match=message):
        inspect(triple)


def test_unrelated_surface_in_declared_interface_rejected(triple):
    triple["surfaces"].append({"surface_id": "other-face", "phase_id": "phase-C"})
    triple["interfaces"][0]["surface_ids"][-1] = "other-face"
    with pytest.raises(ValueError, match="Interface and surface domains disagree"):
        inspect(triple)


def test_phase_cooccurrence_cannot_pad_scope(triple):
    # Keep the full declared three-phase contact but move the product to phase B.
    triple["species"][-1].update(surface_ids=["face-B"], material_ids=["host-B"], site_occupancy={"B-pool": 2})
    triple["reactions"][0].update(sites_consumed={"B-pool": 1}, sites_released={"A-pool": 1},
                                   required_sites={"A-pool": 1, "B-pool": 2})
    with pytest.raises(ValueError, match="unrelated or missing participating surface"):
        inspect(triple)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("composition", {"H": 1, "O": 1}, "element conservation"), ("charge", 1, "charge conservation")])
def test_chemistry_conflict_rejected_independently(pair, field, value, message):
    pair["species"][-1][field] = value
    with pytest.raises(ValueError, match=message):
        inspect(pair)


@pytest.mark.parametrize("field", ["composition", "charge"])
def test_missing_chemistry_is_unknown_in_partial_path(pair, field):
    pair["species"][0][field] = None
    r = inspect(pair)
    assert r["level"] == "DRAFT" and r["cross_phase_qualification"]["stoichiometrically_valid"] is None
    assert all(v["balanced"] for v in r["site_balance_by_inventory"].values())
    assert ("Unknown element balance" if field == "composition" else "Unknown charge balance") in r["gaps"]


def test_equal_global_site_totals_cannot_cancel_inventory_mismatch(pair):
    pair["reactions"][0].update(sites_consumed={}, sites_released={})
    with pytest.raises(ValueError, match="site conservation"):
        inspect(pair)


def test_missing_footprint_leaves_other_inventory_verifiable(pair):
    pair["species"][0]["site_occupancy"] = None
    r = inspect(pair)
    rows = r["site_balance_by_inventory"]
    assert r["level"] == "DRAFT"
    assert rows["A-pool"]["reactants"]["occupied"] is rows["A-pool"]["balanced"] is None
    assert rows["B-pool"]["balanced"] is True
    pair["reactions"][0]["sites_consumed"] = {}
    with pytest.raises(ValueError, match="Site conservation failed in domain B-pool"):
        inspect(pair)


def test_null_vacancy_stays_unknown(triple):
    triple["reactions"][0]["sites_released"] = None
    r = inspect(triple)
    assert r["level"] == "DRAFT"
    for site, v in r["site_balance_by_inventory"].items():
        assert v["products"]["vacant"] is v["balanced"] is None
        assert r["net_stoichiometry"]["site:" + site] is None


def bind_test_ts(pair):
    # An invented catalog label exercises the reference join only.
    ts = dict(pair["species"][-1], species_id="complex-test", structure_id="model-ts-test")
    pair["species"].append(ts)
    pair["reactions"][0].update(ts_species_id=ts["species_id"], ts_treatment="located", ts_id=ts["structure_id"])
    return ts


def test_interface_transition_complex_is_location_only(pair):
    ts = bind_test_ts(pair)
    r = inspect(pair)
    assert ts["interface_id"] == r["definition"]["interface_id"]
    assert r.get("ts_review") is None and r["mkm_status"] == "blocked"
    assert ts["species_id"] not in r["direction"]["forward"]["products"]
    assert r["level"] == "STRUCTURALLY_VALID"


@pytest.mark.parametrize(("field", "value", "message"), [
    ("structure_id", "wrong-state", "matching located transition"),
    ("composition", {"H": 1}, "TS species composition"),
    ("charge", 2, "TS species charge"),
    ("interface_id", "other-contact", "different interface")])
def test_misbound_transition_complex_fails(pair, field, value, message):
    pair["interfaces"].append(dict(pair["interfaces"][0], interface_id="other-contact"))
    ts = bind_test_ts(pair)
    ts[field] = value
    with pytest.raises(ValueError, match=message):
        inspect(pair)


def test_missing_reactant_composition_cannot_hide_known_ts_product_contradiction(pair):
    ts = bind_test_ts(pair)
    pair["species"][0]["composition"] = None
    ts["composition"] = {"O": 1}
    with pytest.raises(ValueError, match="TS species composition"):
        inspect(pair)


def test_bound_transition_footprint_must_fit_declared_inventory(pair):
    ts = bind_test_ts(pair)
    ts["site_occupancy"] = {"A-pool": 3, "B-pool": 2}
    with pytest.raises(ValueError, match="TS species footprint"):
        inspect(pair)


def test_unconfirmed_transition_footprint_is_local(pair):
    ts = bind_test_ts(pair)
    ts["site_occupancy"] = None
    r = inspect(pair)
    assert r["level"] == "DRAFT" and "Unknown TS site footprint" in r["gaps"]
    assert r["cross_phase_qualification"]["stoichiometrically_valid"] is True


def test_same_formula_preserves_both_resident_identities_and_explicit_class():
    data = load_json_object(FIX / "synthetic_interphase_transfer.json")
    transfer = inspect(data)
    assert "interphase_transfer" in transfer and "cross_phase_qualification" not in transfer
    data["reactions"][0]["reaction_type"] = "cross_phase_elementary"
    n = build_network(data)
    row = n["reactions"][0]
    assert len(set(n["species_fingerprints"].values())) == 2
    assert "cross_phase_qualification" in row and "interphase_transfer" not in row
    assert transfer["direction"] == row["direction"]


def test_finite_population_and_b1_columns(pair):
    n = build_network(pair)
    ctx = load_json_object(FIX / "cross_phase_counting_cell.json")
    m = build_matrices(pair["reactions"])
    assert conservation_residuals(m, pair["species"])["combine"] == {
        "elements": {"H": 0, "O": 0}, "charge": 0, "inventories": {"A-pool": 0, "B-pool": 0}}
    ds, dv = project_progress(m, {"combine": 1})
    assert ds == {"left-H": -2, "right-O": -1, "contact-product": 1}
    assert dv == {"A-pool": 1, "B-pool": -1}
    stocks = []
    for step in ("before", "after"):
        obs = dict(inventory_reference=ctx["inventory_reference"], sites=ctx["sites"],
                   species=[dict(species_id=s, coverage=v, molecular_reference=ctx["inventory_reference"])
                            for s, v in ctx[step].items()])
        rows = coverage_analysis(n, obs, {})["sites"]
        stocks.append({s: tuple(v["site_counts"][k] for k in ("occupied", "vacant", "capacity")) for s, v in rows.items()})
    assert stocks == [{"A-pool": (2, 1, 3), "B-pool": (1, 3, 4)}, {"A-pool": (1, 2, 3), "B-pool": (2, 2, 4)}]
    # Two reactant/product configurations share pool A through one declared inventory.
    # Claiming one physical member in two inventories invalidates both capacities.
    obs["sites"][1]["physical_site_ids"][0] = obs["sites"][0]["physical_site_ids"][0]
    assert all(v["site_counts"]["capacity"] is None for v in coverage_analysis(n, obs, {})["sites"].values())


def rename(data, labels):
    if isinstance(data, dict):
        return {labels.get(k, k): rename(v, labels) for k, v in data.items()}
    if isinstance(data, list):
        return [rename(v, labels) for v in data]
    return labels.get(data, data)


def test_label_and_order_invariance(pair):
    labels = {key: "z-" + key for key in ["phase-A", "phase-B", "face-A", "face-B", "A-pool", "B-pool",
                                            "junction", "left-H", "right-O", "contact-product"]}
    changed = rename(pair, labels)
    for k in ("phases", "surfaces", "species", "sites"):
        changed[k].reverse()
    a, b = inspect(pair), inspect(changed)
    for field in ("direction", "site_balance_by_inventory", "cross_phase_qualification"):
        assert rename(a[field], labels) == b[field]


def test_strict_exchange_entry_and_class_isolation():
    bundle = load_json_object(FIX / "valid.json")
    r = bundle["reactions"][0]
    r["reaction_type"] = "cross_phase_elementary"
    validate_bundle(bundle)
    out = inspect(bundle)
    assert out["definition"]["reaction_type"] == "cross_phase_elementary"
    assert out["cross_phase_qualification"]["electronic_evidence"] == "supplied"
    assert out["cross_phase_qualification"]["thermal_evidence"] == "supplied"
    assert out["cross_phase_qualification"]["scientific_review"] == "unaccepted"
    assert out["mkm_status"] == "blocked"
    r["ts_species_id"] = "H2-g"
    with pytest.raises(ValueError, match="matching located transition"):
        validate_bundle(bundle)
    r.pop("ts_species_id")
    r["reaction_type"] = "interphase_transfer"
    with pytest.raises(ValueError, match="resident"):
        validate_bundle(bundle)


def test_bound_rejection_and_native_eligibility_are_separate(pair):
    first = inspect(pair)
    review = dict(reaction_id="combine", subject_sha256=first["subject_sha256"], decision="rejected",
                  reviewer="fixture-reviewer", reviewed_at="2026-11-22T08:00:00+00:00", reason="test only")
    result = build_network(pair, decisions=[review])["reactions"][0]
    assert result["cross_phase_qualification"]["scientific_review"] == "rejected"
    assert result["cross_phase_qualification"]["mkm_eligibility"] == "blocked"


def test_kinetically_eligible_network_projection_still_requires_engine_qualification():
    # Only exercise the status projection for an upstream eligibility decision.
    result = dict(level="KINETICALLY_ELIGIBLE", mkm_status="eligible", scientific_review={"status": "accepted"},
                  network_review={"decision": "accepted"}, cross_phase_qualification={})
    record_review_status(result, LEVELS[3:])
    assert result["cross_phase_qualification"] == dict(scientific_review="accepted",
                                                       mkm_eligibility="requires_native_qualification",
                                                       kmc_eligibility="unassessed")


def test_strict_cannot_infer_missing_species_chemistry():
    bundle = load_json_object(FIX / "valid.json")
    bundle["reactions"][0]["reaction_type"] = "cross_phase_elementary"
    bundle["species"][0]["composition"] = None
    with pytest.raises(ValueError, match="composition"):
        validate_bundle(bundle)
