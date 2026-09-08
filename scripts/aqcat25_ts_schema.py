#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

try:
    from scripts.artifact_io import load_json_object
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from artifact_io import load_json_object


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "configs" / "aqcat25_ts_active_learning.schema.json"
KNOWN_DOCUMENT_KINDS = {
    "aqcat25_ts_active_learning_state",
    "scheduler_job_evidence",
    "aqcat25_ts_force_prediction_request",
    "aqcat25_ts_force_prediction",
    "vasp_ts_force_label",
    "aqcat25_ts_independent_validation_set",
    "aqcat25_ts_domain_assessment",
    "aqcat25_ts_domain_calibration_review",
    "aqcat25_ts_domain_reuse_context",
    "aqcat25_ts_force_only_training_manifest",
    "aqcat25_ts_force_only_finetune_result",
}


def _schema_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    if DEFAULT_SCHEMA.is_file():
        return DEFAULT_SCHEMA
    sibling = Path(__file__).with_name("aqcat25_ts_active_learning.schema.json")
    if sibling.is_file():
        return sibling
    raise FileNotFoundError("AQCat25 TS active-learning schema is unavailable")


def validate_document(
    document: dict[str, Any], *, expected_kind: str | None = None, schema_path: Path | None = None
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("active-learning document must be a JSON object")
    if expected_kind and document.get("document_kind") != expected_kind:
        raise ValueError(f"expected {expected_kind}, got {document.get('document_kind')}")
    schema = load_json_object(_schema_path(schema_path))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: [str(value) for value in error.absolute_path],
    )
    if errors:
        messages = []
        for error in errors[:8]:
            location = ".".join(str(value) for value in error.absolute_path) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValueError("active-learning schema validation failed: " + "; ".join(messages))
    return document


def load_document(
    path: Path, *, expected_kind: str | None = None, schema_path: Path | None = None
) -> dict[str, Any]:
    payload = load_json_object(path)
    return validate_document(payload, expected_kind=expected_kind, schema_path=schema_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an AQCat25 TS active-learning JSON document.")
    parser.add_argument("document", type=Path)
    parser.add_argument("--kind", choices=sorted(KNOWN_DOCUMENT_KINDS))
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()
    payload = load_document(args.document, expected_kind=args.kind, schema_path=args.schema)
    print(f"VALID {payload['document_kind']}")


if __name__ == "__main__":
    main()
