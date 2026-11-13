from __future__ import annotations

import base64
import copy
import json

import pytest

from scripts.artifact_io import sha256_bytes
from scripts.ts_strategy_engine import paper_sequential as paper
from scripts.ts_strategy_engine.paper_stopping import effective_force_target, revise_stopping_target
from test_ts_paper_sequential import accept, advance_training, executed_state, reseal


def approval(raw, state, target=0.03):
    instruction = b"Continue sequential rounds until raw movable DFT fmax is strictly below 0.03 eV/A"
    return json.dumps({
        "schema_version": 1, "document_kind": "paper_sequential_continuation_authorization",
        "decision": "approved_until_raw_DFT_force_target", "reviewer": "user",
        "origin_state": {"path": "/reviewed/state.json", "sha256": sha256_bytes(raw)},
        "source": {"path": "/reviewed/instruction.txt", "sha256": sha256_bytes(instruction)},
        "raw_user_instruction_base64": base64.b64encode(instruction).decode(),
        "protocol_sha256": state["protocol_sha256"], "comparison": "strictly_less_than",
        "force_metric": "raw_DFT_movable_atom_vector_norm", "training_epochs": 100,
        "reset_original_base_and_optimizer_each_round": True, "latest_label_only": True,
        "automatic_retries": 0, "separate_candidate_review_and_execution_gate_required": True,
        "no_new_round_after_threshold": True, "final_TS_or_barrier_acceptance_authorized": False,
        "first_evaluation_index": state["reserved_dft_slots"] + 1,
        "maximum_total_dft_evaluations": state["protocol"]["maximum_dft_evaluations"],
        "maximum_additional_dft_evaluations": state["protocol"]["maximum_dft_evaluations"] - state["reserved_dft_slots"],
        "previous_force_target_eV_per_A": 0.05, "force_target_eV_per_A": target,
    }).encode()


def revise(state, target=0.03):
    raw = json.dumps(state).encode()
    authorization = approval(raw, state, target)
    return revise_stopping_target(raw, expected_state_sha256=sha256_bytes(raw),
                                 raw_authorization=authorization, expected_authorization_sha256=sha256_bytes(authorization))


def test_stricter_revision_reopens_004_and_preserves_frozen_original_bytes():
    original = accept(executed_state(), forces=[[999.0, 0.0, 0.0], [0.04, 0.0, 0.0], [0.0] * 3])
    original_bytes = json.dumps(original).encode()
    updated = revise(original)
    assert original["force_converged_candidate"]
    assert updated["status"] == "awaiting_training_request"
    assert not updated["force_converged_candidate"]
    assert effective_force_target(updated) == 0.03
    assert updated["protocol"] == original["protocol"]
    assert updated["evaluations"] == original["evaluations"]
    assert base64.b64decode(updated["stopping_revision"]["origin_state"]["raw_base64"]) == original_bytes
    assert len(paper.training_request(updated)["training_samples"]) == 1
    paper.validate_state(original)
    paper.validate_state(updated)


@pytest.mark.parametrize(("force", "converged"), [(0.03, False), (0.04, False), (0.0299, True)])
def test_future_label_uses_strict_003_after_reset_training(force, converged):
    state = advance_training(revise(accept(executed_state())))
    state = executed_state(state=state, structure="9" * 64, job="200")
    final = accept(state, forces=[[999.0, 0.0, 0.0], [force, 0.0, 0.0], [0.0] * 3])
    paper.validate_state(final)
    assert final["force_converged_candidate"] is converged
    assert final["status"] == ("force_converged_candidate_only" if converged else "awaiting_training_request")


@pytest.mark.parametrize("target", [0.05, 0.06, 0, -0.03, float("nan"), True])
def test_no_looser_nonfinite_or_invalid_revision(target):
    with pytest.raises(ValueError):
        revise(accept(executed_state()), target)


def test_changed_accepted_history_is_rejected_even_after_outer_reseal():
    state = revise(accept(executed_state()))
    state["evaluations"][0]["request"]["candidate_structure_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="history"):
        paper.validate_state(reseal(state))


def test_revision_cannot_nest_or_attach_before_completed_label():
    state = revise(accept(executed_state()))
    with pytest.raises(ValueError, match="already"):
        revise(state)
    with pytest.raises(ValueError, match="accepted label"):
        revise(executed_state())


def test_raw_instruction_hash_and_origin_binding_are_mandatory():
    state = accept(executed_state())
    raw = json.dumps(state).encode()
    for key, value in [("raw_user_instruction_base64", base64.b64encode(b"changed").decode()),
                       ("origin_state", {"path": "/other", "sha256": "9" * 64})]:
        authorization = json.loads(approval(raw, state))
        authorization[key] = value
        auth_raw = json.dumps(authorization).encode()
        with pytest.raises(ValueError):
            revise_stopping_target(raw, expected_state_sha256=sha256_bytes(raw),
                                   raw_authorization=auth_raw, expected_authorization_sha256=sha256_bytes(auth_raw))


def test_revision_cannot_grant_final_TS_authority():
    state = revise(accept(executed_state()))
    changed = copy.deepcopy(state)
    changed["restrictions"]["scientifically_validated_ts"] = True
    with pytest.raises(ValueError, match="authority"):
        paper.validate_state(reseal(changed))


def test_explicit_empty_training_slot_remains_bound_after_later_training():
    origin = accept(executed_state())
    origin["evaluations"][-1]["training_result"] = None
    state = advance_training(revise(reseal(origin)))
    paper.validate_state(state)
