#!/usr/bin/env python3
"""Validate a completed dual-model TS VASP force-label batch."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.aqcat25_calibration import parse_final_outcar, parse_poscar_symbols
from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.execution_backends import load_execution_backends
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.scheduler_evidence import query_lsf_job
from scripts.vasp_result_gate import final_scf_status, read_incar_values


SAMPLE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
REMOTE_FILES = ("POSCAR", "INCAR", "KPOINTS", "POTCAR", "OUTCAR", "OSZICAR", "CONTCAR", "vasp.out")


def _canonical_incar(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    upper = text.upper().strip(".")
    if upper in {"TRUE", "T"}:
        return True
    if upper in {"FALSE", "F"}:
        return False
    try:
        return float(text)
    except ValueError:
        return upper


def _remote_hashes(server: str, remote_parent: str, sample_id: str) -> dict[str, str]:
    if not SAMPLE_ID.fullmatch(sample_id):
        raise ValueError(f"unsafe sample id: {sample_id}")
    if not remote_parent.startswith("~/sbq/") or any(char.isspace() for char in remote_parent):
        raise ValueError("remote parent is outside the approved path or contains whitespace")
    paths = [f"{remote_parent}/{sample_id}/{name}" for name in REMOTE_FILES]
    completed = subprocess.run(
        ["ssh", server, "sha256sum", *paths],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"remote hash query failed for {sample_id}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    rows: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        rows[Path(fields[-1]).name] = fields[0]
    if set(rows) != set(REMOTE_FILES):
        raise ValueError(f"incomplete remote hashes for {sample_id}")
    return rows


def _validate_incar(actual: dict[str, str], requested: dict[str, Any], sample_id: str) -> None:
    mismatches = []
    for key, expected in requested.items():
        if key not in actual or _canonical_incar(actual[key]) != _canonical_incar(expected):
            mismatches.append(key)
    if mismatches:
        raise ValueError(f"INCAR mismatch for {sample_id}: {', '.join(mismatches)}")


def _kpoint_mesh(path: Path) -> list[int]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 4:
        raise ValueError(f"invalid KPOINTS: {path}")
    return [int(value) for value in lines[3].split()[:3]]


def collect(  # noqa: C901 - collection is a linear evidence gate.
    state_path: Path,
    batch_path: Path,
    submission_path: Path,
    root: Path,
    evidence_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise FileExistsError(f"scheduler evidence directory is not empty: {evidence_dir}")
    state = load_json_object(state_path)
    batch = load_json_object(batch_path)
    submission = load_json_object(submission_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    if batch.get("document_kind") not in {
        "dual_model_ts_vasp_force_label_batch_request",
        "dual_model_ts_heldout_vasp_force_label_batch_request",
    }:
        raise ValueError("invalid VASP force-label batch request")
    if submission.get("document_kind") != "dual_model_ts_vasp_force_label_batch_submission_summary":
        raise ValueError("invalid VASP force-label submission summary")
    batch_sha = sha256_file(batch_path)
    if submission.get("batch_request_sha256") != batch_sha:
        raise ValueError("submission summary is not bound to the batch request")
    if batch.get("reaction_id") != state.get("reaction_id"):
        raise ValueError("reaction id mismatch")

    selected = {str(row["sample_id"]): row for row in state.get("selected_vasp_labels", [])}
    requested = {str(row["sample_id"]): row for row in batch.get("labels", [])}
    jobs = {str(row["sample_id"]): row for row in submission.get("jobs", [])}
    if not selected or set(selected) != set(requested) or set(selected) != set(jobs):
        raise ValueError("state, request, and submission sample sets differ")

    backend = load_execution_backends().vasp
    if submission.get("backend") != backend.server_alias or submission.get("scheduler") != backend.name:
        raise ValueError("submission backend conflicts with execution_backends.yaml")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    labels: list[dict[str, Any]] = []
    atoms_per_label: set[int] = set()
    for sample_id in requested:
        directory = root / sample_id
        request_path = directory / "label_request.json"
        request = load_json_object(request_path)
        if sha256_file(request_path) != requested[sample_id]["label_request_sha256"]:
            raise ValueError(f"label request hash mismatch: {sample_id}")
        if sha256_file(directory / "POSCAR") != selected[sample_id]["structure_sha256"]:
            raise ValueError(f"exact-structure hash mismatch: {sample_id}")
        symbols = parse_poscar_symbols(directory / "POSCAR")
        atoms_per_label.add(len(symbols))
        if len(symbols) != 50:
            raise ValueError(f"expected 50 atoms for {sample_id}, found {len(symbols)}")

        remote_hashes = _remote_hashes(backend.server_alias, submission["remote_parent"], sample_id)
        for name in ("POSCAR", "INCAR", "KPOINTS", "OUTCAR", "OSZICAR", "CONTCAR", "vasp.out"):
            if sha256_file(directory / name) != remote_hashes[name]:
                raise ValueError(f"remote/local hash mismatch for {sample_id}/{name}")
        if remote_hashes["POTCAR"] != submission["potcar"]["sha256"]:
            raise ValueError(f"POTCAR hash mismatch: {sample_id}")

        incar = read_incar_values(directory / "INCAR")
        _validate_incar(incar, request["input_profile"]["incar"], sample_id)
        if _kpoint_mesh(directory / "KPOINTS") != request["input_profile"]["gamma_mesh"]:
            raise ValueError(f"KPOINTS mesh mismatch: {sample_id}")

        scheduler = query_lsf_job(jobs[sample_id]["job_id"], stage="vasp_force_label")
        if scheduler["status"] != "DONE":
            raise ValueError(f"scheduler status is not DONE: {sample_id}")
        evidence_path = evidence_dir / f"{sample_id}_job{jobs[sample_id]['job_id']}_DONE.json"
        write_json_atomic(evidence_path, scheduler, ensure_ascii=True)

        parsed = parse_final_outcar(directory / "OUTCAR")
        outcar = parse_outcar(directory / "OUTCAR")
        scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
        forces = parsed["forces_eV_per_A"]
        if not parsed["normal_completion"] or outcar["fatal_keywords"]:
            raise ValueError(f"VASP normal-completion gate failed: {sample_id}")
        if not scf["electronically_converged"]:
            raise ValueError(f"electronic convergence failed: {sample_id}")
        if len(forces) != len(symbols) or not all(len(row) == 3 for row in forces):
            raise ValueError(f"incomplete force block: {sample_id}")
        if not all(math.isfinite(value) for row in forces for value in row):
            raise ValueError(f"non-finite force data: {sample_id}")
        total_mag = outcar["total_magnetization_history_muB"]
        local_mag = outcar["local_magnetization_last_muB"]
        if not total_mag or len(local_mag) != len(symbols):
            raise ValueError(f"incomplete magnetic evidence: {sample_id}")

        labels.append(
            {
                "sample_id": sample_id,
                "image": request.get("image"),
                "role": request["role"],
                "job_id": jobs[sample_id]["job_id"],
                "structure_sha256": sha256_file(directory / "POSCAR"),
                "vasp_energy_eV": parsed["final_toten_eV"],
                "energy_class": "force_label_only_not_reportable_final_energy",
                "vasp_forces_eV_per_A": forces,
                "maximum_atomic_force_eV_per_A": max(
                    math.sqrt(sum(component * component for component in row)) for row in forces
                ),
                "total_magnetic_moment_muB": total_mag[-1],
                "atom_resolved_magnetic_moments_muB": local_mag,
                "electronic_status": scf,
                "scheduler_evidence": {
                    "path": str(evidence_path.resolve()),
                    "sha256": sha256_file(evidence_path),
                },
                "input_output_hashes": {
                    name: remote_hashes[name] for name in REMOTE_FILES
                },
                "acceptance_evidence": {
                    "scheduler_DONE": True,
                    "normal_vasp_completion": True,
                    "electronically_converged": True,
                    "complete_atom_aligned_force_block": True,
                    "total_magnetic_moment_available": True,
                    "atom_resolved_magnetic_moments_available": True,
                    "sigma_0p20_compatibility": True,
                    "remote_to_local_output_hashes_match": True,
                },
            }
        )

    result = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_vasp_force_label_set",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "source_batch_path": str(batch_path.resolve()),
        "source_batch_sha256": batch_sha,
        "source_submission_sha256": sha256_file(submission_path),
        "compatibility": {
            "final_energy_convention": "fe110_converged_toten_sigma0p20_v1",
            "ISMEAR": 1,
            "SIGMA_eV": 0.2,
            "reportable_final_energy": False,
        },
        "checks": {
            "all_scheduler_DONE": True,
            "all_normal_vasp_completion": True,
            "all_electronically_converged": True,
            "all_exact_structure_hashes_match": True,
            "all_complete_force_blocks": True,
            "all_magnetic_evidence_complete": True,
            "all_remote_to_local_hashes_match": True,
            "atoms_per_label": sorted(atoms_per_label),
        },
        "labels": labels,
        "scientific_status": "accepted_force_labels_only",
        "reportable_final_energy": False,
        "barrier_or_TS_claim": False,
    }
    write_json_atomic(output_path, result, ensure_ascii=True)
    state["vasp_label_batch"] = {
        "path": str(batch_path.resolve()),
        "sha256": batch_sha,
        "completed_label_set_path": str(output_path.resolve()),
        "completed_label_set_sha256": sha256_file(output_path),
    }
    state["status"] = "awaiting_completed_VASP_force_labels"
    state["scientific_status"] = "VASP_force_labels_accepted_pending_error_assessment"
    write_json_atomic(state_path, state, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(
        args.state,
        args.batch,
        args.submission,
        args.root,
        args.evidence_dir,
        args.output,
    )
    print(
        json.dumps(
            {
                "labels": len(result["labels"]),
                "status": result["scientific_status"],
                "reportable_final_energy": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
