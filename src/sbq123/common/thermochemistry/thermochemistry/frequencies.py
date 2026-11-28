"""Adapt unreviewed VASP spectra for Scientific Intake."""
from __future__ import annotations

from sbq123.common.workflow.vasp_vibrations import (
    SETTING as SETTING,
    frequency_header as frequency_header,
    parse_frequency_outcar as parse_frequency_outcar,
)

# Legacy two-path spectrum reader used by existing thermochemistry callers.
parse_outcar = parse_frequency_outcar


def draft_intake(observation, reaction_id, state, thermal_basis=None):
    """Convert an observation to an upload that can receive a later documented review."""
    value = {"structure_identity": observation["frequency_structure_sha256"], "atom_map": observation["atom_map"],
             "constraints": "Cartesian flags by atom: " + " ".join(observation["constraints"]),
             "method": "VASP " + " ".join(f"{k}={v}" for k, v in sorted(observation["settings"].items())),
             "expected_modes": observation["expected_cartesian_modes"], "thermal_basis": thermal_basis,
             "frequencies_cm1": observation["frequencies_cm1"]}
    provenance = {k: observation[k] for k in ("source_reference", "source_artifact_hash")}
    return {"schema_version": 1, "reaction_id": reaction_id, "records": [{
        "id": f"{state}-spectrum-{provenance['source_artifact_hash']}", "state": state, "kind": "spectrum",
        "mode": "USER_PROVIDED", "value": value, "provenance": provenance,
        "validation": {"validation_status": "unreviewed", "compatibility_status": "unknown",
                       "validated_properties": [], "limitations": []}, "acceptance": {"acceptance_status": "pending"},
    }]}
