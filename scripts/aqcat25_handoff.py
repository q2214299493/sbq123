#!/usr/bin/env python3
"""Validate versioned work/AQCat25 handoffs and their bound files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

try:
    from scripts.artifact_io import load_json_object, sha256_file, sha256_text
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from artifact_io import load_json_object, sha256_file, sha256_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "configs" / "aqcat25_handoff.schema.json"


class HandoffValidationError(ValueError):
    """Raised when schema-valid data is not bound to the declared files."""


def atom_order_sha256(symbols: list[str]) -> str:
    return sha256_text("\n".join(symbols) + "\n")


def _read_poscar_info(path: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 8:
        raise HandoffValidationError(f"incomplete POSCAR: {path}")
    symbols = lines[5].split()
    counts = [int(value) for value in lines[6].split()]
    if len(symbols) != len(counts):
        raise HandoffValidationError(f"POSCAR symbol/count mismatch: {path}")
    expanded = [symbol for symbol, count in zip(symbols, counts, strict=True) for _ in range(count)]
    selective = lines[7].strip().lower().startswith("s")
    mode_index = 8 if selective else 7
    start = mode_index + 1
    if len(lines) < start + len(expanded):
        raise HandoffValidationError(f"POSCAR coordinate count mismatch: {path}")
    flags = []
    for index in range(len(expanded)):
        fields = lines[start + index].split()
        flags.append(tuple(fields[3:6]) if selective else ("T", "T", "T"))
    return expanded, flags


def _resolve_file(base: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise HandoffValidationError(f"handoff file path must be relative: {relative}")
    resolved_base = base.resolve()
    resolved = (resolved_base / path).resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise HandoffValidationError(f"handoff file escapes its root: {relative}")
    if not resolved.is_file():
        raise HandoffValidationError(f"handoff file does not exist: {relative}")
    return resolved


def _validate_structure_ref(ref: dict[str, Any], base: Path) -> tuple[Path, list[str], list[tuple[str, str, str]]]:
    path = _resolve_file(base, ref["path"])
    actual_sha256 = sha256_file(path)
    if actual_sha256 != ref["sha256"]:
        raise HandoffValidationError(f"SHA256 mismatch for {ref['path']}: {actual_sha256}")
    symbols, flags = _read_poscar_info(path)
    if len(symbols) != ref["atom_count"]:
        raise HandoffValidationError(f"atom_count mismatch for {ref['path']}")
    if atom_order_sha256(symbols) != ref["atom_order_sha256"]:
        raise HandoffValidationError(f"atom_order_sha256 mismatch for {ref['path']}")
    return path, symbols, flags


def _validate_indices(indices: list[int], atom_count: int, label: str) -> None:
    if any(index > atom_count for index in indices):
        raise HandoffValidationError(f"{label} contains an index larger than atom_count={atom_count}")


def _validate_work_to_gpu(document: dict[str, Any], base: Path) -> None:
    _, symbols, flags = _validate_structure_ref(document["candidate_structure"], base)
    atom_count = len(symbols)
    fixed_declared = sorted(document["selective_dynamics"]["fixed_atom_indices_1based"])
    fixed_actual = sorted(
        index
        for index, atom_flags in enumerate(flags, start=1)
        if tuple(value.upper() for value in atom_flags) == ("F", "F", "F")
    )
    if fixed_declared != fixed_actual:
        raise HandoffValidationError(
            f"Selective Dynamics mismatch: manifest={fixed_declared}, POSCAR={fixed_actual}"
        )
    if document["selective_dynamics"]["free_atom_count"] != atom_count - len(fixed_actual):
        raise HandoffValidationError("free_atom_count does not match the candidate POSCAR")

    if document["workflow_kind"] == "adsorption":
        adsorption = document["adsorption"]
        atoms = adsorption["adsorbate_atoms"]
        indices = [item["index_1based"] for item in atoms]
        _validate_indices(indices, atom_count, "adsorbate_atoms")
        if len(indices) != len(set(indices)):
            raise HandoffValidationError("adsorbate atom indices must be unique")
        for item in atoms:
            actual = symbols[item["index_1based"] - 1]
            if actual != item["symbol"]:
                raise HandoffValidationError(
                    f"adsorbate symbol mismatch at atom {item['index_1based']}: manifest={item['symbol']}, POSCAR={actual}"
                )
        for key in ("connectivity_constraints", "monitored_pairs"):
            for pair in adsorption[key]:
                _validate_indices(pair["atoms_1based"], atom_count, f"adsorption.{key}")
    else:
        transition_state = document["transition_state"]
        structure_refs = [
            transition_state["initial_structure"],
            *transition_state["waypoint_structures"],
            transition_state["final_structure"],
        ]
        for ref in structure_refs:
            _, state_symbols, state_flags = _validate_structure_ref(ref, base)
            if state_symbols != symbols:
                raise HandoffValidationError("TS endpoint/waypoint atom order differs from candidate_structure")
            if state_flags != flags:
                raise HandoffValidationError("TS endpoint/waypoint Selective Dynamics differs from candidate_structure")
        for change in transition_state["indexed_bond_changes"]:
            _validate_indices(change["atoms_1based"], atom_count, "transition_state.indexed_bond_changes")


def _validate_gpu_to_work(document: dict[str, Any], base: Path) -> None:
    source_ref = document["source_handoff"]
    source_path = _resolve_file(base, source_ref["path"])
    if sha256_file(source_path) != source_ref["sha256"]:
        raise HandoffValidationError("source handoff SHA256 mismatch")
    source_document = load_json_object(source_path)
    for key in ("handoff_id", "workflow_kind", "source_workflow_sha256"):
        if source_document.get(key) != document[key]:
            raise HandoffValidationError(f"source handoff disagrees on {key}")
    if document["workflow_kind"] == "transition_state" and source_document.get("transition_state") != document.get(
        "transition_state"
    ):
        raise HandoffValidationError("source handoff disagrees on transition_state")
    _, candidate_symbols, candidate_flags = _validate_structure_ref(document["candidate_structure"], base)
    if document["workflow_kind"] == "transition_state":
        transition_state = document["transition_state"]
        _, initial_symbols, initial_flags = _validate_structure_ref(transition_state["initial_structure"], base)
        if candidate_symbols != initial_symbols:
            raise HandoffValidationError("returned TS candidate atom order differs from initial_structure")
        if candidate_flags != initial_flags:
            raise HandoffValidationError("returned TS candidate Selective Dynamics differs from initial_structure")
    exit_ref = document["producer_exit_record"]
    exit_path = _resolve_file(base, exit_ref["path"])
    if sha256_file(exit_path) != exit_ref["sha256"]:
        raise HandoffValidationError("producer exit-record SHA256 mismatch")
    exit_document = load_json_object(exit_path)
    expected_status = "success" if exit_ref["exit_code"] == 0 else "failed"
    if exit_ref["status"] != expected_status:
        raise HandoffValidationError("producer exit status and exit code disagree")
    for key in ("gpu_job_id", "exit_code"):
        expected = document["producer"]["gpu_job_id"] if key == "gpu_job_id" else exit_ref["exit_code"]
        if exit_document.get(key) != expected:
            raise HandoffValidationError(f"producer exit record disagrees on {key}")

    expected_class = (
        "predicted_adsorption_candidate_only"
        if document["workflow_kind"] == "adsorption"
        else "predicted_transition_state_candidate_only"
    )
    if document["result"]["result_class"] != expected_class:
        raise HandoffValidationError("result_class does not match workflow_kind")


def validate_handoff(
    manifest_path: Path,
    *,
    root: Path | None = None,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    document = load_json_object(manifest_path)
    schema = load_json_object(schema_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in errors
        )
        raise HandoffValidationError(details)
    base = manifest_path.parent if root is None else root
    if document["direction"] == "work_to_gpu":
        _validate_work_to_gpu(document, base)
    else:
        _validate_gpu_to_work(document, base)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()
    document = validate_handoff(args.manifest, root=args.root, schema_path=args.schema)
    print(json.dumps({"valid": True, "direction": document["direction"], "handoff_id": document["handoff_id"]}))


if __name__ == "__main__":
    main()
