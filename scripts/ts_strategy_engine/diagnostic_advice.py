"""One-case diagnostic contract and scalar-only evidence tools; no scientific authority."""
from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.artifact_io import sha256_file, sha256_json
from .learning_cases import DIAGNOSIS_KEYS, diagnosis_error
from .learning_evaluation import _load_bundle
from .learning_evidence import exact_keys, observe
from .review_evidence import EvidenceTools, safe_file
from .strategy_learning import policy


TEXT = {"type": "string", "minLength": 1, "maxLength": 2400}
IDS = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def array_schema(item: dict, minimum: int = 0, maximum: int = 3) -> dict:
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def output_schema() -> dict:
    diagnosis = object_schema({
        "failure_class": {"enum": list(policy()["failure_routes"])},
        "causal_claim": {"anyOf": [TEXT, {"type": "null"}]},
        "causal_status": {"enum": ["unknown", "hypothesis", "confirmed"]},
        "causal_evidence_ids": IDS, "next_review": {"enum": list(policy()["failure_routes"].values())}, "evidence_ids": IDS,
    })
    return object_schema({
        "diagnosis": diagnosis,
        "observations": array_schema(object_schema({"statement": TEXT, "evidence_ids": IDS}), 1, 8),
        "hypotheses": array_schema(object_schema({"claim": TEXT, "supporting_evidence_ids": IDS,
                                                  "opposing_evidence_ids": IDS, "uncertainty": TEXT})),
        "missing_evidence": array_schema(TEXT, 1, 8),
        "next_check": object_schema({"action": TEXT, "rationale": TEXT, "evidence_ids": IDS,
                                     "expected_outcomes": array_schema(object_schema({"if": TEXT, "then": TEXT}), 2, 3)}),
        "conditional_proposals": array_schema(object_schema({"condition": TEXT, "proposal": TEXT, "evidence_ids": IDS})),
        "cost": object_schema({"status": {"enum": ["unknown", "estimate", "known"]},
                               "value": {"type": ["number", "null"], "minimum": 0},
                               "unit": {"type": ["string", "null"]}, "basis": TEXT, "evidence_ids": IDS}),
        # First round has no retrieval. A model cannot invent a retrieved source.
        "method_sources": {"type": "array", "items": TEXT, "maxItems": 0},
        "scientific_scope": TEXT,
    })


def backend_output_schema() -> dict:
    """Portable structural hint; the host still enforces every stronger constraint."""
    unsupported = {"uniqueItems", "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"}

    def project(value):
        if isinstance(value, dict):
            return {key: project(item) for key, item in value.items() if key not in unsupported}
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    return project(output_schema())


def load_case(bundle: Path, case_id: str) -> dict:
    bundle = bundle.resolve(strict=True)
    for name in ("manifest.json", "public.json", "private.json"):
        safe_file(bundle / name, bundle)
    marker, public, private = _load_bundle(bundle)
    pairs = [(a, b) for a, b in zip(public["cases"], private["cases"]) if a["case_id"] == case_id]
    if len(pairs) != 1:
        raise ValueError("diagnose requires one existing case ID")
    case, hidden = pairs[0]
    root = Path(private["allowed_root"])
    sources = {item["evidence_id"]: item for item in hidden["sources"]}
    for item in sources.values():
        safe_file(Path(item["path"]), root)
    selected = {"schema_version": 2, "cases": [case]}
    return {"case": case, "public": selected, "public_sha256": sha256_json(selected),
            "bundle_public_sha256": marker["public_sha256"], "root": root, "bundle": bundle,
            "sources": sources, "provenance": hidden["provenance"]}


class DiagnosticEvidence:
    """Read only preselected scalars. Neither full source JSON nor private answers leave the host."""

    NAME = "read_frozen_evidence"

    def __init__(self, loaded: dict):
        self.loaded = loaded
        self.read_ids: set[str] = set()

    def verify(self):
        for item in self.loaded["sources"].values():
            path = safe_file(Path(item["path"]), self.loaded["root"])
            if sha256_file(path) != item["sha256"]:
                raise ValueError("frozen source changed")
            observe([{key: value for key, value in item.items() if key != "evidence_id"}])

    def specs(self) -> list:
        return [{"type": "function", "deferLoading": False, "name": self.NAME,
                 "description": "Reverify and read selected frozen scalar evidence. No paths, commands, writes or acceptance.",
                 "inputSchema": object_schema({"evidence_ids": {**IDS, "minItems": 1,
                     "maxItems": len(self.loaded["sources"]),
                     "items": {"type": "string", "enum": sorted(self.loaded["sources"])}}})}]

    def execute(self, tool: str, arguments: dict) -> dict:
        if tool != self.NAME:
            raise ValueError("unapproved diagnostic tool")
        exact_keys(arguments, {"evidence_ids"})
        ids = arguments["evidence_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) \
                or len(ids) != len(set(ids)) or not set(ids) <= self.loaded["sources"].keys():
            raise ValueError("unique listed evidence IDs required")
        self.verify()
        result = [item for item in self.loaded["case"]["evidence"] if item["evidence_id"] in ids]
        self.read_ids.update(ids)
        return EvidenceTools.response({"evidence": result, "execution_permission": False}, True)


def validate_output(document: dict, loaded: dict, read_ids: set[str]) -> dict:
    Draft202012Validator(output_schema()).validate(document)
    allowed = set(loaded["sources"])
    error = diagnosis_error(document["diagnosis"], allowed)
    if error:
        raise ValueError(f"invalid generated diagnosis: {error}")
    citations: set[str] = set()

    def inspect(value):
        if isinstance(value, dict):
            for key, entry in value.items():
                if key.endswith("evidence_ids"):
                    if not set(entry) <= allowed:
                        raise ValueError("generated output cites unlisted evidence")
                    citations.update(entry)
                else:
                    inspect(entry)
        elif isinstance(value, list):
            for entry in value:
                inspect(entry)

    inspect(document)
    if not document["next_check"]["evidence_ids"] or any(not row["evidence_ids"] for row in document["observations"]):
        raise ValueError("observations and first check require evidence citations")
    if not citations <= read_ids:
        raise ValueError("generated output cites evidence not read through the host tool")
    cost = document["cost"]
    if cost["status"] == "unknown" and (cost["value"] is not None or cost["unit"] is not None):
        raise ValueError("unknown cost must not be encoded as zero or a measured number")
    if cost["status"] != "unknown" and (cost["value"] is None or not cost["unit"] or not cost["evidence_ids"]):
        raise ValueError("known/estimated cost requires a quantity, unit and evidence basis")
    answer = {"case_id": loaded["case"]["case_id"], "input_sha256": loaded["case"]["input_sha256"],
              **{key: document["diagnosis"][key] for key in DIAGNOSIS_KEYS}}
    return {"schema_version": 2, "public_sha256": loaded["public_sha256"], "answers": [answer]}
