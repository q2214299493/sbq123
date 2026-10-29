"""Cache dependencies and current-round provenance; no scientific acceptance logic."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links

from .catalog import blocked


VASP_FILES = ("INCAR", "OSZICAR", "OUTCAR", "POSCAR", "CONTCAR", "vasp.out")


def _kind(path):
    _no_links(path.absolute(), missing_ok=True)
    return "file" if path.is_file() else "directory" if path.is_dir() else "missing"


def _directory(path):
    children = []
    for child in path.iterdir():
        if blocked(child):
            continue
        if len(children) >= 4096:
            return {"path": str(path), "truncated": True}
        try:
            kind = _kind(child)
            children.append((child.name, kind, child.stat().st_size if kind == "file" else None))
        except (OSError, ValueError):
            children.append((child.name, "unreadable_or_link", None))
    return {"path": str(path), "children_sha256": sha256_json(sorted(children)), "count": len(children), "truncated": False}


def dependency_proof(registry, request, *, refresh=False):
    """Files are narrow dependencies; directory/global searches also bind coverage."""
    catalog = registry.catalog
    try:
        paths = [catalog.resolve(identity) for identity in request["target_ids"]]
        expected = [path for path in paths if path.is_file()]
        optional = []
        if request["tool"] in {"vasp.inspect", "terminal.align"} and len(paths) == 1:
            optional = [paths[0] / name for name in VASP_FILES]
            expected += [path for path in optional if path.is_file()]
        journals = [path.with_name(path.name + suffix) for path in expected if path.suffix in {".db", ".sqlite3"}
                    for suffix in ("-wal", "-journal")]
        proof = {"version": 1, "expected_files": sorted(str(path) for path in expected),
                 "presence": [{"path": str(path), "kind": _kind(path)} for path in [*optional, *journals]], "search": None}
        searching = request["tool"] in {"methods.search", "history.search"} and (not paths or any(path.is_dir() for path in paths))
        if searching:
            roots = paths or catalog.scopes
            if refresh:
                for root in roots:
                    if root.is_dir():
                        scope = next(i for i, bound in enumerate(catalog.scopes) if root.is_relative_to(bound))
                        catalog.discover(root, scope, 2)
            visible = [path for path in catalog.paths.values() if any(path == root or path.is_relative_to(root) for root in roots)]
            directories = sorted(set(path for path in [*roots, *visible] if path.is_dir()))
            proof["search"] = {"roots": [str(path) for path in roots], "directories": [_directory(path) for path in directories],
                               "catalogued_files": [list(row) for row in sorted({(str(path), path.stat().st_size) for path in visible if path.is_file()})],
                               "coverage": "bounded catalog plus direct membership of catalogued directories"}
        return proof
    except (OSError, ValueError):
        return {"version": 1, "unavailable": True}


def stamp(proof, after, sources):
    bound = {source["path"] for source in sources}
    for source in sources:
        if source.get("kind") == "derived_corpus_receipt":
            bound.update(row["path"] for row in load_json_object(Path(source["path"]))["sources"])
    search = proof.get("search") or {}
    return {"proof": after, "stable": proof == after,
            "complete_inputs": not after.get("unavailable") and set(after.get("expected_files", [])) <= bound
                and not any(row["truncated"] for row in search.get("directories", []))}


def dependencies_match(result, proof):
    saved = result.get("cache_dependencies", {})
    return bool(saved.get("stable") and saved.get("complete_inputs") and saved.get("proof") == proof)


def _publish(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if sha256_json(load_json_object(path)) != sha256_json(document):
            raise ValueError("current-round derived receipt differs")
    else:
        write_json_exclusive(path, document)


def rebind_result(old, refs, registry, parent):
    """Copy bytes, rebind derived metadata, retain immutable parent/origin hashes."""
    replacements, by_source = {}, {}
    for reference in refs:
        _, current = registry.catalog.freeze(Path(reference["path"]))
        if current["sha256"] != reference["sha256"]:
            raise ValueError("source changed during current-round rebinding")
        replacements[reference["snapshot"]] = current["snapshot"]
        by_source[(reference["path"], reference["sha256"])] = current

    def rewrite(value):
        if isinstance(value, dict):
            result = {key: rewrite(item) for key, item in value.items()}
            key = (value.get("path"), value.get("sha256"))
            if isinstance(value.get("snapshot"), str) and value["snapshot"] in replacements \
                    and isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str) and key in by_source:
                result.update(by_source[key])
            return result
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, str):
            return replacements.get(value, value)
        return value

    result = rewrite(deepcopy(old))
    for index, reference in enumerate(old.get("sources", [])):
        if reference.get("kind") != "derived_corpus_receipt":
            continue
        path = Path(reference["path"])
        _no_links(path.absolute())
        if not path.resolve().is_relative_to((parent / "tools").resolve()) or sha256_file(path) != reference["sha256"]:
            raise ValueError("search corpus is not bound to the parent round")
        corpus = rewrite(load_json_object(path))
        corpus["rebound_from"] = {"path": str(path), "sha256": reference["sha256"]}
        target = registry.output / "tools" / ("search-corpus-resumed-" + reference["sha256"][:16] + ".json")
        _publish(target, corpus)
        result["sources"][index] = {"path": str(target), "sha256": sha256_file(target), "kind": "derived_corpus_receipt"}
    draft = result.get("data", {}).get("draft") if isinstance(result.get("data"), dict) else None
    if draft:
        original = old["data"]["draft"]
        path = Path(original["path"])
        _no_links(path.absolute())
        if not path.resolve().is_relative_to((parent / "drafts").resolve()) or sha256_file(path) != original["sha256"]:
            raise ValueError("draft is not bound to the parent round")
        document = rewrite(load_json_object(path))
        document["rebound_from"] = {"path": str(path), "sha256": original["sha256"]}
        target = registry.output / "drafts" / ("resumed-" + original["sha256"][:16]) / path.name
        _publish(target, document)
        draft.update({"path": str(target), "sha256": sha256_file(target)})
    return result
