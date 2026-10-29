"""One-off real-source C3 plan receipt, using the installed SPC owners offline.

The definition supplies explicitly authored planning fields, never model answers
or scientific acceptance. Output is a new isolated evidence workspace and an
unapproved plan; this script has no scientific executor or approval provider.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.research_assistant.spc_adapter import export, load_spc


class SourceBindingProvider:
    """Only existing quote/claim extraction; source wording stays unresolved."""

    def __init__(self, interpretation_refs):
        self.interpretation_refs = set(interpretation_refs)

    def bind_evidence_repository(self, repository):
        self.repository = repository

    def interpret(self, context):
        from spc.interpretation.claim_extractor import extract_source_claims, extract_source_quotes
        from spc.models import EpistemicStatus, EvidenceAssessment, InterpretationProposal
        from spc.serialization import content_hash
        quotes = extract_source_quotes(context, self.repository)
        claims = extract_source_claims(context, quotes)
        claims = tuple(claim.model_copy(update={"epistemic_status": EpistemicStatus.SOURCE_INTERPRETATION})
            if claim.epistemic_status == "source_reported" and set(claim.evidence_refs) & self.interpretation_refs
            else claim for claim in claims)
        payload = {
            "context_id": context.context_id, "context_hash": context.content_hash,
            "provider_id": "rsi-real-source-quote-binding", "provider_version": "2",
            "source_quotes": quotes, "source_claims": claims,
            "reported_results": (), "method_facts": (), "model_facts": (),
            "evidence_assessments": tuple(EvidenceAssessment(
                assessment_id="assessment-" + content_hash({"claim_ref": claim.claim_id})[:24],
                claim_ref=claim.claim_id, supporting_evidence_refs=claim.evidence_refs,
                assessment="unresolved", limitations=("Provenance does not establish scientific acceptance.",),
                confidence_basis="Exact real source bytes and offsets, with no independent truth assessment."
            ) for claim in claims),
            "conflict_sets": (), "comparison_constraints": (), "evidence_gaps": (),
            "unknowns": tuple(row.statement for row in context.unknowns),
            "assumption_candidates": tuple(row.statement for row in context.assumptions),
            "capability_candidates": tuple(hit.record_id for hit in context.capability_hits),
        }
        return InterpretationProposal(proposal_id="interpretation-" + content_hash(payload)[:24], **payload)


def materialize(run, spc_root, definition_path, output):
    models = load_spc(spc_root)
    from spc.compiler import ScientificProblemCompiler
    from spc.interpretation import ScientificEvidencePacketBuilder
    from spc.planning import PlanningContextResolver
    from spc.repositories import KnowledgeRepositories, SourceEvidenceStore
    from spc.retrieval import ScientificContextBuilder
    from spc.serialization import content_hash, dump_json, load_model
    definition = load_json_object(definition_path)
    result = load_json_object(run / "research_result.json")
    if definition["research_result_sha256"] != sha256_file(run / "research_result.json"):
        raise ValueError("definition does not bind the exact current RSI result")
    output.mkdir(parents=True, exist_ok=False)
    (output / "helper.original.py").write_bytes(Path(__file__).read_bytes())
    write_json_exclusive(output / "definition.original.json", definition)
    store = SourceEvidenceStore(output / ".spc")
    source_rows = []
    for row in definition["source_spans"]:
        path = Path(row["path"])
        if sha256_file(path) != row["sha256"]:
            raise ValueError("source changed before ingestion: " + str(path))
        source = store.ingest(path, "source-" + row["evidence_id"], "v1",
                              source_role="internal_researcher", source_type="calculation_archive")
        text = path.read_bytes().decode("utf-8")
        start, end = row.get("start_offset", 0), row.get("end_offset", len(text))
        evidence = models.EvidenceSpan(evidence_id=row["evidence_id"], source_id=source.source_id,
            source_version=source.version, content_sha256=source.content_sha256,
            start_offset=start, end_offset=end, text=text[start:end])
        store.add_evidence(evidence)
        store.verify_evidence_integrity(evidence)
        if sha256_file(path) != row["sha256"]:
            raise ValueError("source changed during ingestion")
        source_rows.append({**row, "source_id": source.source_id, "source_version": source.version,
                            "start_offset": start, "end_offset": end})
    context = ScientificContextBuilder().build(definition["planning_request"], "base",
        state_dir=output / ".spc", knowledge_dir=output / "knowledge")
    interpretations = [row["evidence_id"] for row in definition["source_spans"]
                       if row.get("epistemic_scope") == "historical_interpretation"]
    packet = ScientificEvidencePacketBuilder(SourceBindingProvider(interpretations)).build(context, store)
    planning = PlanningContextResolver().resolve(context, packet, KnowledgeRepositories(output / "knowledge"), store)
    for name, model in (("context", context), ("evidence-packet", packet), ("planning-input", planning)):
        dump_json(output / (name + ".json"), model)
    binding = {"schema_version": 1, "research_result_sha256": definition["research_result_sha256"],
        "planning_input_sha256": sha256_file(output / "planning-input.json"),
        "selected_option_ids": definition["selected_option_ids"],
        "selection_rationale": definition["selection_rationale"],
        "evidence_map": definition["evidence_map"], "branches": []}
    for branch in definition["branches"]:
        fields = dict(branch["spc_fields"])
        refs = {ref for identity in next(o for o in result["answer"]["options"] if o["id"] == branch["option_id"])["evidence_ids"]
                for ref in definition["evidence_map"][identity]}
        fields["claim_refs"] = [claim.claim_id for claim in packet.source_claims if set(claim.evidence_refs) <= refs]
        binding["branches"].append({"option_id": branch["option_id"], "spc_fields": fields})
    write_json_exclusive(output / "bindings.json", binding)
    mapped = export(run, spc_root, output / "export", binding_path=output / "bindings.json",
                    planning_input_path=output / "planning-input.json")
    if mapped["status"] != "OFFLINE_PROPOSAL_VALIDATED":
        raise ValueError("SPC rejected real-source proposal; inspect retained export/spc_mapping.json")
    proposal = load_model(output / "export/spc_proposal.json", models.PlanningProposalSet)
    compilation = ScientificProblemCompiler(None, evidence_repository=store).compile_proposal(planning, proposal)
    for index, plan in enumerate(compilation.candidates, 1):
        dump_json(output / f"plan-{index:02d}.json", plan)
    for index, receipt in enumerate(compilation.compilation_receipts, 1):
        dump_json(output / f"compilation-receipt-{index:02d}.json", receipt)
    reports = [report.model_dump(mode="json") for report in compilation.reports]
    loaded = {str(Path(module.__file__).resolve().relative_to(spc_root.resolve())): sha256_file(Path(module.__file__))
              for module in list(sys.modules.values()) if getattr(module, "__file__", None)
              and Path(module.__file__).resolve().is_relative_to((spc_root / "src").resolve())
              and Path(module.__file__).suffix == ".py"}
    receipt = {"status": "MATERIALIZED_PENDING_REVIEW" if all(r["valid"] for r in reports) else "INVALID_PLAN",
        "definition_sha256": sha256_file(definition_path), "sources": source_rows,
        "planning_input_hash": planning.content_hash, "proposal_hash": content_hash(proposal),
        "reports": reports, "loaded_spc_source_hashes": loaded,
        "scientific_acceptance": False, "human_adoption": None, "approval_granted": False,
        "runnable": False, "production_spc_state_modified": False,
        "interpretation_limits": "Exact source claims are unresolved; plan hypotheses are assumptions. No automatic scientific conflict resolution or numeric scientific validation was performed."}
    write_json_exclusive(output / "materialization_receipt.json", receipt)
    if receipt["status"] != "MATERIALIZED_PENDING_REVIEW":
        raise ValueError("SPC materialized plan failed owner validation; retained receipt")
    return receipt["status"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("run", "spc-root", "definition", "output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.run, args.spc_root, args.definition, args.output_dir))
