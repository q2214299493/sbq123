"""Configuration is selected by ID from the installed release, never from a request path."""

from hashlib import sha256
from importlib.resources import files
import json

from sbq123.common.evidence.trust import TRUST_SHA256, SCHEMAS_SHA256
from jsonschema import Draft202012Validator
from functools import lru_cache
from copy import deepcopy
from sbq123.common.kinetic_model.contracts import identity

FIELDS = {
    "engine_families": {"role", "native", "archived_engine_sha256"},
    "replay": {"path", "sha256", "scope"},
    "basis_conversions": {"model_sha256", "mol_sites_per_kg", "approval", "scope"},
    "catalysts": {"scope", "conversion_ids"},
    "analysis": {"mode", "yield_denominator", "selectivity_denominator"},
    "drc": {"target", "denominator", "perturbation", "scope"},
    "datasets": {"model", "sha256", "scope"},
}


def _document(name, expected):
    raw = files("sbq123.common").joinpath("registries", name + ".json").read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"Registry identity mismatch for {name}")
    return json.loads(raw)


@lru_cache(maxsize=16)
def _registry(kind):
    if kind not in FIELDS:
        raise ValueError("Unknown registry or selector")
    trust = _document("trust", TRUST_SHA256)
    if (
        set(trust) != {"schema_version", "registry_bytes"}
        or type(trust["schema_version"]) is not int
        or trust["schema_version"] != 1
        or trust["registry_bytes"].keys() != FIELDS.keys()
    ):
        raise ValueError("Invalid release trust index")
    doc = _document(kind, trust["registry_bytes"][kind])
    if (
        set(doc) != {"schema_version", "kind", "entries", "source", "content_sha256"}
        or doc["kind"] != kind
        or type(doc["schema_version"]) is not int
        or doc["schema_version"] != 1
        or not doc["source"]
        or not isinstance(doc["entries"], dict)
        or identity(doc["entries"]) != doc["content_sha256"]
    ):
        raise ValueError("Invalid configuration registry")
    schemas = _document("schemas", SCHEMAS_SHA256)
    validator = Draft202012Validator(schemas[kind])
    for identifier, row in doc["entries"].items():
        if not identifier or not isinstance(identifier, str):
            raise ValueError("Invalid registry identifier")
        errors = list(validator.iter_errors(row))
        if errors:
            raise ValueError(f"Invalid {kind} entry {identifier}: {errors[0].message}")
    return doc["entries"]


def entry(kind: str, key: str) -> dict:
    """Return an isolated copy of a release-verified registry entry."""
    if not isinstance(kind, str) or kind not in FIELDS or not isinstance(key, str):
        raise ValueError("Unknown registry or selector")
    if key not in _registry(kind):
        from .trust import project_document
        project = project_document(kind, key)
        if project is not None:
            record, _ = project
            if not isinstance(record, dict) or set(record) != FIELDS[kind]:
                raise ValueError("Invalid project registry entry")
            Draft202012Validator(_document("schemas", SCHEMAS_SHA256)[kind]).validate(record)
            return record
        raise ValueError("Unknown registry or selector")
    return deepcopy(_registry(kind)[key])
