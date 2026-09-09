from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from hybrid_search import cosine_scores, semantic_scores, rank_records
from validate_records import validate_embedding
from scripts.adsmind_lite.evidence_lifecycle import assess_evidence, review_subject, record_subject, text_digest
from scripts.artifact_io import sha256_json
from scripts.prediction_provenance import prediction_metadata, validate_prediction
from scripts.scientific_validation import finite_array
from tests.evidence_fixtures import bound_evidence

TARGET = {"domain": "surface_adsorption", "scope": "motif_selection",
          "compatibility": {"species": "C", "surface": "Fe110"}}


def vector_record():
    record = {"id": "source-1", "title": "carbon", "summary": "synthetic carbon motif"}
    record["evidence"] = bound_evidence(record)
    record["embedding"] = [1., 0.]
    record["embedding_provenance"] = {
        "model": "test-model@v1", "generated_at": "2026-09-09T02:00:00Z", "dimension": 2,
        "record_sha256": record_subject(record), "content_sha256": record["evidence"]["content"]["sha256"],
    }
    return record


@pytest.mark.parametrize("missing,state", [("claim", "IMPORTED"), ("source", "SCHEMA_VALID"),
                                         ("content", "SOURCE_VERIFIED"), ("review", "CONTENT_BOUND"),
                                         ("transfer", "REVIEWED")])
def test_evidence_requires_each_stage(missing, state):
    evidence = bound_evidence()
    del evidence[missing]
    evidence["state"] = "TRANSFERABLE"
    evidence["reviewed"] = True
    assert assess_evidence(evidence, target=TARGET)["state"] == state


def test_reviewed_transfer_requires_actual_compatibility():
    evidence = bound_evidence()
    assert assess_evidence(evidence, target=TARGET)["state"] == "TRANSFERABLE"
    assert assess_evidence(evidence)["state"] == "REVIEWED"
    evidence["transfer"]["compatibility"] = {"surface": "Pt111"}
    assert assess_evidence(evidence, target=TARGET)["state"] == "REVIEWED"


@pytest.mark.parametrize("field", ["reviewer", "reviewed_at", "decision", "scope", "subject_sha256"])
def test_missing_review_metadata_cannot_review(field):
    evidence = bound_evidence()
    del evidence["review"][field]
    assert assess_evidence(evidence)["state"] == "CONTENT_BOUND"


def test_rejected_review_is_reviewed_but_not_accepted():
    evidence = bound_evidence()
    evidence["review"]["decision"] = "rejected"
    evidence["transfer"]["review_sha256"] = sha256_json(evidence["review"])
    assert assess_evidence(evidence, target=TARGET) == {
        "state": "REVIEWED", "blocker": "transfer requires accepted review", "accepted": False}


@pytest.mark.parametrize("kind", ["model_prediction", "expert_opinion"])
def test_review_does_not_turn_prediction_or_opinion_into_result(kind):
    evidence = bound_evidence(kind=kind)
    assert assess_evidence(evidence, target=TARGET)["state"] == "REVIEWED"
    evidence["claim"]["type"] = "scientific_fact"
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    assert assess_evidence(evidence)["state"] == "IMPORTED"


def test_source_exists_without_extraction_cannot_be_reviewed():
    evidence = bound_evidence()
    evidence["content"]["text"] = "unrelated extracted text"
    evidence["content"]["sha256"] = text_digest(evidence["content"]["text"])
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    assert assess_evidence(evidence)["state"] == "SOURCE_VERIFIED"


def test_embedding_exists_but_source_missing_rejected():
    record = vector_record()
    del record["evidence"]["source"]
    with pytest.raises(ValueError, match="source"):
        validate_embedding(record)


@pytest.mark.parametrize("vector", [[float("nan"), 0], [float("inf"), 0], [float("-inf"), 0], [], [0, 0], [1], [[1], [2]], [True, 0]])
def test_invalid_embedding_rejected(vector):
    record = vector_record()
    record["embedding"] = vector
    with pytest.raises(ValueError):
        validate_embedding(record)


@pytest.mark.parametrize("field", ["model", "generated_at", "record_sha256", "content_sha256", "dimension"])
def test_embedding_metadata_required(field):
    record = vector_record()
    del record["embedding_provenance"][field]
    with pytest.raises((ValueError, KeyError)):
        validate_embedding(record)


def test_precomputed_ranking_never_approves(tmp_path):
    record = vector_record()
    del record["evidence"]["review"]
    query = "carbon"
    path = tmp_path / "query.json"
    path.write_text(json.dumps({"query": query, "embedding": [1, 0], "embedding_provenance": {
        "model": "test-model@v1", "generated_at": "2026-09-09T02:00:00Z", "dimension": 2,
        "query_sha256": text_digest(query)}}))
    scores, backend = semantic_scores([record], ["carbon"], query, "test-model@v1", path)
    assert backend == "precomputed-source-bound"
    ranked = rank_records([record], query, scores, .5, .5, 1)
    assert ranked[0]["evidence_state"] == "CONTENT_BOUND"
    assert ranked[0]["scientific_acceptance"] is False
    with pytest.raises(ValueError, match="identity"):
        semantic_scores([record], ["carbon"], "different query", "test-model@v1", path)


def test_cosine_large_finite_values_do_not_overflow():
    assert cosine_scores(np.array([1e308, 1e308]), np.array([[1e308, 1e308]]))[0] == pytest.approx(1)


def prediction():
    return prediction_metadata(model_name="GAME-Net", model_version="v1", input_fingerprint="a" * 64,
                               source_reference="synthetic-input", generated_at="2026-09-09T00:00:00Z",
                               uncertainty={"status": "estimated", "value": .2, "unit": "eV", "method": "ensemble"})


def test_prediction_provenance_and_uncertainty_required():
    record = prediction()
    for field in ("uncertainty", "model_name", "model_version", "input_fingerprint", "generated_at"):
        invalid = copy.deepcopy(record)
        del invalid[field]
        with pytest.raises(ValueError):
            validate_prediction(invalid)
    record["scientific_acceptance"] = True
    with pytest.raises(ValueError, match="acceptance"):
        validate_prediction(record)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_uncertainty(value):
    record = prediction()
    record["uncertainty"]["value"] = value
    with pytest.raises(ValueError):
        validate_prediction(record)


def test_ragged_descriptors_rejected():
    with pytest.raises(ValueError):
        finite_array([[1, 2], [3]], "descriptors", shape=(None, None))


def test_external_ready_payload_cannot_bypass_evidence_owner():
    from pathlib import Path
    from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_species

    root = Path(__file__).resolve().parents[1]
    rules = load_prescreen_rules(str(root / "configs/adsmind_lite/prescreen_rules.yaml"))
    forged = {"species": "unseen", "decision": "READY", "candidate_count": 1,
              "candidates": [{"build_ready": True}]}
    with pytest.raises(ValueError, match="source evidence"):
        plan_species("unseen", rules, external_plans={"unseen": forged})


def test_ranking_and_prediction_have_no_acceptance_side_effects():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    expected = {"assess_evidence": "scripts/adsmind_lite/evidence_lifecycle.py",
                "validate_prediction": "scripts/prediction_provenance.py",
                "finite_array": "scripts/scientific_validation.py",
                "_source_labels": "scripts/matris_training_data.py",
                "assert_dataset_splits_disjoint": "scripts/matris_training_exclusions.py"}
    owners = {name: [] for name in expected}
    for path in (root / "scripts").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name in owners:
                owners[node.name].append(path.relative_to(root).as_posix())
    assert owners == {name: [path] for name, path in expected.items()}
    for relative in ("skills/catalysis-data-retrieval/scripts/hybrid_search.py", "scripts/prediction_provenance.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert not calls & {"require_transferable", "apply_registry_batch", "record_ts_validation", "submit"}
