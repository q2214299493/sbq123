from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, write_json
from scripts.ts_strategy_engine.scientific_claims import _verify_scientific_owner
from test_b21_scientific_acceptance import bound_case


def test_claim_reuses_bound_formal_dimer_soft_review(tmp_path: Path):
    case = bound_case(tmp_path, soft_decision="accept_for_ts_validation")
    path = case["vfa"] / "vfa_analysis.json"
    _verify_scientific_owner(load_json_object(path), path)


def test_claim_does_not_promote_frequency_only_review(tmp_path: Path):
    case = bound_case(tmp_path, soft_decision="allow_frequency_handoff")
    path = case["vfa"] / "vfa_analysis.json"
    with pytest.raises(ValueError, match="not accepted"):
        _verify_scientific_owner(load_json_object(path), path)


def test_claim_rejects_changed_bound_soft_review(tmp_path: Path):
    case = bound_case(tmp_path, soft_decision="accept_for_ts_validation")
    path = case["vfa"] / "vfa_analysis.json"
    review = load_json_object(case["soft"])
    review["notes"] = "Changed after the frequency summary was bound"
    write_json(case["soft"], review)
    with pytest.raises(ValueError, match="not accepted"):
        _verify_scientific_owner(load_json_object(path), path)


def test_claim_rejects_missing_bound_soft_review(tmp_path: Path):
    case = bound_case(tmp_path, soft_decision="accept_for_ts_validation")
    path = case["vfa"] / "vfa_analysis.json"
    case["soft"].unlink()
    with pytest.raises((ValueError, OSError)):
        _verify_scientific_owner(load_json_object(path), path)
