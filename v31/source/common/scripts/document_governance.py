"""Read-only document classification, freshness and link checks; no scientific authority."""
from __future__ import annotations

from scripts.runtime_resources import require_repository_context

import argparse
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

from scripts.provenance_fields import timestamp
from scripts.registry_schema import CURRENT_VERSION

CLASSES = {"CURRENT_AUTHORITY", "CURRENT_REFERENCE", "GENERATED_CURRENT_REPORT",
           "HISTORICAL_SNAPSHOT", "SUPERSEDED", "UNKNOWN_REVIEW_REQUIRED"}
ROOT = Path(__file__).resolve().parents[1]


def read_document(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return preserved_document_metadata(path), text
    _, header, body = text.split("---\n", 2)
    metadata = yaml.safe_load(header)
    if not isinstance(metadata, dict) or metadata.get("document_class") not in CLASSES:
        raise ValueError(f"invalid document classification: {path}")
    timestamp(metadata.get("as_of"), "document as_of")
    return metadata, body


def preserved_document_metadata(path: Path) -> dict:
    # Root reports are hash-bound historical artifacts: classify them externally,
    # never rewrite their bytes to add a banner or infer freshness from a name.
    for root in path.resolve().parents:
        model = root / "docs/DOCUMENT_GOVERNANCE.md"
        if not model.is_file():
            continue
        _, header, _ = model.read_text(encoding="utf-8").split("---\n", 2)
        metadata = yaml.safe_load(header)
        relative = path.resolve().relative_to(root).as_posix()
        for key, classification in (("preserved_authority_documents", "CURRENT_AUTHORITY"),
                                    ("preserved_historical_documents", "HISTORICAL_SNAPSHOT")):
            if relative in metadata.get(key, []):
                return {"document_class": classification, "as_of": metadata["as_of"],
                        "source_version": metadata["source_version"], "source_branch": metadata["source_branch"],
                        "source_scope": "preserved canonical report/constraint; B6 classification only",
                        "evidence_kind": "HISTORICAL" if classification == "HISTORICAL_SNAPSHOT" else "CURRENT_CODE_STATE"}
        break
    return {"document_class": "UNKNOWN_REVIEW_REQUIRED"}


def is_current_authority(root: Path, relative: str) -> bool:
    model, _ = read_document(root / "docs/DOCUMENT_GOVERNANCE.md")
    metadata, _ = read_document(root / relative)
    owners = {path for value in model["owners"].values() for path in (value if isinstance(value, list) else [value])}
    return metadata["document_class"] == "CURRENT_AUTHORITY" and relative in owners | {"docs/DOCUMENT_GOVERNANCE.md"}


def wording_findings(metadata: dict, body: str) -> list[str]:
    if metadata.get("document_class") not in {"CURRENT_AUTHORITY", "CURRENT_REFERENCE", "GENERATED_CURRENT_REPORT"}:
        return []
    findings = []
    for number, line in enumerate(body.splitlines(), 1):
        lower = line.lower()
        if re.search(r"\bcurrently running\b|当前正在运行", lower):
            if not re.search(r"observed_at:\s*\d{4}-\d{2}-\d{2}t", lower) or "source:" not in lower:
                findings.append(f"{number}: live scheduler claim lacks timestamp/source")
        if "production ready" in lower and not re.search(r"not |no |never |without|does not|不得|不能", lower):
            if "deployment_evidence:" not in lower or "observed_at:" not in lower:
                findings.append(f"{number}: production readiness lacks deployment evidence")
        if "validated" in lower and (re.search(r"tests? pass|pytest|unit tests?|integration tests?", lower)
                                     or metadata.get("evidence_kind") == "SOFTWARE_TEST_RECORD"):
            if not re.search(r"not |never |does not|cannot|software|不能", lower):
                findings.append(f"{number}: software tests cannot establish scientific validation")
        if re.search(r"(?:supported_code_schema|current supported (?:code )?schema)\s*[:=]?\s*(?:version |v)?8\b|current code.*schema (?:version )?v?8\b", lower):
            findings.append(f"{number}: supported schema must resolve to {CURRENT_VERSION}")
        if re.search(r"production_schema_version:\s*9\b|production (?:database )?(?:is |uses |at )?(?:schema )?v9\b|production (?:registry|database).*migrated to (?:schema )?v?9\b", lower):
            if "deployment_evidence:" not in lower:
                findings.append(f"{number}: production schema is not established by source schema")
        if re.search(r"(?:final|current|verified|pass).*filename.*(?:proves|guarantees).*current", lower):
            findings.append(f"{number}: filename cannot establish freshness")
    return findings


def classify_data(relative: str, policy: dict) -> str:
    path = relative.replace("\\", "/")
    if Path(path).is_absolute() or ".." in path.split("/"):
        raise ValueError("classification requires a repository-relative path")
    for rule in policy["rules"]:
        if any(fnmatchcase(path, pattern) for pattern in rule["patterns"]):
            return rule["class"]
    return "UNKNOWN_REVIEW_REQUIRED"


def local_links(text: str) -> set[str]:
    return {match.group(1).split(" \"")[0].strip("<>") for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text)}


def broken_links(root: Path, relative: str, *, only: set[str] | None = None) -> list[str]:
    source = root / relative
    links = local_links(source.read_text(encoding="utf-8"))
    errors = []
    for target in sorted(links if only is None else links & only):
        url = urlsplit(target)
        if url.scheme or url.netloc:
            continue
        destination = (source.parent / unquote(url.path)).resolve() if url.path else source.resolve()
        try:
            destination.relative_to(root.resolve())
        except ValueError:
            errors.append(f"{target}: outside repository")
            continue
        if not destination.exists():
            errors.append(f"{target}: missing target")
        elif url.fragment and destination.suffix == ".md":
            headings = re.findall(r"(?m)^#+\s+(.+)$", destination.read_text(encoding="utf-8"))
            anchors = {re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-") for title in headings}
            if unquote(url.fragment) not in anchors:
                errors.append(f"{target}: missing heading")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Check explicitly classified document wording and local links.")
    parser.add_argument("documents", nargs="+")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--links", action="store_true")
    args = parser.parse_args()
    args.root = require_repository_context(args.root)
    findings = {}
    for relative in args.documents:
        metadata, body = read_document(args.root / relative)
        errors = wording_findings(metadata, body)
        if metadata["document_class"] == "UNKNOWN_REVIEW_REQUIRED":
            errors.append("unclassified document requires review")
        if args.links:
            errors += broken_links(args.root, relative)
        if errors:
            findings[relative] = errors
    print(json.dumps(findings, indent=2, ensure_ascii=False))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
