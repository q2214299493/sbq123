"""Independent one-event witnesses and unchanged archived artifacts, all offline."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.rate_output_v2 import main, validate_network_bound_rate_output, validate_rate_output_v2

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "reports/multiphase/stage_b1_4/replay"
NETWORK = ROOT / "reports/multiphase/phase3_0/closed_cycle_network.json"


def canonical(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def seal(payload):
    binding = payload["output_binding"]
    binding.pop("dataset_id", None)
    binding["dataset_id"] = "rates-" + canonical(payload)


def observations(payload):
    # Independent one-event ledger for the deliberately small subset.
    row, = payload["reaction_rates"]
    terms = {}
    for group, left, right, key, value in (
        ("species", "reactants", "products", "species_id", "net_production_rate"),
        ("site_inventories", "sites_consumed", "sites_released", "site_id", "net_vacancy_rate"),
    ):
        before, after = row[left], row[right]
        terms[group] = [{key: k, value: None if row["net"] is None else
                         row["net"] * (after.get(k, 0) - before.get(k, 0))} for k in sorted(before.keys() | after.keys())]
    payload["source_terms"] = terms
    seal(payload)


@pytest.fixture
def subset():
    payload = json.loads((REPLAY / "catkinas-phase3_0.json").read_bytes())
    payload.pop("rate_coefficients")
    payload["reaction_rates"] = [dict(
        reaction_id="ads", parameter_set_id="parameters-ads", reactants={"H2-g": 1},
        products={"H2-top": 1, "H2-bridge": 1}, sites_consumed={"top-Ni": 1, "bridge-Cu": 1},
        sites_released={}, forward=3, reverse=1, net=2)]
    observations(payload)
    return payload


@pytest.mark.parametrize("change", [
    {"reaction_id": "unlisted"}, {"reaction_id": "transfer"}, {"parameter_set_id": "absent"},
    {"parameter_set_id": "parameters-transfer"}, {"reactants": {"H2-g": 2}},
    {"products": {"H2-top": 2}}, {"sites_consumed": {"bridge-Cu": 1}},
    {"sites_released": {"top-Ni": 1}}, {"sites_consumed": {"bridge-Cu": 2, "top-Ni": 1}},
    {"forward": "not_applicable", "reverse": 1, "net": -1},
    {"reactants": {"H2-top": 1, "H2-bridge": 1}, "products": {"H2-g": 1},
     "sites_consumed": {}, "sites_released": {"top-Ni": 1, "bridge-Cu": 1}},
])
def test_shape_valid_but_wrong_network_row(subset, change, tmp_path):
    subset["reaction_rates"][0].update(change)
    observations(subset)
    assert hashlib.sha256(NETWORK.read_bytes()).hexdigest() == subset["provenance"]["network"]["sha256"]
    validate_rate_output_v2(subset, network=json.loads(NETWORK.read_bytes()))
    with pytest.raises(ValueError):
        validate_network_bound_rate_output(subset, NETWORK, reaction_ids=["ads"])
    path = tmp_path / "rate.json"
    path.write_text(json.dumps(subset))
    with pytest.raises(SystemExit) as failure:
        main([str(path), "--qualified-network", str(NETWORK), "--reaction-id", "ads"])
    assert failure.value.code == 1


def test_subset_is_external_and_exact(subset, tmp_path):
    before = deepcopy(subset)
    validate_network_bound_rate_output(subset, NETWORK, reaction_ids=["ads"])
    assert subset == before
    for selection in (None, [], ["ads", "ads"], ["transfer"], ["ads", "missing"]):
        with pytest.raises(ValueError, match="subset"):
            validate_network_bound_rate_output(subset, NETWORK, reaction_ids=selection)
    path = tmp_path / "rate.json"
    path.write_text(json.dumps(subset))
    assert main([str(path), "--qualified-network", str(NETWORK), "--reaction-id", "ads"]) == 0


@pytest.mark.parametrize("case", sorted(REPLAY.glob("*.json")), ids=lambda p: p.stem)
def test_archived_qualification_preserves_identity_and_basis(case):
    record = json.loads(case.read_bytes())
    before = deepcopy(record)
    validate_rate_output_v2(record)
    validate_network_bound_rate_output(record, ROOT / record["provenance"]["network"]["path"])
    assert record == before


def test_missing_or_wrong_binding(subset, tmp_path):
    with pytest.raises(ValueError):
        validate_network_bound_rate_output(subset, None)
    path = tmp_path / "network.json"
    path.write_bytes(NETWORK.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])
    subset["output_binding"]["run_id"] += "-different"
    with pytest.raises(ValueError, match="dataset identity"):
        validate_network_bound_rate_output(subset, NETWORK, reaction_ids=["ads"])
    del subset["output_binding"]
    with pytest.raises(ValueError, match="identity"):
        validate_network_bound_rate_output(subset, NETWORK, reaction_ids=["ads"])


def modified_network(path, network, payload):
    network.pop("network_version")
    version = canonical(network)
    network["network_version"] = version
    path.write_bytes(json.dumps(network).encode())
    payload["network_version"] = payload["native_normalization"]["reference_scope"]["network_version"] = version
    payload["provenance"]["network"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    observations(payload)


@pytest.mark.parametrize("state", ["unknown", "irreversible"])
def test_reverse_evidence_and_directional_parameter(state, subset, tmp_path):
    network = json.loads(NETWORK.read_bytes())
    entry = next(r for r in network["reactions"] if r["definition"]["reaction_id"] == "ads")
    entry["definition"]["reversible"] = None if state == "unknown" else False
    entry["direction"].update(status=state, reverse=None)
    param = next(r for r in network["parameter_sets"] if r["parameter_set_id"] == "parameters-ads")
    param["reverse"] = None
    row = subset["reaction_rates"][0]
    row.update(reverse=None if state == "unknown" else "not_applicable", net=None if state == "unknown" else 3)
    path = tmp_path / "network.json"
    modified_network(path, network, subset)
    validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])
    row.update(reverse=0, net=3)
    observations(subset)
    with pytest.raises(ValueError, match="direction"):
        validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])


@pytest.mark.parametrize("field,bad", [("phase_ids", ["foreign"]), ("reaction_type", "unknown-type"),
                                       ("interface_id", None), ("surface_ids", ["foreign"])])
def test_inconsistent_network_scope(subset, tmp_path, field, bad):
    network = json.loads(NETWORK.read_bytes())
    definition = next(e["definition"] for e in network["reactions"] if e["definition"]["reaction_id"] == "ads")
    definition[field] = bad
    path = tmp_path / "network.json"
    modified_network(path, network, subset)
    with pytest.raises(ValueError):
        validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])


def test_parameter_ownership_and_missing_direction(subset, tmp_path):
    network = json.loads(NETWORK.read_bytes())
    param = next(p for p in network["parameter_sets"] if p["reaction_id"] == "ads")
    path = tmp_path / "network.json"
    param["reaction_id"] = "transfer"
    modified_network(path, network, subset)
    with pytest.raises(ValueError, match="belong"):
        validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])
    param["reaction_id"] = "ads"
    param["forward"] = None
    modified_network(path, network, subset)
    with pytest.raises(ValueError, match="parameter binding"):
        validate_network_bound_rate_output(subset, path, reaction_ids=["ads"])


def test_network_free_v2():
    record = json.loads((ROOT / "tests/fixtures/multiphase/rate_output_v2.json").read_bytes())
    validate_rate_output_v2(record)
    with pytest.raises(ValueError, match="V2.1"):
        validate_network_bound_rate_output(record, NETWORK)
