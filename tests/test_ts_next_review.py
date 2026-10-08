"""Local-only tests for bounded next-review advice; no registry or calculation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_json, write_json
from scripts.ts_strategy_engine import learning_cli
from scripts.ts_strategy_engine.next_review import recommend_next_reviews


def sample(tmp_path: Path):
    rows = [
        ("geometry", "hypothesis", "review_path_repair_without_assuming_model_error"),
        ("optimizer", "confirmed", "diagnose_optimizer_and_path"),
        ("scf", "unknown", "incar_custodian_diagnosis"),
        ("runtime", "hypothesis", "repair_runtime_without_training"),
    ]
    cases, answers = [], []
    for index, (failure_class, certainty, route) in enumerate(rows):
        case_id = f"case-{index}"
        case = {"case_id": case_id, "group_id": f"group-{index}",
                "question": "What needs review?",
                "evidence": [{"evidence_id": "e1", "pointer": "/message",
                              "value": "observed symptom", "source_sha256": "a" * 64}]}
        case["input_sha256"] = sha256_json(case)
        cases.append(case)
        answers.append({"case_id": case_id, "input_sha256": case["input_sha256"],
                        "failure_class": failure_class,
                        "causal_claim": None if certainty == "unknown" else "Specific cause to review",
                        "causal_status": certainty,
                        "causal_evidence_ids": [] if certainty == "unknown" else ["e1"],
                        "next_review": route, "evidence_ids": ["e1"]})
    public = {"schema_version": 2, "cases": cases}
    answer_set = {"schema_version": 2, "public_sha256": sha256_json(public), "answers": answers}
    public_path, answer_path = tmp_path / "public.json", tmp_path / "answers.json"
    write_json(public_path, public)
    write_json(answer_path, answer_set)
    return public_path, answer_path, sha256_json(public)


def test_recommendation_preserves_claim_and_only_hints_existing_strategy_fields(tmp_path):
    public, answers, frozen_hash = sample(tmp_path)
    result = recommend_next_reviews(public, answers, tmp_path / "out.json", frozen_hash)
    assert result["status"] == "ADVISORY_ONLY_NOT_AUTHORIZED"
    assert result["public_source_files_reverified"] is False
    assert result["causal_claims_scientifically_validated"] is False
    assert result["ts_strategy_changes_authorized"] is False
    by_id = {r["case_id"]: r for r in result["recommendations"]}
    assert by_id["case-0"]["ts_strategy_fields_to_review"] == ["interpolation_strategy", "initial_images"]
    assert by_id["case-1"]["ts_strategy_fields_to_review"] == ["candidate_method"]
    assert by_id["case-2"]["ts_strategy_fields_to_review"] == []
    assert by_id["case-2"]["review_focus"] == "collect_cause_specific_evidence"
    assert by_id["case-3"]["ts_strategy_fields_to_review"] == []
    assert all(r["requires_owning_review"] and not r["automatic_execution"] for r in by_id.values())
    with pytest.raises(FileExistsError):
        recommend_next_reviews(public, answers, tmp_path / "out.json", frozen_hash)


@pytest.mark.parametrize("damage", ["public_changed", "source_sha", "answer_missing", "answer_extra",
                                      "answer_duplicate", "wrong_input", "wrong_route", "unknown_claim",
                                      "bad_causal_ids", "old_schema", "duplicate_case"])
def test_fail_closed_without_writing_advice(tmp_path, damage):
    public_path, answers_path, frozen_hash = sample(tmp_path)
    public = json.loads(public_path.read_text(encoding="utf-8"))
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    if damage == "public_changed":
        public["cases"][0]["evidence"][0]["value"] = "tampered"
    elif damage == "source_sha":
        public["cases"][0]["evidence"][0]["source_sha256"] = "not-hash"
        public["cases"][0]["input_sha256"] = sha256_json({k: v for k, v in public["cases"][0].items() if k != "input_sha256"})
        answers["answers"][0]["input_sha256"] = public["cases"][0]["input_sha256"]
        answers["public_sha256"] = sha256_json(public)
    elif damage == "answer_missing":
        answers["answers"].pop()
    elif damage == "answer_extra":
        answers["answers"].append({**answers["answers"][0], "case_id": "unexpected"})
    elif damage == "answer_duplicate":
        answers["answers"].append(answers["answers"][0].copy())
    elif damage == "wrong_input":
        answers["answers"][0]["input_sha256"] = "f" * 64
    elif damage == "wrong_route":
        answers["answers"][0]["next_review"] = "incar_custodian_diagnosis"
    elif damage == "unknown_claim":
        answers["answers"][2]["causal_claim"] = "guessed reason"
    elif damage == "bad_causal_ids":
        answers["answers"][0]["causal_evidence_ids"] = ["invented"]
    elif damage == "old_schema":
        answers["schema_version"] = 1
    else:
        public["cases"].append(public["cases"][0].copy())
        answers["public_sha256"] = sha256_json(public)
    write_json(public_path, public)
    write_json(answers_path, answers)
    report_path = tmp_path / "result.json"
    with pytest.raises(ValueError):
        recommend_next_reviews(public_path, answers_path, report_path, frozen_hash)
    assert not report_path.exists()


def test_cli_exposes_advisory_without_opening_registry_or_executor(monkeypatch, tmp_path, capsys):
    public, answers, frozen_hash = sample(tmp_path)
    def forbidden(*_a, **_kw):
        pytest.fail("no registry or execution side effects")
    monkeypatch.setattr("scripts.ts_strategy_engine.learning_store.read_events", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.registry.open_registry", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.execution_gate.decide_execution", forbidden)
    report = tmp_path / "advice.json"
    learning_cli.main(["advise-next", "--public", str(public), "--answers", str(answers),
                       "--expected-public-sha256", frozen_hash, "--report", str(report)])
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "ADVISORY_ONLY_NOT_AUTHORIZED"
    assert "ADVISORY_ONLY_NOT_AUTHORIZED" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        learning_cli.main(["--output", str(tmp_path / "bad.json"), "advise-next",
                           "--public", str(public), "--answers", str(answers),
                           "--expected-public-sha256", frozen_hash,
                           "--report", str(tmp_path / "not-created.json")])
    assert exc.value.code == 2
    assert not (tmp_path / "not-created.json").exists()
