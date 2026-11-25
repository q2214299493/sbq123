"""Shared MatRIS/AQCat25 label binding and dataset validation (no training)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, require_sha256
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent.utils_structure import read_poscar
from scripts.scientific_validation import finite_array, finite_number
from scripts.provenance_fields import required_text

LABEL_KIND = "dual_model_ts_vasp_force_label_set"
EXPECTED_CONVENTION = "fe110_converged_toten_sigma0p20_v1"
DATASET_STATES = ("RAW", "PARSED", "VALIDATED", "TRAINING_ELIGIBLE", "USED_IN_MODEL")


def _validate_label_set(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = path.resolve()
    payload = load_json_object(path)
    if payload.get("document_kind") != LABEL_KIND:
        raise ValueError(f"invalid TS label set: {path}")
    reaction_id = required_text(payload.get("reaction_id"), "TS reaction identity")
    if payload.get("scientific_status") != "accepted_force_labels_only":
        raise ValueError(f"TS label set is not accepted: {path}")
    checks = payload.get("checks", {})
    required_checks = (
        "all_scheduler_DONE",
        "all_normal_vasp_completion",
        "all_electronically_converged",
        "all_exact_structure_hashes_match",
        "all_complete_force_blocks",
    )
    if not all(checks.get(field) is True for field in required_checks):
        raise ValueError(f"TS label set quality checks failed: {path}")
    compatibility = payload.get("compatibility", {})
    if (
        compatibility.get("final_energy_convention") != EXPECTED_CONVENTION
        or compatibility.get("ISMEAR") != 1
        or float(compatibility.get("SIGMA_eV", -1.0)) != 0.2
    ):
        raise ValueError(f"incompatible TS label set: {path}")
    batch_path = Path(str(payload.get("source_batch_path", ""))).resolve()
    if (
        not batch_path.is_file()
        or sha256_file(batch_path) != payload.get("source_batch_sha256")
    ):
        raise ValueError(f"TS source batch binding failed: {path}")
    batch = load_json_object(batch_path)
    if batch.get("reaction_id") != reaction_id:
        raise ValueError("TS reaction identity differs from source batch")
    batch_rows = {row["sample_id"]: row for row in batch.get("labels", [])}
    for row in payload.get("labels", []):
        request = batch_rows.get(row.get("sample_id"))
        if not isinstance(request, dict):
            raise ValueError("label lacks source calculation row")
        root = path.parent.resolve()
        directory = (root / required_text(request.get("directory"), "label directory")).resolve()
        if not directory.is_relative_to(root):
            raise ValueError("label directory escapes source root")
        hashes = row.get("input_output_hashes", {})
        if not all(name in hashes for name in ("POSCAR", "INCAR", "OUTCAR", "OSZICAR")):
            raise ValueError("training label lacks complete calculation source evidence")
        for name, digest in hashes.items():
            require_sha256(digest, label=f"training source {name}")
            if name == "POTCAR":  # Collector binds remote licensed identity, not local contents.
                continue
            source = (directory / name).resolve()
            if not source.is_relative_to(directory) or not source.is_file() or sha256_file(source) != digest:
                raise ValueError("training label source file binding failed")
        if row.get("type", "calculated_result") != "calculated_result":
            raise ValueError("prediction cannot become a VASP training label")
    return payload, batch


def _load_bound(reference: dict[str, Any], *, name: str) -> tuple[Path, dict[str, Any]]:
    path = Path(str(reference.get("path", ""))).resolve()
    expected = str(reference.get("sha256", ""))
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{name} binding failed")
    return path, load_json_object(path)


def calculation_identity(row: dict) -> str:
    """Use explicit calculation identity or the collector's bound scheduler job."""
    if row.get("calculation_id") is not None:
        return required_text(row["calculation_id"], "calculation identity")
    if row.get("source_directory") is not None:
        return required_text(row["source_directory"], "calculation source directory identity")
    from scripts.scheduler_evidence import validate_stored_lsf_evidence

    _, evidence = _load_bound(row.get("scheduler_evidence", {}), name="label scheduler evidence")
    validate_stored_lsf_evidence(evidence, required_status="DONE")
    if str(row.get("job_id")) != evidence["job_id"]:
        raise ValueError("label job identity mismatch")
    return f"{evidence['server_alias']}/{evidence['scheduler']}/{evidence['job_id']}"


def _source_labels(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    path, payload = _load_bound(reference, name="VASP label source")
    if payload.get("document_kind") == "vasp_ts_force_label":
        from scripts.ts_strategy_engine.active_learning_common import load_bound_vasp_label

        report = load_bound_vasp_label(path, reference["sha256"], contract_sha256=payload["contract_sha256"],
                                       compatibility_sha256=payload["compatibility_sha256"])
        _, scheduler = _load_bound(report["scheduler_evidence"], name="label scheduler evidence")
        identity = f"{scheduler['server_alias']}/{scheduler['scheduler']}/{scheduler['job_id']}"
        return {"label": {"energy_eV": report["dft_toten_eV_force_label_only"], "forces_eV_per_A": report["forces_eV_per_A"],
                          "calculation_id": identity, "reaction_id": report["reaction_id"],
                          "structure_sha256": report["structure"]["sha256"]}}
    rows = payload.get("labels", payload.get("samples", []))
    ids = [required_text(row.get("sample_id"), "source sample id") for row in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("missing or duplicate label source identity")
    if payload.get("document_kind") == "dual_model_ts_vasp_force_label_set":
        _validate_label_set(path)
        return {
            str(row["sample_id"]): {
                "energy_eV": finite_number(row["vasp_energy_eV"], "source energy"),
                "forces_eV_per_A": row["vasp_forces_eV_per_A"],
                "calculation_id": calculation_identity(row),
                "structure_sha256": row.get("structure_sha256"),
                "reaction_id": payload.get("reaction_id"),
            }
            for row in payload.get("labels", [])
        }
    if payload.get("calibration_id") and isinstance(payload.get("samples"), list):
        if any(row.get("normal_completion") is not True or row.get("ionic_converged") is not True for row in rows):
            raise ValueError("adsorption labels lack accepted convergence evidence")
        for row in rows:
            bindings = row.get("source_files")
            if not isinstance(bindings, list) or not bindings:
                raise ValueError("adsorption training label lacks source-file evidence")
            for binding in bindings:
                source = Path(required_text(binding.get("path"), "source file path"))
                if not source.is_absolute():
                    source = path.parent / source
                if not source.is_file() or sha256_file(source) != binding.get("sha256"):
                    raise ValueError("adsorption training source file binding failed")
            if row.get("type", "calculated_result") != "calculated_result":
                raise ValueError("prediction cannot become an adsorption training label")
        return {
            str(row["sample_id"]): {
                "energy_eV": finite_number(row["final_toten_eV"], "source energy"),
                "forces_eV_per_A": row["forces_eV_per_A"],
                "calculation_id": calculation_identity(row),
                "structure_sha256": row.get("structure_sha256"),
                "reaction_id": row.get("reaction_id"),
            }
            for row in payload["samples"]
        }
    raise ValueError("unsupported VASP label source")


def _hydrate_samples(
    samples: Iterable[dict[str, Any]],
    *,
    label_cache: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for source in samples:
        sample = dict(source)
        required_text(sample.get("sample_id"), "sample identity")
        sample["data_state"] = "PARSED"
        structure_ref = dict(sample.get("structure", {}))
        structure_path = Path(str(structure_ref.get("path", ""))).resolve()
        if (
            not structure_path.is_file()
            or sha256_file(structure_path) != structure_ref.get("sha256")
        ):
            raise ValueError(f"training structure binding failed: {sample.get('sample_id')}")
        structure = read_poscar(structure_path)
        if geometry_fingerprint(structure) != structure_ref.get("geometry_sha256"):
            raise ValueError(f"training geometry binding failed: {sample.get('sample_id')}")
        if len(structure.labels) != int(structure_ref.get("atom_count", -1)):
            raise ValueError(f"training atom count failed: {sample.get('sample_id')}")

        label_ref = sample.get("label_source")
        if not isinstance(label_ref, dict):
            raise ValueError("sample lacks a label-source binding")
        source_key = f"{label_ref.get('path')}::{label_ref.get('sha256')}"
        if source_key not in label_cache:
            label_cache[source_key] = _source_labels(label_ref)
        label = label_cache[source_key].get(str(sample.get("source_sample_id", "")))
        if not isinstance(label, dict):
            raise ValueError(f"VASP label row missing: {sample.get('sample_id')}")
        calculation_id = required_text(label.get("calculation_id"), "label calculation identity")
        if sample.get("calculation_id") != calculation_id or label.get("structure_sha256") != structure_ref.get("sha256"):
            raise ValueError("label calculation/structure identity mismatch")
        if sample.get("reaction_id") != label.get("reaction_id"):
            raise ValueError("label reaction identity mismatch")
        forces = np.asarray(finite_array(label["forces_eV_per_A"], "VASP forces", shape=(len(structure.labels), 3)))
        energy = finite_number(label["energy_eV"], "VASP energy")
        if not math.isclose(
            energy,
            finite_number(sample["vasp_label"]["energy_eV"], "bound energy"),
            abs_tol=1.0e-8,
            rel_tol=0.0,
        ):
            raise ValueError(f"VASP energy binding failed: {sample.get('sample_id')}")
        sample["structure_path"] = str(structure_path)
        sample["reference_energy_eV"] = energy
        sample["reference_forces_eV_per_A"] = forces.tolist()
        sample["data_state"] = "VALIDATED"
        sample["validation_evidence"] = {"source": dict(label_ref), "source_sample_id": sample["source_sample_id"],
                                         "calculation_id": calculation_id, "structure_sha256": structure_ref["sha256"]}
        hydrated.append(sample)
    return hydrated

