"""Tests for the standalone reviewed kinetic-parameter handoff contract."""

from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from src.kinetics.handoff import (
    canonical_json_sha256,
    file_sha256,
    validate_handoff,
    validate_handoff_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "examples" / "kinetic_parameter_handoff.template.json"
ROLES = {
    "initial": "INITIAL_ENERGY",
    "final": "FINAL_ENERGY",
    "ts": "TRANSITION_STATE_ENERGY",
    "frequency": "FREQUENCY_EVIDENCE",
    "connectivity": "CONNECTIVITY_EVIDENCE",
    "validation": "VALIDATION_REPORT",
    "review": "REVIEW_EVIDENCE",
}


def _state_validation() -> dict[str, str]:
    """Return one accepted state-validation fixture."""

    return {
        "electronic_convergence": "PASS",
        "ionic_convergence": "NOT_APPLICABLE",
        "geometry_validation": "PASS",
        "scientific_status": "ACCEPTED",
    }


def _write_json(path: Path, value: object) -> None:
    """Write strict JSON for one test fixture."""

    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _approved_contract(root: Path) -> dict[str, object]:
    """Create a complete synthetic contract with real fixture hashes."""

    record = {"reaction_id": "r1", "status": "UNVERIFIED"}
    dataset = {"schema_version": "1.0", "records": [record]}
    dataset_path = root / "kinetic_dataset.json"
    _write_json(dataset_path, dataset)

    sources: list[dict[str, object]] = []
    for source_id, role in ROLES.items():
        path = root / f"{source_id}.txt"
        path.write_text(f"fixture evidence for {source_id}\n", encoding="utf-8")
        sources.append(
            {
                "source_id": source_id,
                "role": role,
                "path": path.name,
                "storage": "LOCAL",
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "calculation_id": f"calc-{source_id}",
                "job_id": f"job-{source_id}",
                "extraction_location": "test fixture record",
                "verification_status": "VERIFIED",
            }
        )

    energy_sources = {
        "initial": ["initial"],
        "final": ["final"],
        "transition_state": ["ts"],
        "reaction": ["initial", "final"],
        "activation_forward": ["initial", "ts"],
        "activation_reverse": ["final", "ts"],
    }
    energy_numbers = {
        "initial": -100.0,
        "final": -99.8,
        "transition_state": -99.0,
        "reaction": 0.2,
        "activation_forward": 1.0,
        "activation_reverse": 0.8,
    }
    values = {
        key: {
            "value": value,
            "source_ids": energy_sources[key],
            "extraction_method": "explicit fixture extraction",
        }
        for key, value in energy_numbers.items()
    }
    digest = "a" * 64
    return {
        "schema_version": "1.0.0",
        "handoff_id": "handoff-r1-v1",
        "status": "APPROVED",
        "created_at": "2026-07-31T00:00:00Z",
        "dataset_binding": {
            "path": dataset_path.name,
            "sha256": file_sha256(dataset_path),
            "schema_version": "1.0",
            "reaction_id": "r1",
            "reaction_record_sha256": canonical_json_sha256(record),
        },
        "energetics": {
            "basis": "ELECTRONIC_ENERGY",
            "unit": "eV",
            "temperature_K": None,
            "pressure_bar": None,
            "reference_convention_id": "matched-static-v1",
            "consistency_tolerance_eV": 1e-6,
            "values": values,
        },
        "method": {
            "code": "VASP",
            "code_version": "6.x",
            "xc_functional": "PBE",
            "pseudopotential_family": "PAW-PBE",
            "pseudopotential_spec_sha256": digest,
            "encut_eV": 400.0,
            "kpoints": "Gamma 5x5x1",
            "spin_policy": "ISPIN=2",
            "ismear": 1,
            "sigma_eV": 0.1,
            "ediff_eV": 1e-6,
            "slab_model_id": "fixture-slab",
            "fixed_atom_indices_sha256": digest,
            "dipole_policy": "LDIPOL=false",
            "vacuum_angstrom": 15.0,
            "energy_convention_id": "matched-static-v1",
            "compatibility_fingerprint_sha256": digest,
        },
        "sources": sources,
        "validation": {
            "automated_status": "PASS",
            "dataset_validation": "PASS",
            "method_compatibility": "PASS",
            "initial_state": _state_validation(),
            "final_state": _state_validation(),
            "transition_state": _state_validation(),
            "ts_grade": "A",
            "frequency_validation": "PASS",
            "connectivity_validation": "PASS",
            "validation_report_source_id": "validation",
        },
        "review": {
            "decision": "APPROVED",
            "reviewer_id": "reviewer-fixture",
            "reviewed_at": "2026-07-31T01:00:00Z",
            "rationale": "Synthetic contract fixture only.",
            "evidence_source_id": "review",
        },
        "downstream": {
            "eligibility": "ELIGIBLE",
            "software": ["CATKINAS", "ZACROS"],
        },
    }


class KineticHandoffTests(unittest.TestCase):
    """Verify draft handling and every release-critical approved invariant."""

    def test_draft_template_is_valid_but_not_eligible(self) -> None:
        result = validate_handoff_file(TEMPLATE)

        self.assertEqual(result.status, "VALID_NOT_ELIGIBLE")
        self.assertFalse(result.eligible)
        self.assertEqual(result.errors, ())
        self.assertIn("HANDOFF_NOT_APPROVED", result.warnings)

    def test_complete_approved_contract_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = validate_handoff(_approved_contract(root), root)

        self.assertEqual(result.status, "ELIGIBLE")
        self.assertTrue(result.eligible)
        self.assertEqual(result.errors, ())

    def test_nonfinite_energy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract = _approved_contract(root)
            contract["energetics"]["values"]["activation_forward"]["value"] = math.nan

            result = validate_handoff(contract, root)

        self.assertFalse(result.eligible)
        self.assertTrue(
            any(error.startswith("NON_FINITE_NUMBER:") for error in result.errors)
        )

    def test_energy_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract = _approved_contract(root)
            contract["energetics"]["values"]["activation_reverse"]["value"] = 0.9

            result = validate_handoff(contract, root)

        self.assertIn(
            "ENERGY_IDENTITY_MISMATCH:activation_reverse",
            result.errors,
        )

    def test_dataset_record_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract = _approved_contract(root)
            contract["dataset_binding"]["reaction_record_sha256"] = "b" * 64

            result = validate_handoff(contract, root)

        self.assertIn("BOUND_REACTION_RECORD_HASH_MISMATCH", result.errors)

    def test_missing_review_approval_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract = copy.deepcopy(_approved_contract(root))
            contract["review"]["decision"] = "PENDING"

            result = validate_handoff(contract, root)

        self.assertFalse(result.eligible)
        self.assertTrue(any(error.startswith("SCHEMA_ERROR:review") for error in result.errors))


if __name__ == "__main__":
    unittest.main()
