from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scheduler_architecture import dispatch_sites

from scripts.artifact_io import sha256_json
from scripts.ts_strategy_engine.registry import open_registry, compatibility_fingerprint
from scripts.ts_strategy_engine.matched_static_evidence import validate_barrier_values
from tests.test_registry_write import _database


def test_registry_connection_commit_rollback_close_and_schema(tmp_path):
    db = _database(tmp_path)
    with open_registry(db, migrate=True) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert isinstance(connection.execute("SELECT 1").fetchone(), sqlite3.Row)
        connection.execute("INSERT INTO calculations(calculation_id,module,purpose,workflow_status,created_at) VALUES ('b5','test','fixture','registered','2026-09-09')")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="rollback"):
        with open_registry(db) as connection:
            connection.execute("INSERT INTO calculations(calculation_id,module,purpose,workflow_status,created_at) VALUES ('rollback','test','fixture','registered','2026-09-09')")
            raise RuntimeError("rollback")
    with open_registry(db) as connection:
        assert connection.execute("SELECT calculation_id FROM calculations").fetchall()[0][0] == "b5"
        assert connection.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 1
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError, match="not found"):
        with open_registry(missing, migrate=True):
            pytest.fail("missing schema accepted")
    assert not missing.exists()
    empty = tmp_path / "empty.sqlite3"
    with sqlite3.connect(empty):
        pass
    with pytest.raises(ValueError, match="schema is missing"):
        with open_registry(empty):
            pytest.fail("empty schema accepted")


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_barrier_validation_and_compatibility_identity_unchanged(bad):
    chemistry = {"branch": "fixture", "encut": 400}
    assert compatibility_fingerprint(chemistry) == sha256_json(chemistry)
    values = {"forward_barrier_ev": 1., "reverse_barrier_ev": 2., "reaction_energy_ev": -1.}
    assert validate_barrier_values(values) == values
    with pytest.raises(ValueError):
        validate_barrier_values({**values, "forward_barrier_ev": bad})


@pytest.mark.parametrize("surface", ["Pt110", "Fe211", "unknown"])
def test_unsupported_site_profile_never_uses_fe110_default(surface):
    from scripts.adsmind_lite.site_detection import detect_surface_sites, metallic_orientation

    root = Path(__file__).resolve().parents[1]
    assert metallic_orientation(surface) == ""
    result = detect_surface_sites(root / "calculations/true_fe110_clean_20260629/POSCAR", surface,
                                  "metallic_fe", root / "configs/adsmind_lite/surfaces.yaml",
                                  root / "configs/adsmind_lite/site_rules.yaml")
    assert result["status"] == "NEEDS_REVIEW"
    assert result["reason_code"] == "explicit_site_label_required"
    assert result["sites"] == []


def test_fe110_profile_preserves_supported_site_classes():
    from scripts.adsmind_lite.site_detection import detect_surface_sites

    root = Path(__file__).resolve().parents[1]
    result = detect_surface_sites(root / "calculations/true_fe110_clean_20260629/POSCAR", "Fe110",
                                  "metallic_fe", root / "configs/adsmind_lite/surfaces.yaml",
                                  root / "configs/adsmind_lite/site_rules.yaml")
    assert result["status"] == "PASS"
    assert [site["site_class"] for site in result["sites"]] == ["top_Fe", "bridge_FeFe_short", "bridge_FeFe_long", "hollow_FeFeFe"]


ROOT = Path(__file__).resolve().parents[1]


def maintained_trees():
    import ast

    return {p.relative_to(ROOT).as_posix(): ast.parse(p.read_text(encoding="utf-8"))
            for p in (ROOT / "scripts").rglob("*.py") if "__pycache__" not in p.parts}


def imported_modules(path, tree):
    import ast

    module = path.removesuffix(".py").replace("/", ".")
    package = module.split(".")[:-1]
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else [])) if node.level else node.module or ""
            result.add(base)
            result.update(base + "." + alias.name for alias in node.names)
    return result


def test_generic_registry_never_imports_ts_domain():
    for path, tree in maintained_trees().items():
        if Path(path).name.startswith("registry_"):
            assert not any(name.startswith("scripts.ts_strategy_engine") for name in imported_modules(path, tree)), path


def test_shared_infrastructure_dependency_closure_stays_domain_free():
    trees = maintained_trees()
    modules = {path.removesuffix(".py").replace("/", "."): path for path in trees}
    roots = {"scripts." + name for name in (
        "artifact_io", "jsonl_io", "provenance_fields", "scientific_validation", "prediction_provenance",
        "registry_connection", "registry_schema", "registry_transactions", "registry_compatibility", "execution_backends",
    )}
    pending, seen = list(roots), set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        assert not module.startswith(("scripts.ts_strategy_engine", "scripts.ts_validation", "scripts.adsorption", "scripts.adsmind_lite")), module
        if module in modules:
            path = modules[module]
            pending.extend(name for name in imported_modules(path, trees[path]) if name in modules)


def test_domain_cannot_import_cli_or_skill_implementations():
    adapters = {"scripts/ts_strategy_engine/cli.py", "scripts/ts_strategy_engine/cli_commands.py",
                "scripts/ts_strategy_engine/active_learning_cli.py", "scripts/ts_strategy_engine/learning_cli.py",
                "scripts/aqcat25_ts_active_learning.py", "scripts/state_manager/__main__.py"}
    cli_names = {p.removesuffix(".py").replace("/", ".") for p in adapters} | {"scripts.state_manager.cli", "scripts.registry_write"}
    for path, tree in maintained_trees().items():
        if path in adapters:
            continue
        dependencies = imported_modules(path, tree)
        assert not dependencies & cli_names, (path, dependencies & cli_names)
        assert not any(name.startswith("skills.") for name in dependencies), path


def test_authoritative_capabilities_have_one_implementation():
    import ast

    expected = {
        "open_registry": "scripts/registry_connection.py",
        "require_current_schema": "scripts/registry_connection.py",
        "migrate_registry": "scripts/registry_schema.py",
        "apply_registry_batch": "scripts/registry_mutations.py",
        "decide_execution": "scripts/ts_strategy_engine/execution_gate.py",
        "require_execution_authorization": "scripts/ts_strategy_engine/execution_evidence.py",
        "evaluate_quality": "scripts/neb_agent/path_quality_control.py",
        "analyze_dimer": "scripts/ts_strategy_engine/dimer_analysis.py",
        "analyze_vfa": "scripts/ts_validation/analyze_vfa.py",
        "assess_evidence": "scripts/adsmind_lite/evidence_lifecycle.py",
        "rank_records": "scripts/catalysis_retrieval/ranking.py",
        "validate_barrier_values": "scripts/ts_validation/barrier_values.py",
        "assert_dataset_splits_disjoint": "scripts/matris_training_exclusions.py",
    }
    found = {name: [] for name in expected}
    dispatch = []
    for path, tree in maintained_trees().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in found:
                found[node.name].append(path)
        if dispatch_sites(tree):
            dispatch.append(path)
    assert found == {name: [path] for name, path in expected.items()}
    assert dispatch == ["scripts/neb_agent/submission.py"]


def test_registry_and_skill_facades_delegate_without_business_logic():
    import ast
    import importlib
    from scripts import registry_connection, registry_mutations, registry_write
    from scripts.ts_strategy_engine import registry
    from scripts.catalysis_retrieval import records, ranking

    for name in ("open_registry", "require_current_schema", "table_exists", "utc_now"):
        assert getattr(registry, name) is getattr(registry_connection, name)
    assert registry_write.apply_registry_batch is registry_mutations.apply_registry_batch
    tree = maintained_trees()["scripts/ts_strategy_engine/registry.py"]
    assert all(isinstance(n, (ast.Import, ast.ImportFrom, ast.Expr)) for n in tree.body)
    tree = maintained_trees()["scripts/registry_write.py"]
    assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == ["main"]
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"execute", "executemany", "executescript", "connect"} for n in ast.walk(tree))
    for filename, owner in (("validate_records", records), ("hybrid_search", ranking)):
        legacy = importlib.import_module("skills.catalysis-data-retrieval.scripts." + filename)
        tree = ast.parse(Path(legacy.__file__).read_text(encoding="utf-8"))
        assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == ["main"]
        assert "sys.path" not in Path(legacy.__file__).read_text(encoding="utf-8")
        for name, value in vars(owner).items():
            if callable(value) and getattr(value, "__module__", None) == owner.__name__:
                assert getattr(legacy, name) is value


def test_maintained_runtime_import_graph_is_acyclic():
    trees = maintained_trees()
    modules = {p.removesuffix(".py").replace("/", "."): p for p in trees}
    graph = {module: imported_modules(path, trees[path]) & modules.keys() for module, path in modules.items()}
    done, active = set(), []
    def visit(module):
        assert module not in active, active + [module]
        if module in done:
            return
        active.append(module)
        for dependency in graph[module]:
            visit(dependency)
        active.pop()
        done.add(module)
    for module in graph:
        visit(module)


def test_dimer_cli_only_dispatches_review_to_application():
    import ast

    tree = maintained_trees()["scripts/ts_strategy_engine/cli_commands.py"]
    command = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_dimer_command")
    calls = {n.func.id for n in ast.walk(command) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert calls == {"prepare_reviewed_dimer_handoff", "print"}


@pytest.mark.parametrize("passed", [False, True])
def test_learning_start_preserves_preflight_and_attempt_spec(tmp_path, monkeypatch, passed):
    from scripts.ts_strategy_engine import workflow
    from scripts.neb_agent import submission

    calls = []
    def preflight(workdir, kind, *, learning_database):
        assert workdir == tmp_path and kind == "dimer" and learning_database == tmp_path / "registry"
        return {"passed": passed, "files": {"POSCAR": "hash", "OUTCAR": "ignored", "01/POSCAR": "image"}}
    monkeypatch.setattr(submission, "preflight", preflight)
    monkeypatch.setattr(workflow, "start_attempt", lambda database, spec: calls.append(spec) or "attempt")
    arguments = (tmp_path / "registry", tmp_path, "dimer", "attempt", "variant", "task", "calculation")
    if not passed:
        with pytest.raises(ValueError, match="VASP preflight failed"):
            workflow.start_vasp_attempt(*arguments)
        assert calls == []
    else:
        assert workflow.start_vasp_attempt(*arguments) == "attempt"
        assert calls == [{"attempt_id": "attempt", "variant_id": "variant", "task_id": "task", "kind": "dimer",
                          "parent_attempt_id": None, "source_calculation_id": "calculation",
                          "inputs": {"POSCAR": str(tmp_path / "POSCAR"), "01/POSCAR": str(tmp_path / "01/POSCAR")}}]


@pytest.mark.parametrize("bound,reviewed", [(True, True), (False, True), (True, False)])
def test_reviewed_dimer_handoff_keeps_binding_checks(tmp_path, monkeypatch, bound, reviewed):
    from scripts.ts_strategy_engine import handoff

    calls = []
    binding = {"valid": bound, "contract_sha256": "fixture"}
    monkeypatch.setattr(handoff, "load_contract", lambda path: {"reaction_atoms": [1, 2]})
    monkeypatch.setattr(handoff, "validate_path_binding", lambda path, contract: binding)
    monkeypatch.setattr(handoff, "validate_path_review", lambda path, generation: (reviewed, {}))
    monkeypatch.setattr(handoff, "prepare_dimer_handoff", lambda *args, **kwargs: calls.append((args, kwargs)) or tmp_path)
    kwargs = dict(contract_path=tmp_path / "contract", analysis=tmp_path / "analysis", path_review=tmp_path / "review",
                  source_image=tmp_path / "source", previous_image=tmp_path / "before", next_image=tmp_path / "after",
                  destination=tmp_path / "destination", dry_run=True, gate_decision=tmp_path / "gate", gate_state_sha256="hash")
    if not bound or not reviewed:
        with pytest.raises(SystemExit, match="contract-bound path generation"):
            handoff.prepare_reviewed_dimer_handoff(**kwargs)
        assert not calls
    else:
        assert handoff.prepare_reviewed_dimer_handoff(**kwargs) == tmp_path
        assert calls[0][1] == {"analysis_path": kwargs["analysis"], "path_review_path": kwargs["path_review"],
                               "reaction_indices": [1, 2], "contract_binding": binding,
                               "gate_decision": kwargs["gate_decision"], "gate_state_sha256": "hash"}


def test_active_learning_discovery_rejects_ambiguity_and_preserves_contract_fallback(tmp_path, monkeypatch):
    from scripts.ts_strategy_engine import active_learning_state as state

    with pytest.raises(FileNotFoundError, match="no GPU candidate"):
        state._discover_candidate_manifest(tmp_path)
    manifest = tmp_path / "output/job_1/gpu_result_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    assert state._discover_candidate_manifest(tmp_path) == manifest
    contract = tmp_path / "contract/reaction.yaml"
    contract.parent.mkdir()
    contract.write_text("fixture")
    calls = []
    monkeypatch.setattr(state, "initialize_workflow", lambda *args, **kwargs: calls.append((args, kwargs)) or {"fixture": True})
    assert state.initialize_from_ts_workdir(tmp_path, tmp_path / "policy", dry_run=True) == {"fixture": True}
    assert calls == [((manifest, tmp_path, contract, tmp_path / "policy", tmp_path / "active_learning"), {"dry_run": True})]
    second = tmp_path / "output/job_2/gpu_result_manifest.json"
    second.parent.mkdir()
    second.write_text("{}")
    with pytest.raises(ValueError, match="multiple GPU candidate"):
        state.initialize_from_ts_workdir(tmp_path, tmp_path / "policy")
    assert len(calls) == 1


def test_retrieval_application_preserves_diagnostic_and_fail_closed_outputs(tmp_path):
    import json
    from scripts.catalysis_retrieval.workflow import search_records
    from tests.test_catalysis_retrieval import record

    source = tmp_path / "records.jsonl"
    source.write_text(json.dumps(record()) + "\n", encoding="utf-8")
    result = search_records(source, query="Fe CO", lexical_only=True)
    assert result["status"] == "DIAGNOSTIC_ONLY" and result["production_ready"] is False
    assert result["scientific_acceptance"] is False and result["status_scope"] == "retrieval_ranking_only"
    source.write_text(json.dumps(record(source_url="https://example.com/invalid")) + "\n", encoding="utf-8")
    result = search_records(source, query="Fe CO", lexical_only=True)
    assert result["status"] == "STOP"
    assert "source_url_not_allowed" in result["validation_failures"][0]["errors"]
