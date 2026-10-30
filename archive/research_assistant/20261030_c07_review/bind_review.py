"""Bind an actual RSI research review to an unchanged SPC plan and real sources.

This is a review sidecar and supplemental evidence store, not SPC approval or
its approval-dependent plan-revision API. No production SPC state is modified.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.research_assistant.spc_adapter import load_spc


def bind(parent, review_path, spc_root, output):
    models = load_spc(spc_root)
    from spc.interpretation.validators import validate_evidence_packet_integrity
    from spc.repositories import FilesystemEvidenceStore, SourceEvidenceStore
    from spc.serialization import content_hash, load_model
    review = load_json_object(review_path)
    plan_path = parent / "plan-01.json"
    plan = load_model(plan_path, models.ScientificQuestionPlan)
    compilation = load_model(parent / "compilation-receipt-01.json", models.PlanCompilationReceipt)
    if sha256_file(plan_path) != review["base_plan_sha256"] or plan.plan_id != review["base_plan_id"] \
            or compilation.plan_hash != content_hash(plan):
        raise ValueError("review does not bind the actual original materialized plan")
    if not (parent / ".spc").is_dir():
        raise ValueError("original evidence store is missing")
    original = FilesystemEvidenceStore(parent / ".spc")
    context = load_model(parent / "context.json", models.ScientificContextPacket)
    packet = load_model(parent / "evidence-packet.json", models.ScientificEvidencePacket)
    integrity = validate_evidence_packet_integrity(packet, context, original)
    if not integrity.valid:
        raise ValueError("original SPC source packet failed current owner integrity validation")
    output.mkdir(parents=True, exist_ok=False)
    (output / "binder.original.py").write_bytes(Path(__file__).read_bytes())
    store = SourceEvidenceStore(output / ".spc")
    refs = [*review["review_sources"], {"evidence_id": "ev-c07-review-outcome", "path": str(review_path),
             "sha256": sha256_file(review_path), "source_type": "internal_note"}]
    bindings = []
    for ref in refs:
        path = Path(ref["path"])
        if sha256_file(path) != ref["sha256"]:
            raise ValueError("supplemental source changed before ingestion")
        source = store.ingest(path, "source-" + ref["evidence_id"], "v1",
            source_role="internal_researcher", source_type=ref["source_type"])
        text = path.read_bytes().decode("utf-8")
        span = models.EvidenceSpan(evidence_id=ref["evidence_id"], source_id=source.source_id,
            source_version=source.version, content_sha256=source.content_sha256,
            start_offset=0, end_offset=len(text), text=text)
        store.add_evidence(span)
        store.verify_evidence_integrity(span)
        if sha256_file(path) != ref["sha256"]:
            raise ValueError("supplemental source changed during ingestion")
        bindings.append({**ref, "source_id": source.source_id, "source_version": source.version,
                         "start_offset": 0, "end_offset": len(text), "integrity_verified": True})
    shutil.copyfile(plan_path, output / "parent-plan.original.json")
    if sha256_file(plan_path) != review["base_plan_sha256"]:
        raise ValueError("parent plan changed during source review binding")
    receipt = {"status": "SOURCE_BOUND_RESEARCH_REVIEW", "plan_id": plan.plan_id,
        "parent_plan_sha256": sha256_file(plan_path), "parent_plan_content_hash": content_hash(plan),
        "parent_compilation_receipt_sha256": sha256_file(parent / "compilation-receipt-01.json"),
        "parent_evidence_packet_sha256": sha256_file(parent / "evidence-packet.json"),
        "parent_source_integrity": integrity.model_dump(mode="json"),
        "review_path": str(review_path), "review_sha256": sha256_file(review_path),
        "supplemental_bindings": bindings,
        "spc_source_hashes": {str(path.relative_to(spc_root)): sha256_file(path) for path in [
            spc_root / "src/spc/models.py", spc_root / "src/spc/repositories.py",
            spc_root / "src/spc/serialization.py", spc_root / "src/spc/interpretation/validators.py"]},
        "scientific_acceptance": False, "approval_granted": False, "execution_authorized": False,
        "researcher_adoption": None, "human_review_seconds": None,
        "original_plan_unchanged": True, "production_spc_state_modified": False,
        "boundary": "RSI research-review sidecar, not a native SPC approval or formal revision. Current native revision requires independent approval records; none were fabricated."}
    write_json_exclusive(output / "review_binding_receipt.json", receipt)
    return {"status": receipt["status"], "supplemental_sources": len(bindings), "parent_integrity_valid": integrity.valid}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ["parent", "review", "spc-root", "output-dir"]:
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    print(bind(args.parent, args.review, args.spc_root, args.output_dir))
