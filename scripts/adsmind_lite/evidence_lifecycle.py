"""External claim provenance and review stages, consumed by the evidence gate.

Snapshots and reviews are supplied evidence, never proof obtained from ranking.
This module has no network, registry, execution, or scientific-result authority.
"""
from __future__ import annotations

import hashlib

from scripts.artifact_io import sha256_json
from scripts.provenance_fields import required_text, timestamp
from scripts.scientific_validation import finite_number, integer_number, validate_finite_tree

STATES = ("IMPORTED", "SCHEMA_VALID", "SOURCE_VERIFIED", "CONTENT_BOUND", "REVIEWED", "TRANSFERABLE")
PROVENANCE_TYPES = {
    "literature_claim", "expert_opinion", "model_prediction",
    "calculated_result", "reported_experimental_value",
}


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_subject(evidence: dict) -> str:
    """Bind review to claim, source and extracted content, excluding review itself."""
    return sha256_json({key: evidence.get(key) for key in ("claim", "source", "content")})


def _schema(evidence: dict) -> None:
    claim = evidence["claim"]
    if claim["type"] not in PROVENANCE_TYPES:
        raise ValueError("unsupported provenance type; no scientific_fact coercion")
    if claim["type"] == "model_prediction":
        from scripts.prediction_provenance import validate_prediction

        validate_prediction(claim["prediction_provenance"])
    for key in ("id", "statement", "source_reference", "status", "evidence_relationship", "scope", "domain"):
        required_text(claim[key], f"claim.{key}")
    if "confidence" in claim:
        confidence = finite_number(claim["confidence"], "claim.confidence", nonnegative=True)
        if confidence > 1:
            raise ValueError("claim.confidence exceeds one")
    validate_finite_tree(evidence)


def _source(evidence: dict) -> None:
    source = evidence["source"]
    required_text(source["identity"], "source.identity")
    reference = required_text(source["reference"], "source.reference")
    if reference != evidence["claim"]["source_reference"]:
        raise ValueError("claim source reference mismatch")
    timestamp(source["retrieved_at"], "source.retrieved_at")
    snapshot = source["snapshot"]
    text = required_text(snapshot["text"], "source snapshot")
    if text_digest(text) != snapshot["sha256"]:
        raise ValueError("source snapshot hash mismatch")
    if source["immutable_reference"] != f"{reference}#sha256={snapshot['sha256']}":
        raise ValueError("source immutable reference mismatch")


def _content(evidence: dict) -> None:
    content = evidence["content"]
    text = required_text(content["text"], "extracted content")
    start = integer_number(content["start"], "content.start", nonnegative=True)
    end = integer_number(content["end"], "content.end", positive=True)
    source = evidence["source"]["snapshot"]["text"]
    if end <= start or end > len(source) or source[start:end] != text:
        raise ValueError("content source span mismatch")
    if content["sha256"] != text_digest(text):
        raise ValueError("content hash mismatch")


def _review(evidence: dict) -> None:
    review = evidence["review"]
    required_text(review["reviewer"], "review.reviewer")
    reviewed_at = timestamp(review["reviewed_at"], "review.reviewed_at")
    if reviewed_at < timestamp(evidence["source"]["retrieved_at"], "source.retrieved_at"):
        raise ValueError("review predates retrieval")
    if review["decision"] not in {"accepted", "rejected", "needs_revision"}:
        raise ValueError("invalid review decision")
    if review["scope"] != evidence["claim"]["scope"]:
        raise ValueError("review scope mismatch")
    if review["subject_sha256"] != review_subject(evidence):
        raise ValueError("review subject binding mismatch")


def _transfer(evidence: dict, target: dict | None) -> None:
    if not isinstance(target, dict) or not target:
        raise ValueError("transfer requires an explicit target")
    transfer = evidence["transfer"]
    claim = evidence["claim"]
    if evidence["review"]["decision"] != "accepted":
        raise ValueError("transfer requires accepted review")
    if transfer["review_sha256"] != sha256_json(evidence["review"]):
        raise ValueError("transfer review binding mismatch")
    if transfer["domain"] != claim["domain"] or target.get("domain") != claim["domain"]:
        raise ValueError("scientific domain mismatch")
    if target.get("scope") != claim["scope"]:
        raise ValueError("transfer scope mismatch")
    compatibility = transfer["compatibility"]
    if not isinstance(compatibility, dict) or not compatibility:
        raise ValueError("transfer compatibility is required")
    if compatibility != target.get("compatibility"):
        raise ValueError("transfer compatibility mismatch")
    if compatibility != claim.get("compatibility"):
        raise ValueError("compatibility was not part of the reviewed claim")
    for key, value in compatibility.items():
        required_text(key, "compatibility key")
        if value is None or value == "" or value == [] or value == {}:
            raise ValueError("empty transfer compatibility")
    # Review never changes the provenance type or turns predictions into results.
    if claim["type"] in {"model_prediction", "expert_opinion"} and claim["scope"] != "candidate_guidance":
        raise ValueError("prediction/opinion is limited to candidate guidance")


def assess_evidence(evidence: dict, *, target: dict | None = None) -> dict:
    """Derive the highest supported stage; ignore all supplied stage/PASS flags."""
    state = "IMPORTED"
    for next_state, check in zip(STATES[1:], (_schema, _source, _content, _review, _transfer)):
        try:
            check(evidence, target) if next_state == "TRANSFERABLE" else check(evidence)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            return {"state": state, "blocker": str(exc), "accepted": False}
        state = next_state
    return {"state": state, "blocker": None, "accepted": True}


def require_transferable(evidence: dict, target: dict) -> dict:
    result = assess_evidence(evidence, target=target)
    if result["state"] != "TRANSFERABLE":
        raise ValueError(f"evidence {result['state']}: {result['blocker']}")
    return result


def record_subject(record: dict) -> str:
    """Identity of a retrieved record excluding derived rankings and evidence."""
    return sha256_json({key: value for key, value in record.items()
                        if key not in {"embedding", "embedding_provenance", "evidence", "evidence_state"}})
