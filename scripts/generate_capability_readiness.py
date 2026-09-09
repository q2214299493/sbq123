"""Deterministic derived capability view; never opens a registry or probes deployment."""
from __future__ import annotations

from scripts.runtime_resources import require_repository_context

import argparse
import json
import re
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_text
from scripts.document_governance import read_document
from scripts.registry_schema import CURRENT_VERSION

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"Planned", "Active", "Blocked", "Completed"}


def build_readiness(root: Path) -> dict:
    metadata, _ = read_document(root / "docs/DOCUMENT_GOVERNANCE.md")
    _, text = read_document(root / "docs/06_MODULE_MAP.md")
    rows = re.findall(r"(?m)^\| `([^`]+)` \| (Planned|Active|Blocked|Completed) \|", text)
    if not rows or len({name for name, _ in rows}) != len(rows):
        raise ValueError("module map requires unique module status rows")
    blocks = re.findall(r"```capability-evidence\n(.*?)```", text, re.S)
    if len(blocks) != 1:
        raise ValueError("module map requires one maturity evidence annotation block")
    annotations = yaml.safe_load(blocks[0]) or {}
    if not isinstance(annotations, dict) or set(annotations) - {name for name, _ in rows}:
        raise ValueError("maturity evidence references an unknown module")
    sources = {"docs/DOCUMENT_GOVERNANCE.md", "docs/06_MODULE_MAP.md", "scripts/registry_schema.py",
               "scripts/generate_capability_readiness.py", "scripts/document_governance.py"}
    modules = []
    for name, status in rows:
        item = annotations.get(name, {})
        implementation = item.get("implementation", "unknown")
        tests = item.get("tests", ["unknown"])
        science = item.get("scientific_validation", "unknown")
        production = item.get("production_readiness", "blocked" if status == "Blocked" else "unverified")
        if implementation not in {"yes", "partial", "no", "unknown"}:
            raise ValueError("unsupported implementation maturity")
        if not isinstance(tests, list) or not tests or set(tests) - {"unit", "integration", "none", "unknown"}:
            raise ValueError("unsupported test evidence")
        # B6 has no reviewed deployment or new scientific acceptance evidence.
        if science not in {"unknown", "unvalidated", "not_applicable"}:
            raise ValueError("scientific validation needs reviewed scientific evidence; tests are insufficient")
        if production not in {"unverified", "blocked", "limited"}:
            raise ValueError("production readiness needs deployment evidence")
        evidence = item.get("evidence", [])
        if implementation != "unknown" or tests != ["unknown"]:
            if not evidence:
                raise ValueError("maturity declaration lacks explicit source references")
        for source in evidence:
            if not isinstance(source, str) or ".." in source.split("/") or not source.startswith(("scripts/", "tests/", "reports/refactor_audit/")):
                raise ValueError("readiness sources must be code/tests/scoped reports, never production data")
            if not (root / source).is_file():
                raise ValueError(f"missing maturity evidence: {source}")
            sources.add(source)
        modules.append({"module": name, "module_status": status, "implementation": implementation,
                        "tests": tests, "scientific_validation": science, "production_readiness": production,
                        "evidence": evidence, "scope": item.get("scope", "No explicit maturity evidence; do not infer from status or file existence.")})
    return {"document_class": "GENERATED_CURRENT_REPORT", "authority": "DERIVED_NOT_AUTHORITATIVE",
            "as_of": metadata["as_of"], "source_scope": metadata["source_scope"],
            "source_branch": metadata["source_branch"], "source_version": metadata["source_version"],
            "evidence_kind": "CURRENT_CODE_STATE", "supported_code_schema": CURRENT_VERSION,
            "production_schema_version": "NOT_VERIFIED_IN_B6",
            "source_hash_convention": "UTF-8 text with LF newlines; not scientific file hashes",
            "source_sha256": {source: sha256_text((root / source).read_text(encoding="utf-8")) for source in sorted(sources)}, "modules": modules}


def render_readiness(payload: dict) -> str:
    metadata = {k: payload[k] for k in ("document_class", "as_of", "source_scope", "source_branch", "source_version", "evidence_kind")}
    lines = ["---", yaml.safe_dump(metadata, sort_keys=False).rstrip(), "---", "", "# Capability Readiness (DERIVED)", "",
             "Owner: [module map](../docs/06_MODULE_MAP.md). [Document governance](../docs/DOCUMENT_GOVERNANCE.md).",
             "This view is DERIVED_NOT_AUTHORITATIVE. Software tests never establish scientific validation or production deployment.",
             "SUPPORTED_CODE_SCHEMA: " + str(payload["supported_code_schema"]),
             "production_schema_version: NOT_VERIFIED_IN_B6", "",
             "Exact source hashes and evidence references: [JSON view](capability_readiness.json).", "",
             "| Module | Status (derived) | Implementation | Tests | Scientific validation | Production readiness |",
             "|---|---|---|---|---|---|"]
    for row in payload["modules"]:
        lines.append("| " + " | ".join([row["module"], row["module_status"], row["implementation"],
                                       ", ".join(row["tests"]), row["scientific_validation"], row["production_readiness"]]) + " |")
    return "\n".join(lines) + "\n"


def generate(root: Path) -> tuple[Path, Path]:
    payload = build_readiness(root)
    directory = root / "reports"
    directory.mkdir(exist_ok=True)
    json_path, markdown_path = directory / "capability_readiness.json", directory / "capability_readiness.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    markdown_path.write_text(render_readiness(payload), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    args.root = require_repository_context(args.root)
    for path in generate(args.root.resolve()):
        print(path)


if __name__ == "__main__":
    main()
