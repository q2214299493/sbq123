"""Read-only saved advice and explicit workflow-policy selection; no execution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .next_review_core import build_next_reviews, review_field_orders as review_field_orders
from .strategy_learning import POLICY
from .workflow_improvement import select_policy


def recommend_next_reviews(public_path: Path, answers_path: Path, report_path: Path,
                           expected_public_sha256: str, *, workflow_store: Path | None = None,
                           workflow_policy: str | None = None, workflow_scope: str | None = None,
                           offline_evaluation: bool = False) -> dict[str, Any]:
    """Select only an explicitly requested policy, validate, and write output once."""
    public, answers = load_json_object(public_path), load_json_object(answers_path)
    orders, strategy_identity = None, None
    if workflow_store is not None or workflow_policy is not None or workflow_scope is not None or offline_evaluation:
        orders, strategy_identity = select_policy(workflow_store, workflow_policy, workflow_scope,
                                                  public, answers_path, offline_evaluation)
    report = build_next_reviews(public, answers, expected_public_sha256, sha256_file(answers_path),
                                sha256_file(POLICY), orders=orders, strategy_identity=strategy_identity)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(report_path, report)
    return report
