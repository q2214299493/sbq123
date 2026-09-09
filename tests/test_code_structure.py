from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = (ROOT / "scripts", ROOT / "skills", ROOT / "modules" / "fe_convergence_baseline")


def current_python_files() -> list[Path]:
    return sorted(path for root in CODE_ROOTS for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_current_python_files_are_not_exact_duplicates() -> None:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in current_python_files():
        groups[hashlib.sha256(path.read_bytes()).hexdigest()].append(path)
    assert [paths for paths in groups.values() if len(paths) > 1] == []


def test_nontrivial_function_bodies_are_not_duplicated() -> None:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in current_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or len(node.body) < 3:
                continue
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            digest = hashlib.sha256(ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False).encode()).hexdigest()
            groups[digest].append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
    assert [locations for locations in groups.values() if len(locations) > 1] == []


def test_adsmind_core_remains_a_compatibility_facade() -> None:
    path = ROOT / "scripts" / "adsmind_lite" / "core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in tree.body)
    expected_modules = {
        "adsmind_common.py",
        "candidate_export.py",
        "candidate_generation.py",
        "relaxed_analysis.py",
        "site_detection.py",
        "state_deduplication.py",
    }
    assert expected_modules <= {child.name for child in path.parent.iterdir()}
    exported = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    assert isinstance(exported, ast.List)
    names = {element.value for element in exported.elts if isinstance(element, ast.Constant)}
    assert len(names) <= 15
    assert {"validate_one_candidate", "connectivity_edges", "manifest_site_record"}.isdisjoint(names)


def test_high_risk_public_geometry_functions_document_units_and_indices() -> None:
    contracts = {
        ROOT / "scripts" / "adsmind_lite" / "candidate_generation.py": {
            "compose_candidate_structure": ("Å", "0-based"),
            "candidate_metadata": ("Å", "0-based"),
        },
        ROOT / "scripts" / "adsmind_lite" / "relaxed_analysis.py": {
            "connectivity_edges": ("Å", "0-based"),
            "structure_indices": ("0-based",),
            "minimum_cross_distance": ("Å", "0-based"),
        },
        ROOT / "scripts" / "adsorption" / "c2_coads_geometry.py": {
            "h_lb_h_c2_cart": ("Cartesian", "Å"),
            "diagonal_c2_cart": ("Cartesian", "Å", "PBC"),
            "combine": ("Cartesian", "Å"),
        },
    }
    for path, functions in contracts.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name, required_terms in functions.items():
            docstring = ast.get_docstring(nodes[name]) or ""
            assert all(term in docstring for term in required_terms), f"{path.name}:{name} missing {required_terms}"


def test_shared_geometry_and_handoff_rules_have_one_owner() -> None:
    candidate_generation = (ROOT / "scripts" / "adsmind_lite" / "candidate_generation.py").read_text(encoding="utf-8")
    assert "def anchor_position_for_site" not in candidate_generation
    for name in ("crop_neb_path.py", "prepare_restart.py"):
        text = (ROOT / "scripts" / "neb_agent" / name).read_text(encoding="utf-8")
        assert "preferred_image_structure(" in text
    handoff = (ROOT / "scripts" / "ts_strategy_engine" / "handoff.py").read_text(encoding="utf-8")
    assert "preferred_image_structure(" in handoff
    assert "prepare_ts_handoff(" in handoff
    validation = (ROOT / "scripts" / "ts_validation" / "prepare_vfa_from_ts_image.py").read_text(encoding="utf-8")
    assert "prepare_ts_handoff(" in validation
    assert "shutil.copy2" not in validation


def test_ts_engine_layers_do_not_recombine() -> None:
    engine = ROOT / "scripts" / "ts_strategy_engine"
    assert not (engine / "library.py").exists()

    cli = (engine / "cli.py").read_text(encoding="utf-8")
    workflow = (engine / "workflow.py").read_text(encoding="utf-8")
    evidence = (engine / "evidence.py").read_text(encoding="utf-8")
    templates = (engine / "templates.py").read_text(encoding="utf-8")
    registry = (engine / "registry.py").read_text(encoding="utf-8")

    assert "import sqlite3" not in cli
    assert "argparse" not in workflow
    assert "argparse" not in evidence
    assert "argparse" not in templates
    assert "from .registry import" in evidence
    assert "from .registry import" in templates
    assert "from scripts.registry_schema import" in registry
    line_counts = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in engine.glob("*.py")
    }
    assert line_counts["execution_gate.py"] <= 160
    assert max(line_counts.values()) <= 400


def test_execution_decision_imports_only_pure_dependencies() -> None:
    path = ROOT / "scripts/ts_strategy_engine/execution_decision.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    permitted = {
        "__future__": {"annotations"},
        "dataclasses": {"dataclass"},
        "datetime": {"datetime", "timezone"},
        "typing": {"Any"},
        "scripts.artifact_io": {"sha256_json"},
    }
    # Inspect nested imports too. Evidence validators and whole I/O modules
    # cannot leak in through an alias or a function-local import.
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import), "Pure decisions use explicit pure imports"
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module in permitted
            assert {alias.name for alias in node.names} <= permitted[node.module]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "__import__", "eval", "exec"}


def test_execution_decision_builders_do_not_access_filesystem(monkeypatch) -> None:
    import builtins
    import io
    import os

    from scripts.ts_strategy_engine import execution_decision as decisions

    def reject_io(*args, **kwargs):
        raise AssertionError("Decision construction must not inspect or modify files")

    evidence = {"thresholds": {}, "source_bindings": {"review": {"path": "/missing/review.json"}}}
    with monkeypatch.context() as patch:
        for module in (builtins, io, os):
            patch.setattr(module, "open", reject_io)
        for name in ("open", "read_text", "read_bytes", "write_text", "write_bytes",
                     "resolve", "stat", "lstat", "exists", "is_file", "is_dir",
                     "iterdir", "glob", "rglob", "mkdir", "unlink", "rename", "replace"):
            patch.setattr(Path, name, reject_io)
        for action in decisions.ACTIONS:
            result = decisions.make_decision("READY", [], evidence, (action,), "Review")
            quality_result = decisions.decision_from_quality({}, evidence, (action,), "Review")
            readiness = decisions.ScientificReadiness("READY", (), (action,))
            assert result["ALLOWED_ACTIONS"] == [action]
            assert quality_result["ALLOWED_ACTIONS"] == [action]
            assert readiness.eligible_actions == (action,)
            assert "execution_authorization" not in result


def test_neb_authorization_application_and_submission_have_single_owners() -> None:
    owners: dict[str, list[str]] = defaultdict(list)
    for path in current_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in {"require_execution_authorization", "bind_execution"}:
                    owners[node.name].append(path.relative_to(ROOT).as_posix())
                # The TS/NEB lifecycle has one submit API. Convergence campaign
                # setup has a separate pre-existing scope outside this lifecycle.
                if node.name == "submit" and path.parent.name in {"neb_agent", "ts_strategy_engine", "ts_validation"}:
                    owners["submit"].append(path.relative_to(ROOT).as_posix())
            if isinstance(node, ast.Constant) and node.value == "bsub script.lsf":
                owners["vasp_dispatch"].append(path.relative_to(ROOT).as_posix())
    assert owners == {
        "require_execution_authorization": ["scripts/ts_strategy_engine/execution_evidence.py"],
        "bind_execution": ["scripts/ts_strategy_engine/execution_evidence.py"],
        "submit": ["scripts/neb_agent/submission.py"],
        "vasp_dispatch": ["scripts/neb_agent/submission.py"],
    }
    from scripts.ts_strategy_engine import execution_evidence, execution_gate

    assert execution_gate._bind_execution is execution_evidence.bind_execution
