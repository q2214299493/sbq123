from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.build import bcc100, bcc111
from ase.io import read as ase_read
from ase.io import write as ase_write

from scripts.adsmind_lite.core import (
    analyze_relaxed_tree,
    deduplicate_records,
    detect_surface_sites,
    export_selected,
    generate_candidates,
    load_yaml,
    read_json,
    validate_candidates,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
SLAB = ROOT / "calculations" / "true_fe110_clean_20260629" / "POSCAR"
CONFIG = ROOT / "configs" / "adsmind_lite"


def write_site_plan(path: Path, adsorbates: list[str], sites: dict) -> Path:
    site_classes = [site["site_class"] for site in sites.get("sites", [])]
    plans = []
    for adsorbate in adsorbates:
        candidates = [
            {
                "motif_id": f"{adsorbate}_{site_class}",
                "site_pattern": site_class,
                "generator_site_class": site_class,
                "priority": index,
                "build_ready": True,
            }
            for index, site_class in enumerate(site_classes, start=1)
        ]
        plans.append({"species": adsorbate, "decision": "READY", "candidate_count": len(candidates), "candidates": candidates})
    write_json(path, {"species_plans": plans})
    return path


def prepare_candidates(tmp_path: Path, adsorbates: list[str]) -> tuple[Path, Path, list[dict]]:
    sites = detect_surface_sites(
        SLAB,
        "Fe110",
        "metallic_fe",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
    )
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    candidate_root = tmp_path / "candidates"
    plan_path = write_site_plan(tmp_path / "plan.json", adsorbates, sites)
    records = generate_candidates(
        SLAB,
        sites_path,
        adsorbates,
        CONFIG / "adsorbate_rules.yaml",
        candidate_root,
        plan_path,
    )
    return sites_path, candidate_root, records


def copy_candidates_as_relaxed(candidate_root: Path, relaxed_root: Path) -> None:
    for metadata_path in candidate_root.rglob("metadata.json"):
        relative = metadata_path.parent.relative_to(candidate_root)
        destination = relaxed_root / relative / "CONTCAR"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(metadata_path.parent / "POSCAR", destination)


def write_surface(path: Path, atoms: Atoms) -> Path:
    atoms.set_pbc([True, True, True])
    ase_write(path, atoms, format="vasp", direct=True, vasp5=True)
    return path


def test_fe110_dry_run_detects_sites_and_generates_initial_adsorbates(tmp_path: Path) -> None:
    sites_path, candidate_root, records = prepare_candidates(tmp_path, ["CO", "H", "O", "OH", "H2O", "C"])
    sites = read_json(sites_path)

    assert [site["site_class"] for site in sites["sites"]] == [
        "top_Fe",
        "bridge_FeFe_short",
        "bridge_FeFe_long",
        "hollow_FeFeFe",
    ]
    assert 2.35 < sites["sites"][1]["support_distance_angstrom"] < 2.55
    assert 2.70 < sites["sites"][2]["support_distance_angstrom"] < 2.95
    assert len(records) == 24

    validated = validate_candidates(
        candidate_root,
        CONFIG / "surfaces.yaml",
        CONFIG / "adsorbate_rules.yaml",
        CONFIG / "analysis_rules.yaml",
    )
    assert len(validated) == 24
    assert all(record["validation_passed"] for record in validated)


def test_candidate_generation_uses_only_evidence_planned_sites(tmp_path: Path) -> None:
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    selected = [site for site in sites["sites"] if site["site_class"] in {"top_Fe", "hollow_FeFeFe"}]
    plan_path = write_site_plan(tmp_path / "two_site_plan.json", ["C"], {"sites": selected})
    records = generate_candidates(
        SLAB,
        sites_path,
        ["C"],
        CONFIG / "adsorbate_rules.yaml",
        tmp_path / "two_candidates",
        plan_path,
    )
    assert [record["planned_site_class"] for record in records] == ["top_Fe", "hollow_FeFeFe"]


def test_carbide_and_oxide_are_gated_without_explicit_labels() -> None:
    carbide = detect_surface_sites(
        SLAB,
        "Fe5C2_010",
        "iron_carbide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
    )
    oxide = detect_surface_sites(
        SLAB,
        "Fe3O4_001",
        "iron_oxide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
    )

    assert carbide["status"] == "NEEDS_REVIEW"
    assert oxide["status"] == "NEEDS_REVIEW"
    assert carbide["reason_code"] == "explicit_site_label_required"
    assert oxide["sites"] == []


def test_fe100_and_fe111_have_distinct_automatic_metallic_sites(tmp_path: Path) -> None:
    cases = [
        (
            "Fe100",
            bcc100("Fe", size=(3, 3, 5), a=2.83, vacuum=7.5),
            {"top_Fe", "bridge_FeFe_short", "hollow_FeFeFeFe"},
        ),
        (
            "Fe111",
            bcc111("Fe", size=(3, 4, 5), a=2.83, vacuum=7.5, orthogonal=True),
            {"top_Fe", "bridge_FeFe_short", "hollow_FeFeFe"},
        ),
    ]
    for surface_name, atoms, expected in cases:
        structure = write_surface(tmp_path / f"{surface_name}.vasp", atoms)
        sites = detect_surface_sites(
            structure,
            surface_name,
            "metallic_fe",
            CONFIG / "surfaces.yaml",
            CONFIG / "site_rules.yaml",
        )
        assert sites["status"] == "PASS"
        assert {site["site_class"] for site in sites["sites"]} == expected
        assert all(not site["needs_review"] for site in sites["sites"])


def test_simple_c1_adsorbate_defaults_high_on_metallic_fe(tmp_path: Path) -> None:
    _, _, records = prepare_candidates(tmp_path, ["CH"])
    assert records
    assert all(record["confidence_level"] == "high" for record in records)


def test_carbide_manifest_preserves_lattice_adsorbate_identity_and_export_gate(tmp_path: Path) -> None:
    surface = write_surface(
        tmp_path / "Fe5C2_010.vasp",
        Atoms(
            ["Fe", "Fe", "Fe", "C"],
            positions=[[1.5, 1.5, 4.0], [4.5, 1.5, 4.0], [3.0, 4.0, 4.0], [3.0, 2.5, 3.2]],
            cell=[6.0, 6.0, 15.0],
        ),
    )
    manifest = {
        "surface_name": "Fe5C2_010",
        "surface_family": "iron_carbide",
        "default_confidence": "medium",
        "atom_labels": {"1": "Fe", "2": "Fe", "3": "Fe", "4": "C_lattice"},
        "enabled_site_classes": ["top_Fe", "bridge_FeC_lattice"],
        "explicit_sites": [
            {
                "site_class": "top_Fe",
                "fractional_xy": [0.25, 0.25],
                "support_indices_1based": [1],
                "explicitly_validated": True,
            },
            {
                "site_class": "bridge_FeC_lattice",
                "fractional_xy": [0.375, 1.0 / 3.0],
                "support_indices_1based": [1, 4],
                "explicitly_validated": True,
            },
        ],
        "high_risk_sites": {},
    }
    manifest_path = tmp_path / "carbide_manifest.json"
    write_json(manifest_path, manifest)
    sites = detect_surface_sites(
        surface,
        "Fe5C2_010",
        "iron_carbide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
        manifest_path,
    )
    assert sites["status"] == "PASS"
    assert all(site["confidence_level"] == "medium" for site in sites["sites"])

    sites_path = tmp_path / "carbide_sites.json"
    write_json(sites_path, sites)
    candidate_root = tmp_path / "carbide_candidates"
    plan_path = write_site_plan(tmp_path / "carbide_plan.json", ["CO", "C", "CH"], sites)
    generated = generate_candidates(
        surface,
        sites_path,
        ["CO", "C", "CH"],
        CONFIG / "adsorbate_rules.yaml",
        candidate_root,
        plan_path,
    )
    assert len(generated) == 6
    assert all(record["confidence_level"] == "medium" for record in generated)
    assert all(
        set(record["slab_indices_structure_0based"]).isdisjoint(record["adsorbate_indices_structure_0based"]) for record in generated
    )
    validated = validate_candidates(
        candidate_root,
        CONFIG / "surfaces.yaml",
        CONFIG / "adsorbate_rules.yaml",
        CONFIG / "analysis_rules.yaml",
    )
    assert all(record["validation_passed"] for record in validated)
    assert all(record["recommend_for_vasp"] for record in validated)
    assert len(export_selected(validated, tmp_path / "default_export")) == 6
    assert export_selected(validated, tmp_path / "high_only_export", include_medium=False) == []


def test_carbide_missing_lattice_carbon_label_is_low_confidence(tmp_path: Path) -> None:
    surface = write_surface(
        tmp_path / "Fe2C.vasp",
        Atoms(["Fe", "Fe", "C"], positions=[[1.0, 1.0, 4.0], [4.0, 1.0, 4.0], [2.5, 3.0, 3.5]], cell=[6, 6, 15]),
    )
    manifest = {
        "surface_name": "Fe2C_001",
        "surface_family": "iron_carbide",
        "default_confidence": "medium",
        "atom_labels": {"1": "Fe", "2": "Fe"},
        "enabled_site_classes": ["top_Fe"],
        "explicit_sites": [
            {
                "site_class": "top_Fe",
                "fractional_xy": [1.0 / 6.0, 1.0 / 6.0],
                "support_indices_1based": [1],
                "explicitly_validated": True,
            }
        ],
        "high_risk_sites": {},
    }
    manifest_path = tmp_path / "ambiguous_carbide.json"
    write_json(manifest_path, manifest)
    sites = detect_surface_sites(
        surface,
        "Fe2C_001",
        "iron_carbide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
        manifest_path,
    )
    sites_path = tmp_path / "ambiguous_sites.json"
    write_json(sites_path, sites)
    candidate_root = tmp_path / "ambiguous_candidates"
    plan_path = write_site_plan(tmp_path / "ambiguous_plan.json", ["C"], sites)
    generate_candidates(surface, sites_path, ["C"], CONFIG / "adsorbate_rules.yaml", candidate_root, plan_path)
    [result] = validate_candidates(
        candidate_root,
        CONFIG / "surfaces.yaml",
        CONFIG / "adsorbate_rules.yaml",
        CONFIG / "analysis_rules.yaml",
    )
    assert result["validation_passed"] is False
    assert result["confidence_level"] == "low"
    assert result["needs_review"] is True
    assert result["reason_code"] == "lattice_adsorbate_atom_confusion"


def test_oxide_vacancy_requires_explicit_role_tag_and_validation(tmp_path: Path) -> None:
    surface = write_surface(
        tmp_path / "Fe3O4_001.vasp",
        Atoms(
            ["Fe", "Fe", "O"],
            positions=[[1.5, 1.5, 4.0], [4.5, 1.5, 4.0], [3.0, 4.0, 3.5]],
            cell=[6.0, 6.0, 15.0],
        ),
    )
    base = {
        "surface_name": "Fe3O4_001",
        "surface_family": "iron_oxide",
        "default_confidence": "medium",
        "atom_labels": {"1": "Fe_oct", "2": "Fe_tet", "3": "O_lattice"},
        "enabled_site_classes": ["oxygen_vacancy"],
        "surface_tags": ["iron_oxide"],
    }
    untagged_manifest = {
        **base,
        "explicit_sites": [
            {
                "site_class": "oxygen_vacancy",
                "site_role": "vacancy_O",
                "fractional_xy": [0.5, 0.5],
                "support_indices_1based": [1, 2],
                "explicitly_validated": False,
            }
        ],
        "high_risk_sites": {"oxygen_vacancy": {"explicitly_tagged": False}},
    }
    untagged_path = tmp_path / "oxide_untagged.json"
    write_json(untagged_path, untagged_manifest)
    untagged = detect_surface_sites(
        surface,
        "Fe3O4_001",
        "iron_oxide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
        untagged_path,
    )
    assert untagged["sites"][0]["reason_code"] == "oxygen_vacancy_not_tagged"
    assert untagged["sites"][0]["confidence_level"] == "low"
    assert untagged["sites"][0]["needs_review"] is True

    validated_manifest = {
        **base,
        "explicit_sites": [
            {
                "site_class": "oxygen_vacancy",
                "site_role": "vacancy_O",
                "fractional_xy": [0.5, 0.5],
                "support_indices_1based": [1, 2],
                "explicitly_validated": True,
            }
        ],
        "high_risk_sites": {
            "oxygen_vacancy": {"explicitly_tagged": True, "explicitly_validated": True},
            "hydroxylated_surface": {"present": False},
        },
    }
    validated_path = tmp_path / "oxide_validated.json"
    write_json(validated_path, validated_manifest)
    validated = detect_surface_sites(
        surface,
        "Fe3O4_001",
        "iron_oxide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
        validated_path,
    )
    assert validated["status"] == "PASS"
    assert validated["sites"][0]["confidence_level"] == "medium"
    assert validated["sites"][0]["needs_review"] is False


def test_oxide_h2o_dissociation_stays_review_only(tmp_path: Path) -> None:
    surface = write_surface(
        tmp_path / "Fe3O4_h2o.vasp",
        Atoms(
            ["Fe", "Fe", "O"],
            positions=[[1.5, 1.5, 4.0], [4.5, 1.5, 4.0], [3.0, 4.0, 3.5]],
            cell=[6.0, 6.0, 15.0],
        ),
    )
    manifest = {
        "surface_name": "Fe3O4_001",
        "surface_family": "iron_oxide",
        "default_confidence": "medium",
        "atom_labels": {"1": "Fe_oct", "2": "Fe_tet", "3": "O_lattice"},
        "enabled_site_classes": ["top_Fe_oct"],
        "explicit_sites": [
            {
                "site_class": "top_Fe_oct",
                "fractional_xy": [0.25, 0.25],
                "support_indices_1based": [1],
                "explicitly_validated": True,
            }
        ],
        "high_risk_sites": {
            "oxygen_vacancy": {"explicitly_tagged": False},
            "hydroxylated_surface": {"present": False},
        },
    }
    manifest_path = tmp_path / "oxide_h2o_manifest.json"
    write_json(manifest_path, manifest)
    sites = detect_surface_sites(
        surface,
        "Fe3O4_001",
        "iron_oxide",
        CONFIG / "surfaces.yaml",
        CONFIG / "site_rules.yaml",
        manifest_path,
    )
    sites_path = tmp_path / "oxide_h2o_sites.json"
    write_json(sites_path, sites)
    candidate_root = tmp_path / "oxide_h2o_candidates"
    plan_path = write_site_plan(tmp_path / "oxide_h2o_plan.json", ["H2O"], sites)
    [generated] = generate_candidates(
        surface,
        sites_path,
        ["H2O"],
        CONFIG / "adsorbate_rules.yaml",
        candidate_root,
        plan_path,
    )
    validated = validate_candidates(
        candidate_root,
        CONFIG / "surfaces.yaml",
        CONFIG / "adsorbate_rules.yaml",
        CONFIG / "analysis_rules.yaml",
    )
    assert validated[0]["validation_passed"] is True

    relaxed_root = tmp_path / "oxide_h2o_relaxed"
    copy_candidates_as_relaxed(candidate_root, relaxed_root)
    relaxed_path = relaxed_root / Path(generated["initial_structure"]).parent.relative_to(candidate_root) / "CONTCAR"
    atoms = ase_read(relaxed_path, format="vasp")
    departing_hydrogen = int(generated["adsorbate_indices_structure_0based"][-1])
    atoms.positions[departing_hydrogen, 2] += 3.0
    ase_write(relaxed_path, atoms, format="vasp", direct=True, vasp5=True)

    [analyzed] = analyze_relaxed_tree(
        candidate_root,
        relaxed_root,
        sites_path,
        CONFIG / "analysis_rules.yaml",
    )
    assert analyzed["dissociated"] is True
    assert analyzed["confidence_level"] == "low"
    assert analyzed["needs_review"] is True
    assert analyzed["recommend_for_vasp"] is False


def test_relaxed_analyzer_detects_slip_and_dissociation(tmp_path: Path) -> None:
    sites_path, candidate_root, _ = prepare_candidates(tmp_path, ["CO"])
    relaxed_root = tmp_path / "relaxed"
    copy_candidates_as_relaxed(candidate_root, relaxed_root)
    sites = read_json(sites_path)

    top_metadata = next(path for path in candidate_root.rglob("metadata.json") if read_json(path)["planned_site_class"] == "top_Fe")
    top_record = read_json(top_metadata)
    top_relative = top_metadata.parent.relative_to(candidate_root)
    top_relaxed = relaxed_root / top_relative / "CONTCAR"
    atoms = ase_read(top_relaxed, format="vasp")
    short_xy = next(site["fractional_xy"] for site in sites["sites"] if site["site_class"] == "bridge_FeFe_short")
    fractional = atoms.get_scaled_positions()
    anchor = int(top_record["anchor_index_structure_0based"])
    translation = np.array(short_xy) - fractional[anchor, :2]
    fractional[anchor:, :2] += translation
    atoms.set_scaled_positions(fractional)
    ase_write(top_relaxed, atoms, format="vasp", direct=True, vasp5=True)

    hollow_metadata = next(
        path for path in candidate_root.rglob("metadata.json") if read_json(path)["planned_site_class"] == "hollow_FeFeFe"
    )
    hollow_record = read_json(hollow_metadata)
    hollow_relative = hollow_metadata.parent.relative_to(candidate_root)
    hollow_relaxed = relaxed_root / hollow_relative / "CONTCAR"
    atoms = ase_read(hollow_relaxed, format="vasp")
    oxygen = int(hollow_record["slab_atom_count"]) + 1
    atoms.positions[oxygen, 2] += 3.0
    ase_write(hollow_relaxed, atoms, format="vasp", direct=True, vasp5=True)

    results = analyze_relaxed_tree(
        candidate_root,
        relaxed_root,
        sites_path,
        CONFIG / "analysis_rules.yaml",
    )
    slipped = next(record for record in results if record["candidate_id"] == top_record["candidate_id"])
    dissociated = next(record for record in results if record["candidate_id"] == hollow_record["candidate_id"])

    assert slipped["relaxed_site_class"] == "bridge_FeFe_short"
    assert slipped["chemical_slip"] is True
    assert slipped["dissociated"] is False
    assert dissociated["dissociated"] is True
    assert dissociated["needs_review"] is True
    assert dissociated["recommend_for_vasp"] is False


def test_deduplication_and_export_keep_only_recommended_unique_state(tmp_path: Path) -> None:
    sites_path, candidate_root, _ = prepare_candidates(tmp_path, ["CO"])
    relaxed_root = tmp_path / "relaxed"
    copy_candidates_as_relaxed(candidate_root, relaxed_root)
    analyzed = analyze_relaxed_tree(
        candidate_root,
        relaxed_root,
        sites_path,
        CONFIG / "analysis_rules.yaml",
    )
    source = next(record for record in analyzed if record["planned_site_class"] == "top_Fe")
    first = {**source, "candidate_id": "state_a", "energy_ev": -1.00}
    second = {**source, "candidate_id": "state_b", "energy_ev": -0.98}
    low = {**source, "candidate_id": "state_low", "confidence_level": "low", "recommend_for_vasp": True}

    deduplicated = deduplicate_records([second, first], load_yaml(CONFIG / "analysis_rules.yaml"))
    assert sum(record["duplicate"] for record in deduplicated) == 1
    exported = export_selected([*deduplicated, low], tmp_path / "vasp_ready")

    assert [record["candidate_id"] for record in exported] == ["state_a"]
    assert (tmp_path / "vasp_ready" / "Fe110" / "CO" / "state_a" / "POSCAR").is_file()
