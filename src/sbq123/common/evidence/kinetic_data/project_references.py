"""Resolve named research evidence relative to its declared base, without writes."""
from pathlib import Path, PureWindowsPath

import yaml

from sbq123.common.artifacts.artifact_io import require_sha256, sha256_bytes, sha256_file
from sbq123.common.workflow.multiphase_contracts import decode_unique_json
from sbq123.common.validation.scientific_validation import validate_finite_tree


class _ManifestLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = super().construct_mapping(node, deep)
        if len(result) != len(node.value):
            raise ValueError("Ambiguous duplicate YAML field or artifact role")
        return result


def manifest(path):
    try:
        data = yaml.load(path.read_bytes(), Loader=_ManifestLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path.name}")
    return data


# Version discriminators come from the domain documents. Unversioned native
# records are usable only through their specific plan/graph/receipt bindings.
FORMATS = {
    "network": ("reaction-network/1", "network-definition/1"),
    "dataset": ("kinetic-dataset/1",),
    "rates": ("kinetic-rate-output/2",),
    "mkm_receipt": ("mkm-single-point-plan/1",),
    "result": ("mkm-single-point-result/1",),
    "drc": ("bounded-drc-batch/1",),
    "drc_plan": ("bounded-drc-plan/1",),
    "observation": ("mkm-coverage-observations/1",),
    "kmc_plan": ("zacros-zero-event-execution-plan/1",),
}
JSON_ROLES = set(FORMATS) | {
    "intake", "configuration", "kmc_configuration", "graph", "kmc_validation",
    "candidate_manifest", "original_manifest", "kmc_receipt", "qualification", "catalog", "ts_review", "models",
}


class UnsupportedFormat(ValueError):
    pass


def _read_document(raw, role, project_id, version, reaction_id):
    doc = decode_unique_json(raw)
    if not isinstance(doc, dict):
        raise ValueError("Expected a JSON object")
    validate_finite_tree(doc)
    if role == "catalog":
        if not (doc.get("format") == "network-definition/1" and "schema_version" not in doc
                or "format" not in doc and doc.get("schema_version") == "1.0.0"):
            raise UnsupportedFormat("Unsupported catalyst catalog format or version")
        return doc
    versions = {"intake": 1, "rates": "2.1.0"}
    if (role in FORMATS and doc.get("format") not in FORMATS[role]
            or role not in FORMATS and "format" in doc
            or doc.get("schema_version") != versions.get(role)
            or isinstance(doc.get("schema_version"), bool)):
        raise UnsupportedFormat("Unsupported artifact format or version")
    for field in ("project_id", "catalyst_project_id"):
        if field in doc and doc[field] != project_id:
            raise ValueError("Cross-project artifact")
    for field in ("network_version", "network_version_id"):
        if version and field in doc and doc[field] != version:
            raise ValueError("Wrong network version")
    if reaction_id and "reaction_id" in doc and doc["reaction_id"] != reaction_id:
        raise ValueError("Wrong reaction identity")
    return doc


def resolve_sources(base, groups, project_id, version, reaction_id):
    inventory, documents, paths = {}, {}, {}
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("sources must map role names to references")
        for role, ref in group.items():
            if not isinstance(role, str) or not role:
                raise ValueError("A source role must be a nonempty name")
            if role in inventory:
                inventory[role].update(status="invalid_reference", reason="Ambiguous artifact role")
                documents.pop(role, None)
                paths.pop(role, None)
                continue
            row = inventory[role] = {"reference": ref, "status": "invalid_reference"}
            try:
                if base is None or not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
                    raise ValueError("Named references require evidence_base, path and sha256")
                original = ref["path"]
                relative = Path(original)
                if not original or PureWindowsPath(original).anchor or relative.is_absolute():
                    raise ValueError("Expected a relative artifact path")
                path = (base / relative).resolve()
                if not path.is_relative_to(base):
                    raise ValueError("Path outside evidence base")
                expected = require_sha256(ref.get("sha256"), label=role)
                if not path.is_file():
                    row.update(status="missing_local_file", reason="Referenced file is unavailable")
                    continue
                raw = path.read_bytes() if role in JSON_ROLES else None
                actual = sha256_bytes(raw) if raw is not None else sha256_file(path)
                row["actual_sha256"] = actual
                if expected != actual:
                    row.update(status="hash_mismatch", reason="Artifact bytes differ from reference")
                    continue
                if raw is not None:
                    doc = _read_document(raw, role, project_id, version, reaction_id)
                    documents[role] = doc
                paths[role] = path
                row.update(status="verified")
            except UnsupportedFormat as exc:
                row.update(status="unsupported_format", reason=str(exc))
            except (ValueError, OSError, RuntimeError) as exc:
                row["reason"] = str(exc)
    return inventory, documents, paths
