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
