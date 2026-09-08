from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from ase.io import read as ase_read

from scripts.adsmind_lite.core import detect_surface_sites, generate_candidates, read_json, validate_candidates, write_json
from scripts.adsmind_lite.relaxed_analysis import connectivity_change, hard_contact_distance, is_hard_contact


ROOT = Path(__file__).resolve().parents[1]
SLAB = ROOT / "calculations" / "true_fe110_clean_20260629" / "POSCAR"
CONFIG = ROOT / "configs" / "adsmind_lite"


def test_same_site_distinct_orientations_survive_initial_validation(tmp_path: Path) -> None:
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    plan_path = tmp_path / "plan.json"
    write_json(
        plan_path,
        {
            "species_plans": [
                {
                    "species": "H2O",
                    "decision": "READY",
                    "candidate_count": 2,
                    "candidates": [
                        {
                            "motif_id": "H2O_top_a",
                            "configuration_id": "orientation_a",
                            "site_pattern": "top",
                            "priority": 1,
                            "orientation_degrees": 0.0,
                            "build_ready": True,
                        },
                        {
                            "motif_id": "H2O_top_b",
                            "configuration_id": "orientation_b",
                            "site_pattern": "top",
                            "priority": 2,
                            "orientation_degrees": 90.0,
                            "build_ready": True,
                        },
                    ],
                }
            ]
        },
    )
    candidate_root = tmp_path / "candidates"

    generated = generate_candidates(
        SLAB,
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

    assert len(generated) == 2
    assert all(record["validation_passed"] for record in validated)
    first = ase_read(generated[0]["initial_structure"], format="vasp").positions[-3:]
    second = ase_read(generated[1]["initial_structure"], format="vasp").positions[-3:]
    assert not np.allclose(first, second)


def test_connectivity_rearrangement_is_not_dissociation() -> None:
    change = connectivity_change(3, [(0, 1), (1, 2)], [(0, 1), (0, 2)])

    assert change["connectivity_changed"] is True
    assert change["dissociated"] is False
    assert change["chemical_event"] == "bond_rearrangement"
    assert change["initial_fragment_count"] == change["relaxed_fragment_count"] == 1


def test_connectivity_fragment_increase_is_dissociation() -> None:
    change = connectivity_change(3, [(0, 1), (1, 2)], [(0, 1)])

    assert change["dissociated"] is True
    assert change["chemical_event"] == "dissociation"
    assert change["relaxed_fragment_count"] == 2


def test_hard_contact_cutoff_has_explicit_angstrom_unit_and_strict_boundary() -> None:
    rules = yaml.safe_load((CONFIG / "analysis_rules.yaml").read_text(encoding="utf-8"))
    cutoff = hard_contact_distance(rules)

    assert cutoff == 0.80
    assert is_hard_contact(cutoff - 1e-6, cutoff) is True
    assert is_hard_contact(cutoff, cutoff) is False
    assert is_hard_contact(cutoff + 1e-6, cutoff) is False


def test_generated_metadata_records_configuration_identity(tmp_path: Path) -> None:
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    plan_path = tmp_path / "plan.json"
    write_json(
        plan_path,
        {
            "species_plans": [
                {
                    "species": "H2O",
                    "decision": "READY",
                    "candidate_count": 1,
                    "candidates": [
                        {
                            "motif_id": "H2O_top_a",
                            "configuration_id": "orientation_a",
                            "site_pattern": "top",
                            "orientation_degrees": 30.0,
                            "priority": 1,
                            "build_ready": True,
                        }
                    ],
                }
            ]
        },
    )

    [record] = generate_candidates(
        SLAB,
        sites_path,
        ["H2O"],
        CONFIG / "adsorbate_rules.yaml",
        tmp_path / "candidates",
        plan_path,
    )

    stored = read_json(Path(record["initial_structure"]).with_name("metadata.json"))
    assert stored["motif_id"] == "H2O_top_a"
    assert stored["configuration_id"] == "orientation_a"
    assert stored["orientation_degrees"] == 30.0
