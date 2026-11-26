"""Synthetic kinetic datasets and the existing dissociative ads benchmark."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.scientific_identity import dataset_reference, read_artifact, require_reaction_identity
from test_native_model import model


def version(dataset):
    dataset["dataset_version"] = sha256_json({k: v for k, v in dataset.items() if k != "dataset_version"})
    return dataset


def test_multistructure_source_requires_matching_record_and_file(tmp_path):
    left, _ = model(gas=True)
    right = deepcopy(left)
    gas = next(s for s in left["species"] if s["phase"] == "gas")
    other = next(s for s in right["species"] if s["species_id"] == gas["species_id"])
    source = tmp_path / "isomers.json"
    source.write_text(json.dumps([{"id": "cis", "configuration": "cis"}, {"id": "trans", "configuration": "trans"}]))
    for species in (gas, other):
        species["structural_provenance"] = dict(path=str(source), sha256=sha256_file(source))
    gas["structure_id"], other["structure_id"] = "cis", "trans"
    rid = left["reactions"][0]["reaction_id"]
    with pytest.raises(ValueError, match="molecular_stoichiometry"):
        require_reaction_identity(version(left), version(right), rid)
    other["structure_id"] = "cis"
    require_reaction_identity(left, version(right), rid)
    other["structural_provenance"]["sha256"] = "a" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        require_reaction_identity(left, version(right), rid)
    del other["structure_id"]
    with pytest.raises(ValueError, match="Invalid id"):
        require_reaction_identity(left, version(right), rid)


def test_identity_uses_species_definitions_and_ignores_native_order():
    left, _ = model(gas=True)
    right = deepcopy(left)
    right["species"].reverse()
    for values in right["catalog"].values():
        values.reverse()
    rid = left["reactions"][0]["reaction_id"]
    identity = require_reaction_identity(left, version(right), rid)
    assert sum(identity["molecular_stoichiometry"]["products"].values()) == 1
    assert identity["per_event_sites"]["sites_consumed"] == {"top-Ni": 1, "bridge-Cu": 1}


def test_reviewed_ads_same_site_demand_different_molecular_products():
    root = Path(__file__).resolve().parents[1]
    mkm, _ = read_artifact(root / "archive/v221_catkinas/nicu-v221-400k-001/dataset.json")
    kmc, _ = model(gas=True)
    r = kmc["reactions"][0]
    assert r["reaction_id"] == "ads"
    a = next(row for row in mkm["reactions"] if row["reaction_id"] == "ads")
    assert a["direction"]["forward"]["sites_consumed"] == r["direction"]["forward"]["sites_consumed"]
    with pytest.raises(ValueError, match="molecular_stoichiometry") as exc:
        require_reaction_identity(mkm, version(kmc), "ads")
    assert "per_event_sites" not in str(exc.value)


@pytest.mark.parametrize("mutation,reason", [
    ("bytes", "digest"), ("direction", "direction"), ("gross", "inventory"),
    ("owner", "inventory_owners"), ("vacancy", "per_event_sites"), ("unknown", "Unknown reaction"),
])
def test_incompatible_or_stale_identity(mutation, reason):
    a, _ = model(gas=True)
    b = json.loads(json.dumps(a))  # Independent forward/reverse mappings as stored on disk.
    r = b["reactions"][0]
    rid = r["reaction_id"]
    if mutation == "direction":
        r["direction"]["reverse"] = None
    elif mutation == "gross":
        r["site_balance"]["top-Ni"] += 1
    elif mutation == "owner":
        b["catalog"]["sites"][0]["local_geometry"] += " altered"
    elif mutation == "vacancy":
        for sense, side in (("forward", "sites_consumed"), ("forward", "sites_released"),
                            ("reverse", "sites_consumed"), ("reverse", "sites_released")):
            counts = r["direction"][sense][side]
            counts["top-Ni"] = counts.get("top-Ni", 0) + 1
        r["site_balance"]["top-Ni"] += 1
        local = r["model"]["local_event"]
        local["site_ids"].append("top-Ni")
        for key in ("initial", "final"):
            local[key].append(None)
        local["neighbors_zero_based"].append([1, 2])
    elif mutation == "unknown":
        rid = "missing"
    version(b)
    if mutation == "bytes":
        b["project_id"] += "x"
    with pytest.raises(ValueError, match=reason):
        require_reaction_identity(a, b, rid)


def test_parameter_content_retains_reference_uncertainty_and_units():
    a, _ = model(gas=True)
    b = deepcopy(a)
    r = b["reactions"][0]
    r["parameter_set"]["energy_reference_id"] += "-different"
    r["parameter_set"]["uncertainty"] = {"kind": "test-only"}
    r["rates"]["forward"]["sigma_ln_k"] = 0.25
    version(b)
    rid = r["reaction_id"]
    assert require_reaction_identity(a, b, rid)
    old, new = (dataset_reference(d, "0" * 64)["parameters"][rid] for d in (a, b))
    assert new["parameter_set_id"] == old["parameter_set_id"]
    assert new["reaction_row_sha256"] != old["reaction_row_sha256"]
    assert new["uncertainty"] == r["parameter_set"]["uncertainty"]
    assert new["energy_reference_id"] == r["parameter_set"]["energy_reference_id"]

def test_missing_local_pattern_or_changed_spectator():
    left, _ = model(gas=True)
    right = deepcopy(left)
    row = right["reactions"][0]
    rid = row["reaction_id"]
    local = row["model"].pop("local_event")
    with pytest.raises(ValueError, match="local site pattern"):
        require_reaction_identity(left, version(right), rid)
    row["model"]["local_event"] = local
    local["environment"] = dict(site_ids=["top-Ni"], state=[None], neighbors_zero_based=[[1, 2]])
    with pytest.raises(ValueError, match="local_geometry"):
        require_reaction_identity(left, version(right), rid)


@pytest.mark.parametrize("change,reason", [
    ("single_leg", "footprint"), ("out_of_range", "site index"), ("inventory", "inventory"),
    ("duplicate", "adjacency"), ("self_loop", "adjacency"), ("disconnected", "Disconnected"),
    ("mixed_entity", "entity"), ("missing_slot", "Incomplete"), ("core_duplicate", "adjacency"),
    ("core_disconnected_dimer", "Disconnected"), ("floating_spectator", "Disconnected"),
])
def test_invalid_geometry_even_when_both_records_agree(change, reason):
    data, _ = model(gas=True)
    event = data["reactions"][0]["model"]["local_event"]
    env = dict(site_ids=["top-Ni", "bridge-Cu"], state=[["H2-bridge", 1], ["H2-bridge", 1]],
               neighbors_zero_based=[[0, 2], [2, 3]])
    event["environment"] = env
    if change == "single_leg":
        env["state"][1] = None
    elif change == "out_of_range":
        env["neighbors_zero_based"][1][1] = 999
    elif change == "inventory":
        env["site_ids"][1] = "top-Ni"
    elif change == "duplicate":
        env["neighbors_zero_based"].append([3, 2])
    elif change == "self_loop":
        env["neighbors_zero_based"].append([2, 2])
    elif change == "disconnected":
        env["neighbors_zero_based"][1] = [1, 3]
    elif change == "mixed_entity":
        env["state"][1][0] = "H2-g"
    elif change == "missing_slot":
        env["state"].pop()
    elif change == "core_duplicate":
        event["neighbors_zero_based"].append([1, 0])
    elif change == "core_disconnected_dimer":
        # A vacancy bridges the two legs: the event is connected but the molecule is not.
        event["site_ids"].append("top-Ni")
        for state in ("initial", "final"):
            event[state].append(None)
        event["neighbors_zero_based"] = [[0, 2], [2, 1]]
        del event["environment"]
    elif change == "floating_spectator":
        env["neighbors_zero_based"] = [[2, 3]]
    version(data)
    with pytest.raises(ValueError, match=reason):
        require_reaction_identity(data, data, "ads")


@pytest.mark.parametrize("spectator", [False, True])
def test_connected_bidentate_identity_with_optional_spectator(spectator):
    data, _ = model(gas=True)
    if spectator:
        data["reactions"][0]["model"]["local_event"]["environment"] = dict(
            site_ids=["top-Ni", "bridge-Cu", "top-Ni"],
            state=[["H2-bridge", 1], ["H2-bridge", 1], None],
            neighbors_zero_based=[[1, 2], [2, 3], [3, 4]],
        )
    version(data)
    assert require_reaction_identity(data, deepcopy(data), "ads")["reaction_id"] == "ads"


def test_structure_registration_hashes_and_selects_one_read(tmp_path, monkeypatch):
    from scripts.reaction_network.catalog import catalog, register_species
    data, _ = model(gas=True)
    src = tmp_path / "structures.json"
    records = {s["structure_id"]: {"geometry": s["structure_id"]} for s in data["species"]}
    src.write_text(json.dumps(records))
    ref = dict(path=str(src), sha256=sha256_file(src))
    for s in data["species"]:
        s["structural_provenance"] = ref
    index = catalog(dict(data["catalog"], species=data["species"], reactions=data["reactions"]))
    read_bytes = Path.read_bytes
    reads = []
    def replace_after_read(path):
        raw = read_bytes(path)
        if path == src:
            reads.append(path)
            src.write_bytes(b"[]")
        return raw
    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    assert register_species(index, require_structure=True).keys() == index["species"].keys()
    assert reads == [src]
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        register_species(index, require_structure=True)
