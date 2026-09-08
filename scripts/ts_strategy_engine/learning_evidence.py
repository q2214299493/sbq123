"""File and JSON-observation checks shared by strategy learning and retry preflight."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_json


def exact_keys(value: dict[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - optional:
        raise ValueError(f"expected fields {sorted(required)}, optional {sorted(optional)}")


def bind_files(files: dict[str, str]) -> dict[str, dict[str, str]]:
    if not isinstance(files, dict) or not files:
        raise ValueError("at least one named evidence file is required")
    result = {}
    for role, value in files.items():
        if not isinstance(role, str) or not role.strip() or not isinstance(value, str) or not value:
            raise ValueError("file roles and paths must be nonempty strings")
        path = Path(value).resolve()
        if not path.is_file():
            raise ValueError(f"missing source file: {path}")
        result[role] = {"path": str(path), "sha256": sha256_file(path)}
    return result


def validate_files(files: dict[str, dict[str, str]]) -> None:
    for reference in files.values():
        exact_keys(reference, {"path", "sha256"})
        path = Path(reference["path"])
        if not path.is_file() or sha256_file(path) != reference["sha256"]:
            raise ValueError(f"missing or stale evidence: {path}")


def input_key(kind: str, files: dict[str, str]) -> str:
    # Directory names, attempt IDs and strategy labels cannot bypass a retry check.
    return sha256_json({"kind": kind, "files": files})


def vasp_input_hashes(manifest: dict[str, str]) -> dict[str, str]:
    names = {"INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "POSCAR", "MODECAR"}
    return {name: digest for name, digest in manifest.items() if name in names or name.endswith("/POSCAR")}


VASP_KINDS = {"ordinary_neb", "ci_neb", "neb_pilot", "diagnostic_static", "dimer", "vfa", "connectivity_relax"}
ATTEMPT_KINDS = VASP_KINDS | {"matris_ml_neb", "aqcat25_ml_neb", "aqcat25_ba_sella", "matris_ml_neb_sella"}


def attempt_input_hashes(kind: str, inputs: dict[str, dict[str, str]]) -> dict[str, str]:
    hashes = {name: reference["sha256"] for name, reference in inputs.items()}
    if kind not in VASP_KINDS:
        if kind not in ATTEMPT_KINDS:
            raise ValueError(f"unsupported attempt kind: {kind}")
        return hashes
    from scripts.vasp_result_gate import read_incar_values
    required = {"INCAR", "KPOINTS", "POTCAR.spec", "script.lsf"}
    if not required <= hashes.keys():
        raise ValueError("VASP attempt requires a complete input manifest; use start-vasp")
    if kind in {"ordinary_neb", "ci_neb", "neb_pilot"}:
        images = int(read_incar_values(Path(inputs["INCAR"]["path"]))["IMAGES"])
        required.update(f"{i:02d}/POSCAR" for i in range(images + 2))
    else:
        required.add("POSCAR")
    if kind == "dimer":
        required.add("MODECAR")
    if not required <= hashes.keys():
        raise ValueError("VASP attempt is missing structures or modes")
    return vasp_input_hashes(hashes)


def observe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check explicit observations, never infer a root cause or a TS from text."""
    if not isinstance(items, list) or not items:
        raise ValueError("nonempty JSON observations are required")
    for item in items:
        exact_keys(item, {"path", "sha256", "pointer", "value"})
        validate_files({"observation": {k: item[k] for k in ("path", "sha256")}})
        value: Any = load_json_object(Path(item["path"]))
        pointer = item["pointer"]
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("observation pointer must be a nonempty JSON pointer")
        try:
            for token in pointer[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"observation pointer does not exist: {pointer}") from exc
        if type(value) is not type(item["value"]) or value != item["value"]:
            raise ValueError(f"observation differs from source: {pointer}")
    return items


def validate_costs(costs: dict[str, Any], observations: list[dict[str, Any]]) -> None:
    exact_keys(costs, set(), {"vasp_core_hours", "gpu_hours", "force_calls"})
    for name, value in costs.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid cost: {name}")
        if not any(item["pointer"].endswith("/" + name) and item["value"] == value for item in observations):
            raise ValueError(f"cost lacks a matching source observation: {name}")
