"""Persistence adapter: consume evidence and owning scientific validation, never decide science."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.adsmind_lite.evidence_lifecycle import assess_evidence, require_transferable
from scripts.artifact_io import sha256_file, sha256_json
from scripts.vasp_result_gate import validate_vasp_relaxation
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.scientific_validation import finite_number


def validate_result_acceptance(connection, row, provenance):
    status = row["validation_status"]
    stage = provenance.get("registry_stage", "accepted_result" if status.startswith("accepted") else "candidate")
    if stage == "published_result":
        raise ValueError("publication requires the separate existing promotion workflow")
    if stage not in {"candidate", "accepted_result"}:
        raise ValueError("prediction cannot enter accepted registry")
    evidence = provenance.get("evidence")
    if stage == "candidate" and not status.startswith("accepted"):
        if not evidence or assess_evidence(evidence)["state"] == "IMPORTED":
            raise ValueError("candidate requires schema-valid evidence")
        return
    if stage != "accepted_result" or not evidence:
        raise ValueError("accepted result requires reviewed evidence and scientific validation")
    if evidence.get("claim", {}).get("type") != "calculated_result":
        raise ValueError("prediction/external claim cannot become an accepted calculated result")
    compatibility = connection.execute("SELECT * FROM calculation_compatibility WHERE calculation_id=?", (row["calculation_id"],)).fetchone()
    calculation = connection.execute("SELECT module FROM calculations WHERE calculation_id=?", (row["calculation_id"],)).fetchone()
    if compatibility is None or calculation is None:
        raise ValueError("accepted result missing compatibility binding")
    target = {"domain": calculation["module"], "scope": "registry_acceptance",
              "compatibility": json.loads(compatibility["compatibility_json"])}
    require_transferable(evidence, target)
    validation = provenance.get("scientific_validation", {})
    claim = evidence["claim"]
    if claim.get("result_sha256") != sha256_json(row) or claim.get("validation_sha256") != sha256_json(validation):
        raise ValueError("review must bind the exact result and scientific validation")
    _validate_relaxation_value(connection, row, validation, target)


def _validate_relaxation_value(connection, row, validation, target):
    if validation.get("owner") != "vasp_relaxation":
        raise ValueError("use the owning scientific registry workflow for this result kind")
    directory = Path(validation["directory"]).resolve()
    bindings = validation.get("source_files", {})
    if set(bindings) != {"INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR"}:
        raise ValueError("scientific validation requires complete source binding")
    if any(sha256_file(directory / name) != digest for name, digest in bindings.items()):
        raise ValueError("scientific validation source changed")
    source = connection.execute("SELECT * FROM files WHERE file_id=?", (row.get("source_file_id"),)).fetchone()
    if source is None or source["calculation_id"] != row["calculation_id"] or source["sha256"] != bindings["OUTCAR"]:
        raise ValueError("result source is not the validated calculation output")
    validate_vasp_relaxation(directory)
    parsed = parse_final_outcar(directory / "OUTCAR")
    if row["result_name"] != "final_toten" or row.get("unit") != "eV":
        raise ValueError("this adapter binds final_toten in eV; use the owning workflow for other result kinds")
    if finite_number(row.get("numeric_value"), "result energy") != finite_number(parsed["final_toten_eV"], "source energy"):
        raise ValueError("result value differs from validated output")
    if row.get("reference_convention") != target["compatibility"].get("final_energy_convention"):
        raise ValueError("result convention does not match reviewed compatibility")
    if any(sha256_file(directory / name) != digest for name, digest in bindings.items()):
        raise ValueError("scientific validation source changed during validation")
