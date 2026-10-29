"""Registered host operations using existing scientific owners; no job executor."""
from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
import sys
from collections import deque
from pathlib import Path
import sqlite3

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.catalysis_retrieval.ranking import bm25_scores
from scripts.catalysis_retrieval.workflow import search_records
from scripts.neb_agent.utils_structure import compatible, read_poscar
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.fingerprint import build_fingerprint, rank_templates
from scripts.ts_strategy_engine.learning_store import read_events
from scripts.ts_strategy_engine.learning_cases import PRIVATE_POINTER_TOKENS
from scripts.ts_strategy_engine.strategy import compose_strategy
from scripts.ts_strategy_engine.templates import load_templates
from scripts.scientific_validation import validate_finite_tree

from .catalog import Catalog
from .vasp_tools import inspect_vasp
from . import structure_tools
from .cache_state import dependency_proof, dependencies_match, stamp


SPECS = {
    "evidence.list": "定向展开目录/按文件名检索。target_ids为目录，可空；query为关键词。",
    "evidence.read": "定向读取文件；query必须为JSON pointer、文件内实际子串或@tail(最后80行)，空串读开头；不要把读取意图当检索字串。",
    "vasp.inspect": "target_ids为一个计算目录。复用VASP/SCF/力解析，分别列电子、离子标志、进程页脚；无调度器断言。",
    "structures.measure": "target_ids为1至3个POSCAR/CONTCAR。原子顺序、约束、MIC距离/位移；只测量不接受结构。",
    "structures.compare": "定向比较1至3个结构。query为JSON对象，可含pairs_zero_based(原子对列表)、adsorbate_zero_based、surface_zero_based。逐对距离、最近选定表面原子、同序目标RMSD；默认非Fe为吸附物，所有Fe为比较集合，不推断顶层或重排映射。",
    "terminal.align": "target_ids为一个计算目录。比较OUTCAR最后完整位置/力块与CONTCAR，结合OSZICAR末态证据。",
    "history.search": "检索范围内已有复核、尝试、策略和反馈；可给稳定的SQLite快照ID，生产数据库不写入。",
    "strategy.candidates": "target_ids顺序：反应contract、端点POSCAR，可选历史数据库快照。调用现有fingerprint/rank/compose，不授予执行权。",
    "methods.search": "query为方法关键词；target_ids可空(项目文档)，也可指定方法文档/目录。给白名单JSONL及已审核查询向量时调用现有混合检索。",
    "workflow.draft": "与strategy.candidates相同输入，保存现有策略组合器生成的候选草案；缺少contract/端点时拒绝，不生成虚构输入。",
    "workflow.review": "吸附结构可审阅草案：两个结构ID(参考目标、待评候选)，query必须为JSON对象{option_id:方案分支ID,adsorbate_zero_based:原子列表}。复用已有adsmind连接性规则，不生成计算参数/成本，不接受结构，不执行。",
}


def _implementation_identity():
    root = Path(__file__).parents[1]
    names = ["neb_agent/outcar_blocks.py", "neb_agent/utils_vasp.py", "neb_agent/utils_structure.py",
             "adsmind_lite/relaxed_analysis.py", "adsmind_lite/adsmind_common.py", "adsmind_lite/candidate_generation.py",
             "vasp_result_gate.py", "scientific_validation.py", "catalysis_retrieval/ranking.py", "catalysis_retrieval/workflow.py",
             "ts_strategy_engine/contract.py", "ts_strategy_engine/fingerprint.py", "ts_strategy_engine/strategy.py",
             "ts_strategy_engine/templates.py", "ts_strategy_engine/learning_store.py"]
    files = [*Path(__file__).parent.glob("*.py"), *[root / name for name in names]]
    dependencies = {}
    for package in ("numpy", "ase", "PyYAML", "jsonschema"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = "not installed"
    return {"sources": {str(p.relative_to(root)): sha256_file(p) for p in files},
            "python": sys.version, "dependencies": dependencies}


class ToolRegistry:
    def __init__(self, catalog: Catalog, project: Path, output: Path):
        self.catalog, self.project, self.output = catalog, project.resolve(), output
        self.actions = []
        self.cache = {}
        self.results = {}
        self.implementation = _implementation_identity()
        self.implementation_sha256 = sha256_json(self.implementation)

    @staticmethod
    def fingerprint(request):
        effective = dict(request)
        if request["tool"] in {"vasp.inspect", "terminal.align", "structures.measure", "strategy.candidates", "workflow.draft"}:
            effective["query"], effective["limit"] = "", 5
        return sha256_json(effective)

    def execute(self, request: dict) -> dict:
        if set(request) != {"tool", "target_ids", "query", "limit"} or request["tool"] not in SPECS:
            raise ValueError("unregistered host tool or argument fields")
        ids, query, limit = request["target_ids"], request["query"], request["limit"]
        if not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(v, str) for v in ids) \
                or not isinstance(query, str) or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 40:
            raise ValueError("invalid bounded host request")
        for identity in ids:
            self.catalog.resolve(identity)
        fingerprint = self.fingerprint(request)
        identity = f"E{len(self.actions) + 1:03d}"
        proof = dependency_proof(self, request, refresh=True)
        invalidated = fingerprint in self.cache and not dependencies_match(self.cache[fingerprint], proof)
        if invalidated:
            del self.cache[fingerprint]
        if fingerprint in self.cache:
            self.catalog.verify()
            cached = self.cache[fingerprint]
            result = {**cached, "evidence_id": identity, "reused_from": cached["evidence_id"], "host_executed": False}
        else:
            sources = []
            try:
                value = self.dispatch(request["tool"], ids, query, limit, sources)
                self.catalog.verify()
                validate_finite_tree(value, "host tool result")
                result = {"evidence_id": identity, "tool": request["tool"], "status": "PARTIAL" if isinstance(value, dict) and value.get("component_errors") else "OK", "host_executed": True,
                          "data": value, "sources": sources, "scientific_acceptance": False}
            except (OSError, ValueError, KeyError, TypeError, IndexError, ImportError, SystemExit, sqlite3.Error) as exc:
                result = {"evidence_id": identity, "tool": request["tool"], "status": "ERROR", "host_executed": True,
                          "error": f"{type(exc).__name__}: {exc}", "sources": sources,
                          "availability": "unknown", "scientific_acceptance": False}
            result["cache_dependencies"] = stamp(proof, dependency_proof(self, request), sources)
            self.cache[fingerprint] = result
        path = self.output / "tools" / (identity + ".json")
        path.parent.mkdir(exist_ok=True)
        write_json_exclusive(path, {"request": request, "result": result})
        action = {"evidence_id": identity, "request": request, "result_path": str(path), "result_sha256": sha256_file(path),
                  "status": result["status"], "executed": result["host_executed"], "reused_from": result.get("reused_from")}
        action.update({"implementation_sha256": self.implementation_sha256, "reused_from_parent": result.get("reused_from_parent")})
        action["cache_invalidated"] = invalidated
        self.actions.append(action)
        self.results[identity] = result
        return result

    def dispatch(self, tool, ids, query, limit, sources):
        if tool == "evidence.list":
            return self.catalog.listing(ids, query, limit)
        if tool == "evidence.read":
            return self.read(ids, query, sources)
        if tool in {"vasp.inspect", "terminal.align"}:
            if len(ids) != 1:
                raise ValueError("one calculation directory required")
            return self.vasp(ids[0], sources, align=tool == "terminal.align")
        if tool == "structures.measure":
            return self.structures(ids, sources)
        if tool == "structures.compare":
            if not ids:
                raise ValueError("structure IDs required")
            return structure_tools.compare([self.frozen(identity, sources) for identity in ids], ids, query)
        if tool == "workflow.review":
            return structure_tools.review(self, ids, query, sources)
        if tool in {"methods.search", "history.search"}:
            return self.search(tool, ids, query, min(limit, 5), sources)
        return self.strategy(ids, sources, draft=tool == "workflow.draft")

    def frozen(self, identity, sources):
        path, reference = self.catalog.freeze(self.catalog.resolve(identity, directory=False))
        sources.append(reference)
        return path

    def read(self, ids, query, sources):
        if not ids:
            raise ValueError("file IDs required")
        output = []
        for identity in ids:
            path = self.frozen(identity, sources)
            if path.suffix in {".sqlite3", ".db"}:
                raise ValueError("use history.search for database snapshots")
            if self.catalog.mode == "evaluation" and path.suffix == ".json" and (not query.startswith("/") or any(
                    token.lower() in PRIVATE_POINTER_TOKENS for token in query.split("/"))):
                raise ValueError("evaluation JSON reads require a selected non-reference scalar pointer")
            if query.startswith("/") and path.suffix == ".json":
                value = load_json_object(path)
                for key in query[1:].split("/"):
                    token = key.replace("~1", "/").replace("~0", "~")
                    value = value[int(token)] if isinstance(value, list) else value[token]
                if self.catalog.mode == "evaluation" and isinstance(value, (dict, list)):
                    raise ValueError("evaluation JSON pointer must select a scalar, not siblings or reference containers")
                output.append({"source_id": identity, "pointer": query, "value": value})
            else:
                rows = []
                if query == "@tail":
                    with path.open(encoding="utf-8", errors="replace") as handle:
                        rows = [{"line": number, "text": line[:1000].rstrip()} for number, line in deque(enumerate(handle, 1), maxlen=80)]
                    output.append({"source_id": identity, "excerpt": rows, "coverage": "last 80 lines, each at most 1000 characters"})
                    continue
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, 1):
                        if (not query or query.casefold() in line.casefold()) and len(rows) < 80:
                            rows.append({"line": number, "text": line[:1000].rstrip()})
                        if not query and len(rows) == 80:
                            break
                output.append({"source_id": identity, "excerpt": rows, "coverage": "at most 80 selected lines, each at most 1000 characters"})
        return output

    def vasp(self, identity, sources, *, align):
        directory = self.catalog.resolve(identity, directory=True)
        return inspect_vasp(self.catalog, directory, sources, align=align)

    def structures(self, ids, sources):
        if not ids:
            raise ValueError("structure IDs required")
        parsed = [read_poscar(self.frozen(i, sources)) for i in ids]
        from ase.geometry import find_mic
        rows = []
        for identity, a in zip(ids, parsed):
            active = [i for i, label in enumerate(a.labels) if label != "Fe"]
            vectors = a.frac[:, None, :] @ a.cell - a.frac[None, :, :] @ a.cell
            _, distances = find_mic(vectors.reshape(-1, 3), a.cell, pbc=True)
            distances = distances.reshape(a.atom_count, a.atom_count)
            np.fill_diagonal(distances, np.inf)
            pair = tuple(int(i) for i in np.unravel_index(np.argmin(distances), distances.shape)) if a.atom_count > 1 else None
            minimum = float(distances[pair]) if pair is not None else None
            rows.append({"source_id": identity, "atoms": a.atom_count, "symbols": a.labels,
                         "fixed_zero_based": [i for i, flag in enumerate(a.flags) if flag and all(v == "F" for v in flag)],
                         "minimum_pair_A": minimum, "minimum_pair_zero_based": pair,
                         "adsorbate_pairs": [{"atoms_zero_based": [i, j], "atoms_one_based": [i + 1, j + 1],
                                               "elements": [a.labels[i], a.labels[j]], "MIC_A": float(distances[i, j])}
                                              for n, i in enumerate(active) for j in active[n + 1:]][:100]})
        comparisons = []
        for left, right in zip(parsed[:-1], parsed[1:]):
            errors = compatible(left, right)
            row = {"mapping_cell_constraint_errors": errors}
            if not errors:
                _, norms = find_mic((right.frac - left.frac) @ left.cell, left.cell, pbc=True)
                index = int(np.argmax(norms))
                row.update({"maximum_same_index_MIC_A": float(norms[index]), "atom_zero_based": index,
                            "atom_one_based": index + 1, "element": left.labels[index]})
            comparisons.append(row)
        return {"structures": rows, "comparisons": comparisons,
                "scope": "numeric identity/distance evidence only; adjacent path images are not optimizer time steps"}

    def database(self, identity, sources):
        original = self.catalog.resolve(identity, directory=False)
        if any(original.with_name(original.name + suffix).exists() for suffix in ("-wal", "-journal")):
            raise ValueError("live/WAL database needs an owner-produced consistent snapshot")
        snapshot = self.frozen(identity, sources)
        target = self.output / ("history-copy-" + sha256_file(snapshot)[:12] + ".sqlite3")
        if not target.exists():
            with sqlite3.connect(snapshot.as_uri() + "?mode=ro&immutable=1", uri=True) as reader, sqlite3.connect(target) as writer:
                reader.backup(writer)
        return target

    def search(self, tool, ids, query, limit, sources):
        if self.catalog.mode == "evaluation" and tool == "history.search":
            raise ValueError("historical answer/experience queries are disabled in frozen evaluation")
        if not query.strip():
            raise ValueError("a directed query is required")
        if tool == "methods.search" and ids and self.catalog.resolve(ids[0]).suffix == ".jsonl":
            records = self.frozen(ids[0], sources)
            vector = self.frozen(ids[1], sources) if len(ids) > 1 else None
            model = load_json_object(vector)["embedding_provenance"]["model"] if vector else "sentence-transformers/all-MiniLM-L6-v2"
            result = search_records(records, query=query, query_vector=vector, model=model, lexical_only=vector is None, top_k=limit)
            return {"owner_retrieval": result, "scope": "No model download or network fallback. Lexical-only is diagnostic, never a production retrieval pass."}
        if tool == "history.search" and ids and self.catalog.resolve(ids[0]).suffix in {".sqlite3", ".db"}:
            database = self.database(ids[0], sources)
            events = {kind: read_events(database, kind) for kind in ("variant", "attempt", "outcome")}
            rows = [{"kind": kind, "id": identity, "value": value} for kind, group in events.items() for identity, value in group.items()
                    if query.casefold() in json.dumps(value, ensure_ascii=False).casefold()]
            return {"events": rows[:limit], "matching_count": len(rows), "scope": "existing history reader on private copy, no production writes"}
        candidates = []
        targets = [self.catalog.resolve(identity) for identity in ids]
        for identity, entry in list(self.catalog.entries.items()):
            path = self.catalog.paths[identity]
            if targets and not any(path == target or (target.is_dir() and path.is_relative_to(target)) for target in targets):
                continue
            is_method = path.suffix.lower() in {".md", ".yaml", ".yml", ".txt"}
            is_history = entry["type"] == "historical_interpretation" or any(v in path.name.lower() for v in ("attempt", "strategy"))
            if path.is_file() and path.stat().st_size <= 512_000 and (is_method if tool == "methods.search" else is_history):
                frozen, reference = self.catalog.freeze(path)
                text = frozen.read_text(encoding="utf-8", errors="replace")
                candidates.append((identity, text, reference))
        scores = bm25_scores(query, [row[1] for row in candidates])
        corpus = self.output / "tools" / f"search-corpus-{len(self.actions) + 1:03d}.json"
        corpus.parent.mkdir(exist_ok=True)
        write_json_exclusive(corpus, {"query": query, "sources": [row[2] for row in candidates],
                                     "ranker": "scripts.catalysis_retrieval.ranking.bm25_scores"})
        sources.append({"path": str(corpus), "sha256": sha256_file(corpus), "kind": "derived_corpus_receipt"})
        selected = sorted(zip(scores, candidates), key=lambda item: float(item[0]), reverse=True)
        matches = []
        for score, (identity, text, reference) in selected[:limit]:
            if score <= 0:
                continue
            sources.append(reference)
            lines = text.splitlines()
            starts = list(range(0, len(lines), 20)) or [0]
            chunks = ["\n".join(lines[start:start + 32]) for start in starts]
            chunk_scores = bm25_scores(query, chunks)
            center = starts[int(np.argmax(chunk_scores))] if len(chunk_scores) else 0
            matches.append({"source_id": identity, "score": float(score), "start_line": center + 1,
                            "excerpt": "\n".join(lines[center:center + 32])[:4000]})
        return {"matches": matches, "ranking": "existing BM25 local-text only; not semantic or external production retrieval",
                "coverage": "currently catalogued project documents/history", "online_connectors": "not connected by this adapter",
                "scientific_acceptance": False}

    def strategy(self, ids, sources, *, draft):
        if len(ids) < 2:
            raise ValueError("requires reaction contract ID and endpoint structure ID; missing data must be collected first")
        contract = load_contract(self.frozen(ids[0], sources))
        structure = read_poscar(self.frozen(ids[1], sources))
        rules_path = self.project / "configs/ts_strategy_engine/families.yaml"
        rules, reference = self.catalog.freeze(rules_path)
        sources.append(reference)
        fingerprint = build_fingerprint(contract, atom_symbols=structure.labels)
        templates = load_templates(self.database(ids[2], sources)) if len(ids) == 3 else []
        ranked = rank_templates(fingerprint, templates)
        strategy = compose_strategy(fingerprint, ranked, yaml.safe_load(rules.read_text(encoding="utf-8")))
        result = {"strategy": strategy, "template_count": len(templates), "scope": "existing strategy composition; endpoint/evidence/path/execution gates still required"}
        if draft:
            directory = self.output / "drafts" / f"candidate-{len(self.actions) + 1:03d}"
            directory.mkdir(parents=True)
            write_json_exclusive(directory / "ts_strategy.candidate.json", strategy)
            result["draft"] = {"path": str(directory / "ts_strategy.candidate.json"), "sha256": sha256_file(directory / "ts_strategy.candidate.json"),
                               "status": "UNAPPROVED_CANDIDATE_NOT_EXECUTABLE"}
        return result
