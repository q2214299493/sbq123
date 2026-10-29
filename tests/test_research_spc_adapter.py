"""Mapping tests; optional SPC owner-fixture integration is entirely offline."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from copy import deepcopy

import pytest

from scripts.research_assistant.spc_adapter import candidate_fragments, load_spc, _ground
from scripts.research_assistant.spc_adapter import export
from scripts.research_assistant.contract import VERSION
from scripts.artifact_io import sha256_file, write_json_exclusive


def minimal_result():
    return {"research_goal": "synthetic research question", "answer": {"scientific_limits": "software fixture only",
        "recommended_next": {"rationale": "explicit fixture evidence"},
        "options": [{"id": "branch-a", "proposal": "review the fixture", "evidence_ids": ["E001"],
            "conditions": ["owner review"], "risks": [], "acceptance_conditions": ["owner standards"], "blocking_gaps": [],
            "cost": {"status": "unknown", "value": None, "unit": None}}]}, "evidence_actions": [{"evidence_id": "E001"}]}


def test_spc_mapping_does_not_invent_trusted_ids_or_hypotheses():
    row = candidate_fragments(minimal_result(), "a" * 64, {})[0]
    assert row["missing_evidence_bindings"] == ["E001"]
    assert "evidence_refs" not in row["candidate_fragment"]
    assert "null_hypothesis" not in row["candidate_fragment"]
    assert row["candidate_fragment"]["cost_tier"] == "unknown"


def test_spc_mapping_requires_exact_result_and_cannot_replace_rsi_branch():
    result = minimal_result()
    with pytest.raises(ValueError, match="exact RSI"):
        candidate_fragments(result, "a" * 64, {"schema_version": 1, "research_result_sha256": "b" * 64})
    binding = {"schema_version": 1, "research_result_sha256": "a" * 64,
               "branches": [{"option_id": "branch-a", "spc_fields": {"cost_tier": "low"}}]}
    with pytest.raises(ValueError, match="cannot override"):
        candidate_fragments(result, "a" * 64, binding)


def test_explicit_spc_selection_retains_alternatives_and_requires_reason():
    result = minimal_result()
    alternative = deepcopy(result["answer"]["options"][0])
    alternative["id"] = "branch-b"
    result["answer"]["options"].append(alternative)
    binding = {"schema_version": 1, "research_result_sha256": "a" * 64, "selected_option_ids": ["branch-a"]}
    with pytest.raises(ValueError, match="recorded rationale"):
        candidate_fragments(result, "a" * 64, binding)
    binding["selection_rationale"] = "Produce one read-only review plan; retain branch-b as an unresolved alternative"
    rows = candidate_fragments(result, "a" * 64, binding)
    assert len(rows) == 2 and [row["selected_for_spc"] for row in rows] == [True, False]


@pytest.mark.parametrize("fabricated_reference", [False, True])
def test_current_spc_owner_validates_mapped_mock_fixture_offline(tmp_path, fabricated_reference):
    location = os.environ.get("RSI_TEST_SPC_ROOT")
    if not location:
        pytest.skip("set RSI_TEST_SPC_ROOT to opt into the separate SPC source contract")
    root = Path(location)
    models = load_spc(root)
    spec = importlib.util.spec_from_file_location("rsi_spc_owner_fixture", root / "tests/test_planning.py")
    owner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = owner
    spec.loader.exec_module(owner)
    *_, planning_input, proposal, _ = owner.build_grounded_inputs(tmp_path / "owner-fixture")
    original = proposal.candidates[0].model_dump(mode="json")
    result = minimal_result()
    result["research_goal"] = planning_input.original_request
    option = result["answer"]["options"][0]
    option.update({"id": original["candidate_key"], "conditions": original["assumptions"] or ["Independent review of this offline fixture"], "risks": original["risks"],
                   "blocking_gaps": [{"question": q, "needed_artifact": "owner fixture evidence", "evidence_ids": ["E001"]}
                                     for q in original["unknowns"]]})
    basic = {"candidate_key", "assumptions", "unknowns", "cost_tier", "risks", "limitations", "evidence_refs"}
    evidence = ["fabricated-evidence"] if fabricated_reference else original["evidence_refs"]
    binding = {"schema_version": 1, "research_result_sha256": "a" * 64, "evidence_map": {"E001": evidence},
               "branches": [{"option_id": option["id"], "spc_fields": {key: value for key, value in original.items() if key not in basic}}]}
    alternative = deepcopy(option)
    alternative["id"] = "retained-unselected"
    alternative["cost"].update({"basis": "not measured", "evidence_ids": []})
    result["answer"]["options"].append(alternative)
    binding.update({"selected_option_ids": [option["id"]], "selection_rationale": "Only materialize one fixture; retain the alternative"})
    rows = candidate_fragments(result, "a" * 64, binding)
    drafts = [models.CandidatePlanDraft.model_validate(rows[0]["candidate_fragment"])]
    mapped, report = _ground(models, result, drafts, planning_input)
    assert report.valid is not fabricated_reference, report.model_dump(mode="json")
    assert mapped.provider_id == "rsi-thin-adapter"
    if fabricated_reference:
        assert any(issue.code == "FABRICATED_EVIDENCE_ID" for issue in report.issues)
    # Exercise the complete file-bound adapter as well as the owner validator.
    from spc.serialization import dump_json
    folder = tmp_path / "rsi-fixture"
    (folder / "tools").mkdir(parents=True)
    action_path = folder / "tools/E001.json"
    write_json_exclusive(action_path, {"result": {"evidence_id": "E001", "data": {"source": "offline owner fixture"}}})
    result["evidence_actions"][0].update({"result_path": str(action_path), "result_sha256": sha256_file(action_path)})
    fact = {"statement": "Offline owner fixture; no scientific run", "evidence_ids": ["E001"]}
    result["answer"].update({"intent": "plan", "goal": result["research_goal"], "facts": [fact], "uncertainties": [],
        "hypotheses": [], "evidence_and_calculation_plan": [], "new_information": [fact], "draft_evidence_ids": [], "progress": None})
    result["answer"]["recommended_next"].update({"action": "Review the offline mapping", "evidence_ids": ["E001"],
        "outcomes": [{"if": "grounding valid", "then": "request independent review"}]})
    option["cost"].update({"basis": "not measured", "evidence_ids": []})
    write_json_exclusive(folder / "research_result.json", result)
    write_json_exclusive(folder / "run_receipt.json", {"protocol_version": VERSION, "intent": "plan", "goal": result["research_goal"],
                                                       "run_mode": "OFFLINE_TEST_TRANSPORT"})
    planning_path = tmp_path / "planning-input.json"
    dump_json(planning_path, planning_input)
    binding.update({"research_result_sha256": sha256_file(folder / "research_result.json"), "planning_input_sha256": sha256_file(planning_path)})
    binding_path = tmp_path / "reviewed-fixture-bindings.json"
    write_json_exclusive(binding_path, binding)
    document = export(folder, root, tmp_path / "mapped", binding_path=binding_path, planning_input_path=planning_path)
    assert document["status"] == ("BLOCKED_SPC_GROUNDING" if fabricated_reference else "OFFLINE_PROPOSAL_VALIDATED")
    assert len(document["branches"]) == 2 and not document["branches"][1]["selected_for_spc"]
    assert not document["runnable"] and not document["approval_granted"] and not document["spc_state_modified"]
