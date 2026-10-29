"""Offline staging adapter to the installed SPC contract, never its approval gate."""
from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import subprocess
import sys

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links, new_output
from .contract import validate_response


def load_spc(root):
    _no_links(root.absolute())
    sys.path.insert(0, str(root / "src"))
    models = importlib.import_module("spc.models")
    if not Path(models.__file__).resolve().is_relative_to((root / "src").resolve()):
        raise ValueError("a different SPC installation is already imported")
    return models


def contract_binding(root, output, models):
    names = ["src/spc/models.py", "src/spc/planning/mock_provider.py", "src/spc/planning/validators.py", "src/spc/serialization.py"]
    files = {}
    for name in names:
        source = root / name
        _no_links(source.absolute())
        digest = sha256_file(source)
        target = output / "contract_sources" / digest / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256_file(target) != digest:
            raise ValueError("SPC contract changed during snapshot")
        files[name] = digest
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "diff", "--name-only", "--", *names], text=True).splitlines()
    write_json_exclusive(output / "spc_candidate_schema.json", models.CandidatePlanDraft.model_json_schema())
    return {"root": str(root), "head": head, "dirty_contract_files": dirty, "source_sha256": files,
            "schema": "spc.models.CandidatePlanDraft / PlanningLLMResponse", "trust": "non-authoritative proposal; no gate, approval or execution"}


def candidate_fragments(result, result_hash, binding):
    if binding and (binding.get("schema_version") != 1 or binding.get("research_result_sha256") != result_hash):
        raise ValueError("SPC binding must name the exact RSI research_result bytes")
    options = result["answer"]["options"]
    selected = binding.get("selected_option_ids", [row["id"] for row in options]) if binding else [row["id"] for row in options]
    known_options = {row["id"] for row in options}
    if not isinstance(selected, list) or not selected or any(not isinstance(v, str) for v in selected) \
            or len(set(selected)) != len(selected) or not set(selected) <= known_options:
        raise ValueError("SPC selection must explicitly name existing unique options")
    rationale = binding.get("selection_rationale")
    if set(selected) != known_options and (not isinstance(rationale, str) or not rationale.strip()):
        raise ValueError("partial SPC selection requires a recorded rationale; alternatives remain in the mapping")
    by_option = {row["option_id"]: row["spc_fields"] for row in binding.get("branches", [])} if binding else {}
    if set(by_option) - {row["id"] for row in options}:
        raise ValueError("SPC mapping contains a branch not proposed by RSI")
    known = {row["evidence_id"] for row in result["evidence_actions"]}
    mapping = binding.get("evidence_map", {}) if binding else {}
    if set(mapping) - known or any(not isinstance(v, list) or any(not isinstance(i, str) or not i for i in v) for v in mapping.values()):
        raise ValueError("invalid evidence mapping; RSI IDs are not SPC trusted IDs")
    rows = []
    for option in options:
        cost = option["cost"]
        fragment = {"candidate_key": option["id"], "assumptions": option["conditions"],
                    "unknowns": [gap["question"] for gap in option.get("blocking_gaps", [])],
                    "cost_tier": "unknown" if cost["status"] == "unknown" else f"{cost['status']}: {cost['value']} {cost['unit']}; {cost['basis']}",
                    "risks": option["risks"], "limitations": [result["answer"]["scientific_limits"]]}
        extra = by_option.get(option["id"], {})
        if set(extra) & set(fragment) or "evidence_refs" in extra:
            raise ValueError("SPC mapping cannot override RSI branch content or bypass evidence mapping")
        fragment.update(extra)
        missing = [identity for identity in option["evidence_ids"] if not mapping.get(identity)]
        if not missing:
            fragment["evidence_refs"] = list(dict.fromkeys(span for identity in option["evidence_ids"] for span in mapping[identity]))
        rows.append({"option_id": option["id"], "rsi_proposal": option["proposal"],
                     "selected_for_spc": option["id"] in selected,
                     "rsi_acceptance_conditions": option["acceptance_conditions"],
                     "branch_blocking_gaps": option.get("blocking_gaps", []), "missing_evidence_bindings": missing,
                     "candidate_fragment": fragment})
    return rows


def _ground(models, result, drafts, planning_input):
    from spc.planning.mock_provider import build_proposal_set
    from spc.planning.validators import validate_planning_proposal_set
    observables = list(dict.fromkeys(item.description for draft in drafts for item in draft.observables))
    refs = list(dict.fromkeys(ref for draft in drafts for ref in draft.evidence_refs))
    response = models.PlanningLLMResponse.model_validate({
        "intent": {"target_claim": result["research_goal"], "latent_concern": result["answer"]["recommended_next"]["rationale"],
                   "atomic_questions": [result["research_goal"]], "decision_relevant_observables": observables, "evidence_basis": refs},
        "ambiguity_assessment": {"multiple_candidates_required": len(drafts) > 1,
            "rationale": result["answer"]["recommended_next"]["rationale"],
            "scientifically_distinct_axes": list(dict.fromkeys(draft.distinguishing_axis for draft in drafts))},
        "candidates": [draft.model_dump(mode="json") for draft in drafts]})
    proposal = build_proposal_set(planning_input, provider_id="rsi-thin-adapter", provider_version="1",
        provider_config={"mode": "offline-explicit-bindings", "rsi_result_hash": sha256_json(result)},
        intent=response.intent, ambiguity_assessment=response.ambiguity_assessment, candidates=response.candidates)
    return proposal, validate_planning_proposal_set(proposal, planning_input)


def export(run, spc_root, output, *, binding_path=None, planning_input_path=None):
    from pydantic import ValidationError
    _no_links(run.absolute())
    output = new_output(output, [run, spc_root])
    models = load_spc(spc_root)
    contract = contract_binding(spc_root, output, models)
    result_path = run / "research_result.json"
    digest = sha256_file(result_path)
    result = load_json_object(result_path)
    receipt = load_json_object(run / "run_receipt.json")
    results = {}
    for action in result["evidence_actions"]:
        path = Path(action["result_path"])
        _no_links(path.absolute())
        if not path.resolve().is_relative_to((run / "tools").resolve()) or sha256_file(path) != action["result_sha256"]:
            raise ValueError("RSI host result differs from its binding")
        results[action["evidence_id"]] = load_json_object(path)["result"]
    validate_response({"kind": "final", "requests": [], "answer": result["answer"]}, results, receipt["intent"], version=receipt["protocol_version"])
    if result["research_goal"] != receipt["goal"] or sha256_file(result_path) != digest:
        raise ValueError("RSI research result/goal changed")
    shutil.copyfile(result_path, output / "rsi_result.original.json")
    binding = load_json_object(binding_path) if binding_path else {}
    rows = candidate_fragments(result, digest, binding)
    drafts = []
    for row in rows:
        try:
            candidate = models.CandidatePlanDraft.model_validate(row["candidate_fragment"])
            row["shape_valid"] = True
            row["validation_issues"] = []
            if row["selected_for_spc"]:
                drafts.append(candidate)
        except ValidationError as exc:
            row["shape_valid"] = False
            row["validation_issues"] = [{"field": ".".join(str(x) for x in issue["loc"]), "type": issue["type"], "message": issue["msg"]}
                                        for issue in exc.errors(include_input=False, include_url=False)]
    status, owner_validation = "BLOCKED_BINDINGS_REQUIRED", None
    if drafts and len(drafts) == sum(row["selected_for_spc"] for row in rows):
        status = "SHAPE_VALIDATED_PENDING_GROUNDING"
        if planning_input_path:
            from spc.serialization import load_model
            if binding.get("planning_input_sha256") != sha256_file(planning_input_path):
                raise ValueError("mapping is not bound to the actual SPC planning input")
            planning_input = load_model(planning_input_path, models.ScientificPlanningInput)
            proposal, validation = _ground(models, result, drafts, planning_input)
            owner_validation = validation.model_dump(mode="json")
            write_json_exclusive(output / "spc_proposal.json", proposal.model_dump(mode="json"))
            status = "OFFLINE_PROPOSAL_VALIDATED" if validation.valid else "BLOCKED_SPC_GROUNDING"
    if any(sha256_file(spc_root / name) != value for name, value in contract["source_sha256"].items()):
        raise ValueError("SPC contract changed during offline validation")
    document = {"schema_version": 1, "status": status, "rsi_result": {"path": str(result_path), "sha256": digest},
                "rsi_run_mode": receipt["run_mode"],
                "selection_rationale": binding.get("selection_rationale"),
                "unselected_alternatives_retained": True,
                "spc_contract": contract, "branches": rows, "spc_owner_validation": owner_validation,
                "required_before_spc_use": (["SPC deterministic materialization and independent review/gates"]
                    if status == "OFFLINE_PROPOSAL_VALIDATED" else ["explicit source-evidence/claim/capability bindings to a valid ScientificPlanningInput",
                    "missing hypothesis/model/observable/baseline/falsification/task fields from reviewed scientific owners",
                    "SPC deterministic materialization and independent review/gates"]),
                "scientific_acceptance": False, "approval_granted": False, "runnable": False, "spc_state_modified": False}
    write_json_exclusive(output / "spc_mapping.json", document)
    return document
