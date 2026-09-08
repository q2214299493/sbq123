from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml
from ase import Atoms
from ase.io import read as ase_read

from scripts.artifact_io import load_json_object as _load_json_object
from scripts.artifact_io import write_json as _write_json
from scripts.jsonl_io import read_jsonl_objects

SITE_CLASS_MAP = {
    "top": "top_Fe",
    "short_bridge": "bridge_FeFe_short",
    "long_bridge": "bridge_FeFe_long",
    "hollow": "hollow_FeFeFe",
}
COMPACT_COLUMNS = (
    "adsorbate",
    "planned_site_class",
    "relaxed_site_class",
    "chemical_slip",
    "dissociated",
    "duplicate",
    "recommend_for_vasp",
    "confidence_level",
    "needs_review",
    "reason_code",
)


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def load_yaml_schema(path: str | Path, required_keys: Iterable[str], error: str) -> dict[str, Any]:
    payload = load_yaml(path)
    if not set(required_keys) <= payload.keys():
        raise ValueError(error)
    return payload


def write_json(path: Path, payload: Any) -> None:
    _write_json(path, payload)


def read_json(path: Path) -> dict[str, Any]:
    return _load_json_object(path)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl_objects(path)


def compact_table(records: list[dict[str, Any]]) -> str:
    if not records:
        return "records=0"
    rows = [[str(record.get(column, "-")) for column in COMPACT_COLUMNS] for record in records]
    widths = [max(len(column), *(len(row[index]) for row in rows)) for index, column in enumerate(COMPACT_COLUMNS)]
    header = " ".join(column.ljust(widths[index]) for index, column in enumerate(COMPACT_COLUMNS))
    body = [" ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows]
    return "\n".join([header, *body])


def require_ase_structure(path: Path) -> Atoms:
    atoms = ase_read(path, format="vasp")
    if not isinstance(atoms, Atoms):
        raise ValueError(f"{path}: ASE did not return one structure")
    return atoms


def surface_family_config(path: Path, family: str) -> dict[str, Any]:
    families = load_yaml(path).get("surface_families", {})
    if family not in families:
        raise ValueError(f"unsupported surface family: {family}")
    return families[family]


def standardized_site_id(surface_name: str, site_class: str, pattern: str, serial: int) -> str:
    return f"{surface_name}__{site_class}__{pattern}__{serial:04d}"
