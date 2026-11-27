"""Build explicit, source-bound diagnostic cases without reading the registry."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json, write_json

from .learning_evidence import exact_keys, observe
from .strategy_learning import POLICY, policy


SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 1_000_000
PROVENANCE = {"synthetic", "reviewed_real", "incomplete"}
ROOT_STATUSES = {"confirmed", "hypothesis", "unknown"}
PRIVATE_POINTER_TOKENS = {"answer", "diagnosis", "expected", "failure_class", "root_cause_status",
                          "next_review", "reviewer", "reference", "posthoc", "password",
                          "secret", "token", "credential", "api_key"}


def _source(item: dict[str, Any], root: Path, *, public: bool) -> dict[str, Any]:
    exact_keys(item, {"evidence_id", "path", "sha256", "pointer", "value"} if public
               else {"path", "sha256", "pointer", "value"})
    if public and (not isinstance(item["evidence_id"], str) or not item["evidence_id"].strip()):
        raise ValueError("evidence_id must be a nonempty string")
    if not isinstance(item["path"], str) or not item["path"]:
        raise ValueError("source path must be a nonempty string")
    path = (root / item["path"]).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".json" or not path.is_file():
        raise ValueError(f"source must be a JSON file inside the allowed root: {item['path']}")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("JSON source exceeds the small-snapshot limit")
    if require_sha256(item["sha256"], label="source sha256") != sha256_file(path):
        raise ValueError(f"source hash changed: {item['path']}")
    if public:
        if not isinstance(item["pointer"], str):
            raise ValueError("public evidence pointer must be a string")
        if isinstance(item["value"], (dict, list)):
            raise ValueError("public evidence must select one scalar value")
        tokens = item["pointer"].lower().split("/")
        if any(token in PRIVATE_POINTER_TOKENS for token in tokens):
            raise ValueError("public evidence selects a reference or post-hoc field")
    observation = {**item, "path": str(path)}
    if public:
        observation.pop("evidence_id")
    observe([observation])
    return {**item, "path": str(path)}


def _reference(reference: Any, provenance: str, selected: list[dict[str, Any]],
               root: Path) -> dict[str, Any] | None:
    if reference is None:
        if provenance == "reviewed_real":
            raise ValueError("reviewed_real case requires a reviewed reference")
        return None
    if provenance == "incomplete":
        raise ValueError("incomplete cases cannot carry a scored reference")
    exact_keys(reference, {"review_status", "review_basis", "source", "expected"})
    if reference["review_status"] != "approved" or not isinstance(reference["review_basis"], str) \
            or not reference["review_basis"].strip():
        raise ValueError("scored reference requires explicit approval and basis")
    source = _source(reference["source"], root, public=False)
    if source["path"] in {item["path"] for item in selected} \
            or source["sha256"] in {item["sha256"] for item in selected}:
        raise ValueError("reference source must be separate from public input sources")
    expected = reference["expected"]
    exact_keys(expected, {"failure_class", "root_cause_status", "next_review", "evidence_ids"})
    routes = policy()["failure_routes"]
    if not isinstance(expected["failure_class"], str) or not isinstance(expected["root_cause_status"], str) \
            or expected["failure_class"] not in routes or expected["root_cause_status"] not in ROOT_STATUSES \
            or expected["next_review"] != routes[expected["failure_class"]]:
        raise ValueError("reference diagnosis conflicts with the learning policy")
    ids = expected["evidence_ids"]
    allowed = {item["evidence_id"] for item in selected}
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids) \
            or len(ids) != len(set(ids)) or not set(ids) <= allowed:
        raise ValueError("reference cites unavailable or repeated public evidence")
    if source["value"] != expected:
        raise ValueError("reference source and expected diagnosis differ")
    return {**reference, "source": source}


def build_cases(spec_path: Path, allowed_root: Path, output_dir: Path) -> dict[str, Any]:
    """Create a write-once bundle; manifest.json is the completion marker."""
    root = allowed_root.resolve(strict=True)
    spec_path = spec_path.resolve(strict=True)
    if not spec_path.is_relative_to(root):
        raise ValueError("case manifest must be inside the allowed root")
    spec = load_json_object(spec_path)
    exact_keys(spec, {"schema_version", "cases"})
    if spec["schema_version"] != SCHEMA_VERSION or not isinstance(spec["cases"], list):
        raise ValueError("unsupported case manifest")
    public_cases: list[dict[str, Any]] = []
    private_cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in spec["cases"]:
        exact_keys(case, {"case_id", "group_id", "question", "provenance", "public_evidence", "reference"})
        for key in ("case_id", "group_id", "question"):
            if not isinstance(case[key], str) or not case[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
        case_id = case["case_id"]
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if case["provenance"] not in PROVENANCE:
            raise ValueError("unknown case provenance")
        evidence = case["public_evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("each case needs explicit public evidence")
        selected = [_source(item, root, public=True) for item in evidence]
        ids = [item["evidence_id"] for item in selected]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate evidence_id in {case_id}")
        reference = _reference(case["reference"], case["provenance"], selected, root)
        public_case = {"case_id": case_id, "group_id": case["group_id"], "question": case["question"],
                       "evidence": [{"evidence_id": item["evidence_id"], "pointer": item["pointer"],
                                     "value": item["value"], "source_sha256": item["sha256"]}
                                    for item in selected]}
        public_case["input_sha256"] = sha256_json(public_case)
        public_cases.append(public_case)
        private_cases.append({"case_id": case_id, "group_id": case["group_id"],
                              "provenance": case["provenance"], "sources": selected, "reference": reference})
    public = {"schema_version": SCHEMA_VERSION, "cases": public_cases}
    private = {"schema_version": SCHEMA_VERSION, "public_sha256": sha256_json(public),
               "policy_sha256": sha256_file(POLICY),
               "builder_sha256": sha256_file(Path(__file__)), "cases": private_cases}
    marker = {"schema_version": SCHEMA_VERSION, "public_sha256": sha256_json(public),
              "private_sha256": sha256_json(private)}
    output_dir.mkdir()  # Existing paths are never overwritten.
    write_json(output_dir / "public.json", public, ensure_ascii=False)
    write_json(output_dir / "private.json", private, ensure_ascii=False)
    write_json(output_dir / "manifest.json", marker, ensure_ascii=False)
    return {"bundle": str(output_dir), "case_count": len(public_cases),
            "public_sha256": marker["public_sha256"]}
