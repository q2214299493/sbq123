#!/usr/bin/env python3
"""Validate normalized catalysis records against the project source whitelist."""

from __future__ import annotations

from scripts.runtime_resources import resource_path

from pathlib import Path
from urllib.parse import urlparse

import yaml

from scripts.jsonl_io import read_jsonl_objects
from scripts.adsmind_lite.evidence_lifecycle import (
    STATES, assess_evidence, record_subject, required_text, timestamp,
)
from scripts.scientific_validation import finite_array, integer_number


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills/catalysis-data-retrieval"
DEFAULT_SOURCES = resource_path("skills/catalysis-data-retrieval/references/sources.yaml")
REQUIRED_FIELDS = ("id", "source_id", "source_url", "source_access_verified", "title", "summary", "retrieved_at", "data_types")


def load_source_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("sources.yaml must contain a sources list")
    return payload


def source_map(config: dict) -> dict[str, dict]:
    return {str(item["id"]): item for item in config["sources"]}


def url_allowed(url: str, source: dict) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if parsed.scheme not in {"http", "https"}:
        return False
    return any(host == str(rule["host"]).lower() and path.startswith(str(rule.get("path_prefix", "/"))) for rule in source.get("allow", []))


def _artifact_url_errors(record: dict, source: dict) -> list[str]:
    artifact_urls = record.get("artifact_urls", [])
    if not isinstance(artifact_urls, list):
        return ["artifact_urls_not_list"]
    return [f"artifact_url_not_allowed:{index}" for index, url in enumerate(artifact_urls) if not url_allowed(str(url), source)]


def _embedding_errors(record: dict) -> list[str]:
    embedding = record.get("embedding")
    if embedding is None:
        return []
    try:
        validate_embedding(record)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"embedding_invalid:{exc}"]
    return []


def validate_embedding(record: dict) -> list[float]:
    metadata = record["embedding_provenance"]
    required_text(metadata["model"], "embedding.model")
    timestamp(metadata["generated_at"], "embedding.generated_at")
    dimension = integer_number(metadata["dimension"], "embedding.dimension", positive=True)
    vector = finite_array(record["embedding"], "embedding", shape=(dimension,))
    if not any(vector):
        raise ValueError("embedding has zero norm")
    if metadata["record_sha256"] != record_subject(record):
        raise ValueError("embedding record binding mismatch")
    evidence = record["evidence"]
    if STATES.index(assess_evidence(evidence)["state"]) < STATES.index("CONTENT_BOUND"):
        raise ValueError("embedding lacks available content-bound source")
    if evidence["claim"].get("record_sha256") != record_subject(record):
        raise ValueError("source does not bind this record")
    if metadata["content_sha256"] != evidence["content"]["sha256"]:
        raise ValueError("embedding source content mismatch")
    return vector


def validate_record(record: dict, sources: dict[str, dict]) -> list[str]:
    errors = [f"missing:{field}" for field in REQUIRED_FIELDS if field not in record]
    try:
        for field in ("id", "source_id", "source_url", "title", "summary"):
            required_text(record.get(field), field)
        timestamp(record.get("retrieved_at"), "retrieved_at")
    except ValueError as exc:
        errors.append(str(exc))
    source_id = str(record.get("source_id", ""))
    source = sources.get(source_id)
    if source is None:
        errors.append(f"unknown_source:{source_id}")
        return errors
    if not url_allowed(str(record.get("source_url", "")), source):
        errors.append("source_url_not_allowed")
    if not isinstance(record.get("source_access_verified"), bool):
        errors.append("source_access_verified_not_boolean")
    errors.extend(_artifact_url_errors(record, source))
    if not isinstance(record.get("data_types", []), list):
        errors.append("data_types_not_list")
    errors.extend(_embedding_errors(record))
    return errors


def load_jsonl(path: Path) -> list[dict]:
    return read_jsonl_objects(path, lambda _path, line_number: f"line {line_number} is not a JSON object")


def validate_records(records: list[dict], config: dict) -> list[dict]:
    sources = source_map(config)
    failures = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        errors = validate_record(record, sources)
        record_id = str(record.get("id", ""))
        if record_id in seen:
            errors.append("duplicate_id")
        seen.add(record_id)
        if errors:
            failures.append({"line": index, "id": record_id, "errors": errors})
    return failures
