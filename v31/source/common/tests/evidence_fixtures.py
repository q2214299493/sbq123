"""Synthetic source snapshots and explicit review records for governance tests."""
from __future__ import annotations

import json

from scripts.adsmind_lite.evidence_lifecycle import record_subject, review_subject, text_digest
from scripts.artifact_io import sha256_json


def bound_evidence(record: dict | None = None, *, kind="literature_claim", scope="motif_selection",
                   domain="surface_adsorption", compatibility=None) -> dict:
    compatibility = compatibility or {"species": "C", "surface": "Fe110"}
    text = json.dumps(record or {"claim": "synthetic source passage"}, sort_keys=True)
    reference = (record or {}).get("source_url", (record or {}).get("publisher_url", "https://example.org/synthetic/source"))
    evidence = {
        "claim": {"id": "claim-1", "type": kind, "statement": "Synthetic reviewed claim",
                  "source_reference": reference, "status": "reported", "evidence_relationship": "extracted_from_source",
                  "domain": domain, "scope": scope, "compatibility": compatibility},
        "source": {"identity": "synthetic-source-1", "reference": reference,
                   "retrieved_at": "2026-09-09T00:00:00Z", "snapshot": {"text": text, "sha256": text_digest(text)},
                   "immutable_reference": f"{reference}#sha256={text_digest(text)}"},
        "content": {"text": text, "sha256": text_digest(text), "start": 0, "end": len(text)},
    }
    if record is not None:
        evidence["claim"]["record_sha256"] = record_subject(record)
    if kind == "model_prediction":
        from scripts.prediction_provenance import prediction_metadata

        evidence["claim"]["prediction_provenance"] = prediction_metadata(
            model_name="synthetic model", model_version="v1", input_fingerprint=text_digest(text),
            source_reference=reference, generated_at="2026-09-09T00:00:00Z",
            uncertainty={"status": "unavailable", "reason": "synthetic fixture has no estimator"},
        )
    evidence["review"] = {"reviewer": "synthetic reviewer", "reviewed_at": "2026-09-09T01:00:00Z",
                          "decision": "accepted", "scope": scope, "subject_sha256": review_subject(evidence)}
    evidence["transfer"] = {"domain": domain, "compatibility": compatibility,
                            "review_sha256": sha256_json(evidence["review"])}
    return evidence
