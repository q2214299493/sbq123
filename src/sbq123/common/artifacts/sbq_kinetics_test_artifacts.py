"""Opt-in retention for MKM/KMC test runs. No operation deletes an artifact."""

from __future__ import annotations

import os
import platform
import re
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sbq123.common.artifacts.artifact_io import (
    load_json_object, sha256_file, sha256_text, write_json_exclusive,
)

AREAS = ("inputs", "outputs", "logs", "scratch")
CLASSES = {"unknown", "input", "fixture", "log", "regression", "golden",
           "scientific-evidence", "historical-evidence", "pytest-alias"}


def create_run(parent: Path, suite: str, *, nodeid: str, revision: str,
               command: list[str], versions: dict[str, str], seed: int | None = None) -> Path:
    """Allocate one persistent test sandbox. Record the actual invoking environment."""
    if suite not in {"mkm", "kmc"} or not all((nodeid, revision, command, versions)):
        raise ValueError("supply suite, test ID, source revision, argv and dependency versions")
    run = parent.resolve() / f"{suite}-{uuid.uuid4().hex}"
    run.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(run / "run.json", {
        "format": "kinetics-test-run/1", "run_id": run.name, "suite": suite,
        "created_utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
        "nodeid": nodeid, "revision": revision, "argv": command, "seed": seed,
        "versions": versions, "python": sys.version, "platform": platform.platform(),
    })
    for area in AREAS:
        (run / area).mkdir()
    return run


def _kind(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return "link"
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"unsupported reparse point: {path}")
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    if stat.S_ISREG(info.st_mode):
        return "file"
    raise ValueError(f"unsupported object: {path}")


def _inventory(run: Path) -> dict:
    if _kind(run) != "directory" or _kind(run / "run.json") != "file":
        raise ValueError("invalid run or metadata")
    unexpected = {p.name for p in run.iterdir()} - {*AREAS, "run.json", "manifest.json"}
    if unexpected or load_json_object(run / "run.json").get("run_id") != run.name:
        raise ValueError("unmanaged root entry or mismatched run identity")
    entries = {}

    def visit(path):
        name = path.relative_to(run).as_posix()
        kind = _kind(path)
        record = {"kind": kind}
        entries[name] = record
        if kind == "link":
            target = os.readlink(path)
            record.update(target=target, sha256=sha256_text(target))
        elif kind == "file":
            record["sha256"] = sha256_file(path)
        else:
            for child in sorted(path.iterdir()):
                visit(child)

    for area in AREAS:
        if _kind(run / area) != "directory":
            raise ValueError(f"invalid run area: {area}")
        visit(run / area)
    return entries


def _references(entries, references):
    """Bind each incoming reference to its target and referring regular file."""
    result = {}
    for target, sources in references.items():
        if target not in entries or not sources:
            raise ValueError(f"missing target or referring source: {target}")
        result[target] = {}
        for source in sources:
            path = Path(source).absolute()
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError(f"reference is not a file: {path}")
            result[target][str(path)] = sha256_file(path)
    return result


def seal_run(run: Path, *, classes: dict[str, str], references: dict) -> str:
    """Seal once after all writers exit. Return the SHA-256 to retain for review."""
    entries = _inventory(run)
    if classes.keys() - entries.keys() or set(classes.values()) - CLASSES:
        raise ValueError("classification has a missing path or unsupported class")
    for name, item in entries.items():
        item["class"] = classes.get(name, "unknown")
        if PurePosixPath(name).name.casefold() == "accepted.json":
            item["class"] = "historical-evidence"
    manifest = {"format": "kinetics-test-manifest/1", "run_id": run.name,
                "metadata_sha256": sha256_file(run / "run.json"), "entries": entries,
                "references": _references(entries, references)}
    return sha256_file(write_json_exclusive(run / "manifest.json", manifest))


def _alias_destination(run, key, item, entries):
    """Accept one lexical hop to an inventoried, real numbered sibling."""
    path = PurePosixPath(key)
    if item["kind"] != "link" or path.parts[0] != "scratch" or not path.name.endswith("current"):
        return None
    spelling = item["target"]
    if os.name == "nt" and spelling.startswith('\\\\?\\') and Path(spelling[4:]).is_absolute():
        spelling = spelling[4:]
    target = Path(spelling)
    if ".." in target.parts:
        return None
    if target.is_absolute() and target.parent == (run / key).parent:
        target = Path(target.name)
    if target.parts != (target.name,) or not re.fullmatch(re.escape(path.name[:-7]) + r"\d+", target.name):
        return None
    sibling = path.with_name(target.name)
    return sibling if entries.get(sibling.as_posix(), {}).get("kind") == "directory" else None


def _protection(entries):
    """Index descendants from the verified inventory. Never dereference a nested link."""
    scientific = {"scientific-evidence", "historical-evidence", "golden"}
    digests = {item["sha256"] for item in entries.values()
               if item["kind"] == "file" and item["class"] in scientific}
    protected = set()
    uncertain_subtrees = set()
    for key, item in entries.items():
        path = PurePosixPath(key)
        kind, label = item["kind"], item["class"]
        if path.name.casefold() == "accepted.json":
            protected.add(path.parent)
        if (kind == "directory" and label not in {"unknown", "pytest-alias"}
                or label in scientific | {"fixture", "input", "regression"}
                or kind == "file" and item["sha256"] in digests):
            protected.add(path)
        if kind == "link" or kind == "file" and label not in CLASSES - {"unknown", "pytest-alias"}:
            uncertain_subtrees.update(path.parents)
    containing = {parent for path in protected for parent in path.parents}
    return protected, containing, uncertain_subtrees


def cleanup_proposal(run: Path, manifest_sha256: str, *, current_references: dict) -> dict:
    """Review explicitly classified pytest aliases only. Caller supplies a fresh reference census."""
    entries = _inventory(run)
    manifest = run / "manifest.json"
    if _kind(manifest) != "file" or sha256_file(manifest) != manifest_sha256:
        raise ValueError("missing or stale manifest binding")
    sealed = load_json_object(manifest)
    if sealed["metadata_sha256"] != sha256_file(run / "run.json"):
        raise ValueError("run metadata changed")
    expected = {k: {f: v for f, v in item.items() if f != "class"}
                for k, item in sealed["entries"].items()}
    if entries != expected:
        raise ValueError("run contents changed")
    prior = sealed["references"]
    if _references(entries, prior) != prior:
        raise ValueError("reference changed")
    current = _references(entries, current_references)
    references = prior.keys() | current.keys()
    protected, containing, uncertain = _protection(sealed["entries"])
    candidates, held = [], {}
    for key, item in sealed["entries"].items():
        if item["class"] != "pytest-alias":
            continue
        path = PurePosixPath(key)
        destination = _alias_destination(run, key, item, entries)
        if destination is None:
            held[key] = "unverified numbered-sibling alias"
        elif destination in containing or protected.intersection((path, destination, *path.parents)):
            held[key] = "protected evidence or fixture directory"
        elif destination in uncertain:
            held[key] = "unresolved descendant link or unclassified file"
        elif any(key == ref or key.startswith(ref + "/") or ref.startswith(key + "/")
                 for ref in references):
            held[key] = "referenced path"
        else:
            candidates.append(key)
    return {"run_id": run.name, "manifest_sha256": manifest_sha256, "candidates": candidates,
            "held_aliases": held, "current_references": current,
            "approval_required": True, "deletion_authorized": False}

