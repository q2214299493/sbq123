from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

from scripts.ts_strategy_engine import execution_decision, execution_gate


def test_legacy_execution_gate_public_imports_remain_available() -> None:
    legacy = importlib.import_module("scripts.ts_strategy_engine.execution_gate")
    for name in (
        "ACTIONS",
        "GATE_NAME",
        "INITIAL_SUBMISSIONS",
        "decide_execution",
        "require_action",
        "validate_decision",
    ):
        assert hasattr(legacy, name), name

    assert legacy.ACTIONS is execution_decision.ACTIONS
    assert legacy.GATE_NAME == execution_decision.GATE_NAME
    assert legacy.decide_execution is execution_gate.decide_execution
    assert legacy.require_action is execution_gate.require_action
    assert legacy.validate_decision is execution_gate.validate_decision
    assert not hasattr(legacy, "make_decision")
    assert not hasattr(legacy, "decision_from_quality")


def test_execution_gate_public_signatures_remain_compatible() -> None:
    decide = inspect.signature(execution_gate.decide_execution)
    assert list(decide.parameters) == [
        "geometry",
        "analysis",
        "thresholds",
        "climb",
        "path_reviewed",
        "path_quality",
        "preflight",
        "validation",
        "scheduler",
        "authorization",
        "source_bindings",
    ]
    assert decide.parameters["climb"].kind is inspect.Parameter.KEYWORD_ONLY
    assert decide.parameters["path_reviewed"].kind is inspect.Parameter.KEYWORD_ONLY
    for name in (
        "path_quality",
        "preflight",
        "validation",
        "scheduler",
        "authorization",
        "source_bindings",
    ):
        assert decide.parameters[name].default is None

    assert list(inspect.signature(execution_gate.require_action).parameters) == [
        "decision_path",
        "action",
        "current_state_sha256",
    ]
    assert list(inspect.signature(execution_gate.validate_decision).parameters) == [
        "decision"
    ]


def test_execution_gate_split_has_no_reverse_import() -> None:
    decision_path = Path(execution_decision.__file__)
    tree = ast.parse(decision_path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "scripts.ts_strategy_engine.execution_gate" not in imports
    assert "execution_gate" not in imports
