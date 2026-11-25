"""Structural identity only. All exchanged structures and source bindings here are synthetic."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.artifact_io import sha256_file
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis
from scripts.baseline_mkm.molecular_coverage import vacancy_requirements
from scripts.multiphase_contracts import interface_phase_ids, validate_bundle
from scripts.reaction_network.builder import build_network
from scripts.reaction_network.catalog import catalog, ownership_report, register_species, resolve_site
from scripts.reaction_network.site_review import register_sites

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/multiphase"
GENERIC = FIX / "synthetic_identity_domains.json"


def read(path):
    return json.loads(path.read_bytes())


def test_generic_catalog_distinguishes_locations_and_independent_interfaces():
    data = read(GENERIC)
    index = catalog(data)
    fingerprints = register_species(index)
    assert len(set(fingerprints.values())) == len(data["species"]) == 5
    assert index["species"]["probe-g"]["surface_ids"] == []
    assert index["species"]["probe-a"]["site_occupancy"] == {"rim-a": 1, "rough-pool": 1}
    assert index["species"]["probe-b"]["interface_id"] == "contact-b"
    assert fingerprints["probe-on-outer"] != fingerprints["probe-on-rough"]
    report = ownership_report(data)
    assert report["phases"]["ordered"]["material_id"] == report["phases"]["disordered"]["material_id"] == "film"
    assert report["surfaces"]["outer"]["phase_id"] == report["surfaces"]["inner"]["phase_id"] == "ordered"
    for key in ["contact-a", "contact-b"]:
        assert report["interfaces"][key]["phase_ids"] == ["disordered", "ordered"]
        assert report["interfaces"][key]["surface_ids"] == ["outer", "rough"]
    phase_only = report["interfaces"]["unlocated"]
    assert phase_only["phase_ids"] == ["disordered", "ordered", "support-phase"]
    assert phase_only["surface_ids"] is None
    assert report["sites"]["rim-a"]["interface_id"] == "contact-a"
    assert report["sites"]["rim-b"]["interface_id"] == "contact-b"
    assert report["sites"]["shared"]["interface_id"] is None
    assert data["reactions"] == []


def test_adsorbate_on_one_side_of_a_contact_has_explicit_location():
    data = read(FIX / "valid.json")
    contact = data["interfaces"][0]["interface_id"]
    private = dict(data["sites"][0], site_id="rim", interface_id=contact)
    data["sites"].append(private)
    one_side = dict(data["species"][2], species_id="edge-state", interface_id=contact, site_occupancy={"rim": 1})
    data["species"].append(one_side)
    validate_bundle(data)
    snapshot = build_network(data)
    assert snapshot["species_fingerprints"]["edge-state"] != snapshot["species_fingerprints"]["H2-top"]
    data["format"] = "network-definition/1"
    assert build_network(data)["species"][-1]["surface_ids"] == [private["surface_id"]]


def test_no_interface_from_phase_coexistence():
    data = read(GENERIC)
    data.update(interfaces=[], sites=data["sites"][:2], species=data["species"][:3])
    assert not ownership_report(data)["interfaces"]
    assert len(register_species(catalog(data))) == 3


def test_full_bundle_alternatives_and_hashed_evidence(tmp_path):
    data = read(FIX / "valid.json")
    phase, surface, interface = data["phases"][0], data["surfaces"][0], data["interfaces"][0]
    phase.update(phase_category="amorphous", description="Synthetic glass", charge=0)
    del phase["composition"]
    source = tmp_path / "patch.xyz"
    source.write_bytes(b"1\nSynthetic identity fixture\nAr 0 0 0\n")
    surface.update(
        surface_descriptor="Disordered boundary",
        lattice_vectors_angstrom=[[3, 0, 0], [0, 4, 0]],
        coordinate_convention="Cartesian angstrom",
        structure_id="patch",
        structural_provenance={"path": source.name, "sha256": sha256_file(source)},
    )
    del surface["miller_indices"]
    interface["phase_ids"] = [p["phase_id"] for p in data["phases"]]
    unseen = dict(interface, interface_id="other")
    del unseen["surface_ids"]
    data["interfaces"].append(unseen)
    validate_bundle(data)
    n = build_network(data)
    assert n["catalog"]["surfaces"][0]["structural_provenance"] == surface["structural_provenance"]
    report = ownership_report(data)
    assert report["surfaces"][surface["surface_id"]]["structural_provenance"]["sha256"] == sha256_file(source)
    assert "composition" not in phase and report["phases"][phase["phase_id"]]["charge"] == 0
    assert report["interfaces"]["other"]["surface_ids"] is None


@pytest.mark.parametrize("mode", ["bundle", "native"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("phase_category", ""),
        ("charge", True),
        ("surface_descriptor", " "),
        ("lattice_vectors_angstrom", [[1, 2]]),
        ("coordinate_convention", 3),
        ("structural_provenance", {"path": "s", "sha256": "wrong"}),
    ],
)
def test_malformed_supplied_metadata_rejected(mode, field, value):
    data = read(FIX / "valid.json")
    if mode == "native":
        data["format"] = "network-definition/1"
    data["phases" if field in ("phase_category", "charge") else "surfaces"][0][field] = value
    with pytest.raises(ValueError):
        (validate_bundle if mode == "bundle" else build_network)(data)


@pytest.mark.parametrize("mode", ["bundle", "native"])
@pytest.mark.parametrize(
    "fault",
    ["foreign_phase", "foreign_facet", "missing_interface", "inventory_owner", "repeated_phase", "repeated_site"],
)
def test_invalid_ownership_never_enters_network(mode, fault):
    data = read(FIX / "valid.json")
    phase_ids = [p["phase_id"] for p in data["phases"]]
    a = data["interfaces"][0]
    a["phase_ids"] = phase_ids
    if fault == "foreign_phase":
        data["phases"].append(dict(data["phases"][0], phase_id="unrelated"))
        a["phase_ids"] = [phase_ids[0], "unrelated"]
    elif fault == "foreign_facet":
        a["surface_ids"] = ["nonexistent", "facet-Cu"]
    elif fault == "missing_interface":
        data["sites"][0]["interface_id"] = "not-defined"
    elif fault == "inventory_owner":
        data["interfaces"].append(dict(a, interface_id="second"))
        data["sites"][0]["interface_id"] = "second"
    elif fault == "repeated_phase":
        a["phase_ids"] = [phase_ids[0], phase_ids[0]]
    else:
        data["sites"].append(copy.deepcopy(data["sites"][0]))
    if mode == "native":
        data["format"] = "network-definition/1"
    with pytest.raises(ValueError):
        (validate_bundle if mode == "bundle" else build_network)(data)


def test_missing_and_conflicting_links_are_local_to_identity_report():
    data = read(GENERIC)
    del data["surfaces"][0]["phase_id"]
    data["interfaces"][1]["surface_ids"] = ["rough", "missing-facet"]
    data["sites"][2]["interface_id"] = "missing-junction"
    data["phases"][0]["structural_provenance"] = {"path": "s", "sha256": "bad"}
    view = ownership_report(data)
    assert view["surfaces"]["outer"]["phase_id"] is None
    assert view["surfaces"]["inner"]["phase_id"] == "ordered"
    assert view["phases"]["ordered"]["material_id"] == "film"
    assert view["phases"]["ordered"]["structural_provenance"] is None
    assert view["sites"]["rim-a"]["surface_id"] == "outer" and view["sites"]["rim-a"]["interface_id"] is None
    assert view["interfaces"]["contact-b"]["surface_ids"] == ["rough"]
    assert view["interfaces"]["contact-b"]["phase_ids"] == ["disordered", "ordered"]
    assert any("missing-facet" in warning for warning in view["interfaces"]["contact-b"]["issues"])
    assert view["interfaces"]["contact-a"]["surface_ids"] == ["outer", "rough"]


def test_phase_only_interface_cannot_authorize_a_partially_located_reaction():
    data = read(FIX / "valid.json")
    data["format"] = "network-definition/1"
    third = dict(data["phases"][0], phase_id="third")
    data["phases"].append(third)
    phases = [p["phase_id"] for p in data["phases"]]
    data["interfaces"][0]["phase_ids"] = phases
    data["reactions"][0]["phase_ids"] = phases
    record = build_network(data)["reactions"][0]
    assert record["level"] == "DRAFT" and record["mkm_status"] == "blocked"
    assert "Interface surface assignment incomplete" in record["gaps"]
    data.pop("format")
    with pytest.raises(ValueError, match="interface and surface"):
        validate_bundle(data)


def test_partial_owner_keeps_inventory_and_molecular_observations():
    data = read(FIX / "synthetic_oxide_site_network.json")
    del data["surfaces"][0]["phase_id"]
    n = build_network(data)
    assert "Catalyst phase unconfirmed" in n["reactions"][0]["gaps"]
    obs = read(ROOT / "reports/multiphase/stage_b2_1/oxide_observations.json")
    out = coverage_analysis(n, obs, {})
    assert out["sites"]["acid-A"]["phase_id"] is None
    assert out["sites"]["acid-A"]["site_counts"]["occupied"] == 2
    assert out["species"][0]["molecule_count"]["value"] == 2


def test_unknown_footprint_excludes_inventories_of_other_interfaces():
    data = read(GENERIC)
    data["species"] = [dict(data["species"][3], site_occupancy=None)]
    n = dict(catalog={g: data[g] for g in ("surfaces", "sites")}, species=data["species"], reactions=[])
    out = coverage_analysis(n, {"species": [], "sites": []}, {})
    assert out["sites"]["rim-a"]["unresolved_membership"] == ["probe-a"]
    assert out["sites"]["rim-b"]["unresolved_membership"] == []
    assert out["sites"]["rim-b"]["interface_id"] == "contact-b"

    definition = {"reaction_id": "test-demand", "surface_ids": ["outer", "rough"], "interface_id": "contact-a"}
    vacancy_requirements(
        {
            "reactions": [
                {"definition": definition, "direction": {"forward": {"sites_consumed": None}, "reverse": None}}
            ]
        },
        out["sites"],
    )
    assert out["sites"]["rim-a"]["activity"][0]["vacant_site_order"] is None
    assert out["sites"]["rim-b"]["activity"] == []


def test_shared_canonical_inventory_and_review_cannot_reassign_private_sites():
    data = read(GENERIC)
    index = catalog(data)
    domain = ["outer", "rough"]
    for interface in ["contact-a", "contact-b"]:
        assert resolve_site("shared", domain, index, interface) == "shared"
    with pytest.raises(ValueError, match="different interface"):
        resolve_site("rim-a", domain, index, "contact-b")
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_site("anchor", domain, index, "contact-a")
    reaction = {"surface_ids": domain, "interface_id": "contact-a"}
    new = dict(
        site_id="new", surface_id="outer", site_type="anchor", local_geometry="edge", interface_id="contact-a"
    )
    register_sites(index, reaction, [new], {"outer": {"anchor"}})
    assert index["sites"]["new"] == new
    with pytest.raises(ValueError):
        register_sites(index, dict(reaction, interface_id="contact-b"), [new], {"outer": {"anchor"}})


def test_cross_project_interface_and_legacy_same_phase_boundary():
    data = read(FIX / "valid.json")
    data["projects"].append(dict(data["projects"][0], project_id="other"))
    data["materials"][1]["project_id"] = "other"
    with pytest.raises(ValueError, match="crosses projects"):
        validate_bundle(data)
    generic = read(GENERIC)
    same_phase = {"interface_id": "grain-boundary", "surface_ids": ["inner", "outer"]}
    generic["interfaces"].append(same_phase)
    assert interface_phase_ids(same_phase, catalog(generic)) == {"ordered"}


def test_permutation_and_consistent_id_renaming():
    data = read(GENERIC)
    pairs = [
        (g, k)
        for g, k in (
            ("materials", "material_id"),
            ("phases", "phase_id"),
            ("surfaces", "surface_id"),
            ("sites", "site_id"),
            ("interfaces", "interface_id"),
            ("species", "species_id"),
        )
    ]
    names = {r[k]: f"x-{g}-{9 - i}" for g, k in pairs for i, r in enumerate(data[g])}

    def rename(obj, mapping):
        if isinstance(obj, dict):
            return {mapping.get(k, k): rename(v, mapping) for k, v in obj.items()}
        if isinstance(obj, list):
            return [rename(v, mapping) for v in obj]
        return mapping.get(obj, obj) if isinstance(obj, str) else obj

    changed = rename(data, names)
    for group, _ in pairs:
        changed[group].reverse()
    for iface in changed["interfaces"]:
        iface["phase_ids"].reverse()
        iface.get("surface_ids", []).reverse()
    assert len(register_species(catalog(changed))) == len(data["species"])
    inverse = {v: k for k, v in names.items()}
    view = rename(ownership_report(changed), inverse)
    original = ownership_report(data)
    for key, row in view["interfaces"].items():
        assert set(row["surface_ids"] or []) == set(original["interfaces"][key]["surface_ids"] or [])
        assert set(row["phase_ids"]) == set(original["interfaces"][key]["phase_ids"])
    for group in ["phases", "surfaces", "sites"]:
        assert view[group] == original[group]


def test_snapshot_ownership_uses_original_version_and_hashes():
    directory = ROOT / "reports/multiphase"
    n = read(directory / "phase3_1_1/network.json")
    view = ownership_report(n)
    assert view["network_version"] == n["network_version"]
    assert view["interfaces"]["junction"]["phase_ids"] == ["fcc-Cu", "fcc-Ni"]
    assert (
        view["surfaces"]["facet-Ni"]["structural_provenance"]
        == n["catalog"]["surfaces"][0]["structural_provenance"]
    )
    n["catalog"]["sites"][0]["site_type"] = "changed"
    with pytest.raises(ValueError, match="digest"):
        ownership_report(n)
    sha = read(directory / "phase2_3_1_site_balance.json")["network_version"]
    fe = ownership_report(read(directory / "networks" / f"network-{sha}.json"))
    assert fe["network_version"] == sha
    assert not fe["interfaces"]
    assert all(s["phase_id"] is None for s in fe["surfaces"].values())


def test_readonly_audit_rejects_an_unsupported_version():
    with pytest.raises(ValueError, match="versioned"):
        ownership_report(dict(read(GENERIC), format="network-definition/unknown"))


def test_ownership_only_cli_handles_a_catalog_without_reactions(tmp_path):
    target = tmp_path / "identity.json"
    cmd = [sys.executable, "-m", "scripts.reaction_network", str(GENERIC), "--identity-report", str(target)]
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
    view = read(target)
    assert view.pop("source")["sha256"] == sha256_file(GENERIC)
    assert view == ownership_report(read(GENERIC))
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode != 0
