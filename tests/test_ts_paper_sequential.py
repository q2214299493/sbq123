from __future__ import annotations

import base64
import copy
import json

import pytest

from scripts.artifact_io import sha256_bytes, sha256_json
from scripts.ts_strategy_engine.paper_sequential import (
    accept_force_label,
    create_protocol,
    initialize_state,
    prepare_dft_evaluation,
    record_execution,
    record_failure,
    recover_prelaunch_failure,
    register_training_result,
    training_request,
    validate_state,
)


BASE, TRAINED, CONTRACT, COMPATIBILITY = (character * 64 for character in "abcd")
STRUCTURE, NEXT_STRUCTURE, GEOMETRY = (character * 64 for character in "ef1")


def protocol(**changes):
    arguments = {
        "initial_checkpoint_path": "/home/sbq/sbq/frozen.pt", "initial_checkpoint_sha256": BASE,
        "contract_sha256": CONTRACT, "compatibility_sha256": COMPATIBILITY,
        "atom_count": 3, "movable_atom_indices": [1, 2], "formed_bonds_1based": [[2, 3]],
        "broken_bonds_1based": [], "maximum_dft_evaluations": 3,
        "model_adaptation": "Existing AQCat25 checkpoint; movable-force training is a model adaptation.",
        "dft_adaptation": "Project Fe(110) VASP profile instead of the paper's QE protocol.",
        "model_recipe_adaptation": {"optimizer": "AdamW", "weight_decay": 0.001, "force_loss": "force_l2mae"},
    }
    arguments.update(changes)
    return create_protocol(**arguments)


def executed_state(*, selected_protocol=None, state=None, structure=STRUCTURE, job="100"):
    state = state or initialize_state(selected_protocol or protocol())
    state = prepare_dft_evaluation(
        state, candidate_structure_sha256=structure,
        search_checkpoint_sha256=state["search_checkpoint"]["sha256"],
    )
    return record_execution(state, job_id=job, bundle_sha256="2" * 64, gate_sha256="3" * 64)


def label_bytes(state, *, forces=None, changes=None):
    current = state["evaluations"][-1]
    label = {
        "document_kind": "vasp_ts_force_label",
        "result_class": "vasp_completed_electronic_converged_force_label_only", "reportable_final_energy": False,
        "normal_completion": True, "electronically_converged": True, "eligible_for_force_only_training": True,
        "contract_sha256": CONTRACT, "compatibility_sha256": COMPATIBILITY,
        "paper_sequential_request_sha256": current["request_sha256"],
        "structure": {"sha256": current["request"]["candidate_structure_sha256"]},
        "scheduler_evidence": {"job_id": current["execution"]["job_id"]},
        "fixed_atom_indices_zero_based": [0], "geometry_sha256": GEOMETRY,
        "forces_eV_per_A": forces or [[100.0, 0.0, 0.0], [0.10, 0.0, 0.0], [0.0, 0.0, 0.0]],
    }
    label.update(changes or {})
    return json.dumps(label, indent=3).encode()


def accept(state, **changes):
    raw = label_bytes(state, **changes)
    return accept_force_label(state, raw, expected_sha256=sha256_bytes(raw))


def reseal(state):
    """Model persisted data whose outer checksum was deliberately recomputed."""
    state["state_sha256"] = sha256_json({key: value for key, value in state.items() if key != "state_sha256"})
    return state


def advance_training(state, *, checkpoint_sha=TRAINED, name="round1.pt"):
    return register_training_result(
        state, checkpoint_path="/home/sbq/sbq/" + name, checkpoint_sha256=checkpoint_sha,
        training_request_sha256=sha256_json(training_request(state)), base_checkpoint_sha256=BASE,
    )


def test_protocol_records_paper_parameters_and_explicit_adaptations():
    settings = protocol()
    assert settings["idpp"]["total_images"] == 10
    assert settings["ba_sella"] == {
        "eta": 0.01, "gamma": 0.05, "delta0": 0.05, "nsteps_per_diag": 1,
        "dot_prod_thr": 0.50, "fmax_eV_per_A": 0.01, "minimum_steps": 10, "maximum_steps": 1000,
    }
    assert settings["training"]["epochs"] == 100
    assert settings["training"]["initial_learning_rate"] == 1e-4
    assert settings["training"]["cosine_eta_min"] is None
    assert not settings["adaptations"]["unmodified_paper_reproduction"]
    assert settings["adaptations"]["model_recipe"]["optimizer"] == "AdamW"


def test_preparation_reserves_but_does_not_claim_a_DFT_execution():
    initial = initialize_state(protocol())
    prepared = prepare_dft_evaluation(initial, candidate_structure_sha256=STRUCTURE, search_checkpoint_sha256=BASE)
    assert initial["reserved_dft_slots"] == 0
    assert prepared["reserved_dft_slots"] == 1
    assert prepared["executed_dft_jobs"] == 0
    assert prepared["completed_label_count"] == 0
    assert prepared["evaluations"][0]["request"]["requires_authoritative_execution_gate"]
    with pytest.raises(ValueError, match="current state"):
        prepare_dft_evaluation(prepared, candidate_structure_sha256=STRUCTURE, search_checkpoint_sha256=BASE)
    with pytest.raises(ValueError, match="no executed"):
        accept_force_label(prepared, b"{}", expected_sha256=sha256_bytes(b"{}"))


def test_failed_execution_consumes_quota_and_never_auto_retries():
    state = executed_state()
    failed = record_failure(state, "DFT electronic convergence failed")
    assert failed["reserved_dft_slots"] == failed["executed_dft_jobs"] == 1
    assert failed["completed_label_count"] == 0
    assert failed["status"] == "failed_needs_review_no_automatic_retry"
    with pytest.raises(ValueError):
        prepare_dft_evaluation(failed, candidate_structure_sha256=STRUCTURE, search_checkpoint_sha256=BASE)


def test_second_round_uses_only_latest_label_and_resets_initial_weights():
    first = accept(executed_state())
    first_request = training_request(first)
    next_state = register_training_result(
        first, checkpoint_path="/home/sbq/sbq/round1.pt", checkpoint_sha256=TRAINED,
        training_request_sha256=sha256_json(first_request), base_checkpoint_sha256=BASE,
    )
    second = accept(executed_state(state=next_state, structure=NEXT_STRUCTURE, job="101"))
    request = training_request(second)
    assert second["executed_dft_jobs"] == second["completed_label_count"] == 2
    assert request["base_checkpoint"] == first["protocol"]["initial_checkpoint"]
    assert len(request["training_samples"]) == 1
    assert request["training_samples"][0]["label"]["structure"]["sha256"] == NEXT_STRUCTURE
    assert request["reset_model_weights"] and request["reset_optimizer_state"] and request["reset_scheduler_state"]
    assert request["reset_amp_state"] and request["reset_ema_state"]
    assert request["training"]["target"] == "forces_only"
    assert request["training"]["energy_loss_coefficient"] == 0.0
    assert request["training"]["train_on_all"] is False
    assert request["training"]["train_finetuned"] is False
    assert request["training"]["replay"] is False
    assert request["training"]["validation_epoch_selection"] is False
    assert request["checkpoint_selection"] == "final_epoch_only"
    request["base_checkpoint"]["path"] = "/changed"
    assert second["protocol"]["initial_checkpoint"]["path"] == "/home/sbq/sbq/frozen.pt"


def test_raw_all_atom_forces_are_retained_but_only_movable_atoms_stop_search():
    state = accept(executed_state(), forces=[[999.0, 0.0, 0.0], [0.049, 0.0, 0.0], [0.0, 0.0, 0.0]])
    assert state["DFT_movable_fmax_eV_per_A"] == pytest.approx(0.049)
    assert state["latest_label"]["raw_forces_eV_per_A"][0] == [999.0, 0.0, 0.0]
    assert state["status"] == "force_converged_candidate_only"
    assert state["force_converged_candidate"]
    assert all(value is False for value in state["restrictions"].values())
    with pytest.raises(ValueError, match="no training"):
        training_request(state)


@pytest.mark.parametrize("force", [[0.05, 0.0, 0.0], [0.04, 0.04, 0.0]])
def test_DFT_stopping_uses_strict_vector_norm_not_component_or_model_error(force):
    state = accept(executed_state(), forces=[[0.0] * 3, force, [0.0] * 3])
    assert state["status"] == "awaiting_training_request"
    assert not state["force_converged_candidate"]


def test_last_allowed_DFT_can_converge_without_an_extra_evaluation():
    state = accept(executed_state(selected_protocol=protocol(maximum_dft_evaluations=1)),
                   forces=[[0.0] * 3, [0.01, 0.0, 0.0], [0.0] * 3])
    assert state["reserved_dft_slots"] == state["executed_dft_jobs"] == 1
    assert state["status"] == "force_converged_candidate_only"


def test_nonconverged_last_DFT_stops_budget_without_training_or_plus_one():
    state = accept(executed_state(selected_protocol=protocol(maximum_dft_evaluations=1)))
    assert state["status"] == "budget_exhausted_not_converged"
    assert not state["force_converged_candidate"]
    with pytest.raises(ValueError):
        training_request(state)
    with pytest.raises(ValueError):
        prepare_dft_evaluation(state, candidate_structure_sha256=NEXT_STRUCTURE, search_checkpoint_sha256=BASE)
    assert state["reserved_dft_slots"] == state["executed_dft_jobs"] == state["completed_label_count"] == 1


@pytest.mark.parametrize("change", [
    {"document_kind": "model_prediction"}, {"result_class": "predicted_transition_state_candidate_only"},
    {"reportable_final_energy": True},
    {"normal_completion": False}, {"electronically_converged": False},
    {"eligible_for_force_only_training": False}, {"contract_sha256": "0" * 64},
    {"compatibility_sha256": "0" * 64}, {"structure": {"sha256": NEXT_STRUCTURE}},
    {"paper_sequential_request_sha256": "0" * 64}, {"scheduler_evidence": {"job_id": "another"}},
    {"fixed_atom_indices_zero_based": []}, {"forces_eV_per_A": [[0.0, 0.0, 0.0]]},
    {"forces_eV_per_A": [[0.0] * 3, [float("nan"), 0.0, 0.0], [0.0] * 3]},
])
def test_ineligible_or_mismatched_labels_are_rejected_without_state_changes(change):
    state = executed_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        accept(state, changes=change)
    assert state == before
    assert state["executed_dft_jobs"] == 1 and state["completed_label_count"] == 0


def test_label_hash_is_checked_on_original_bytes_before_JSON_round_trip():
    state = executed_state()
    raw = label_bytes(state)
    reformatted = json.dumps(json.loads(raw), separators=(",", ":")).encode()
    assert sha256_bytes(raw) != sha256_bytes(reformatted)
    with pytest.raises(ValueError, match="artifact hash"):
        accept_force_label(state, reformatted, expected_sha256=sha256_bytes(raw))


def test_holdout_structure_and_geometry_cannot_enter_training():
    initial = initialize_state(protocol(held_out_structure_sha256=(STRUCTURE,)))
    with pytest.raises(ValueError, match="held-out structure"):
        prepare_dft_evaluation(initial, candidate_structure_sha256=STRUCTURE, search_checkpoint_sha256=BASE)
    state = executed_state(selected_protocol=protocol(held_out_geometry_sha256=(GEOMETRY,)))
    with pytest.raises(ValueError, match="held-out geometry"):
        accept(state)
    with pytest.raises(ValueError, match="geometry hash is required"):
        accept(state, changes={"geometry_sha256": None})


@pytest.mark.parametrize("changes", [
    {"maximum_dft_evaluations": 251}, {"maximum_dft_evaluations": 0}, {"maximum_dft_evaluations": True},
    {"movable_atom_indices": []}, {"movable_atom_indices": [1, 1]}, {"movable_atom_indices": [3]},
    {"initial_checkpoint_path": "relative.pt"}, {"initial_checkpoint_sha256": "bad"},
    {"formed_bonds_1based": []}, {"formed_bonds_1based": [[2, 2]]}, {"model_adaptation": ""},
])
def test_invalid_protocol_inputs_are_rejected(changes):
    with pytest.raises(ValueError):
        protocol(**changes)


def test_frozen_protocol_and_state_mutation_are_detected():
    state = initialize_state(protocol())
    state["protocol"]["initial_checkpoint"]["sha256"] = TRAINED
    with pytest.raises(ValueError, match="state hash"):
        validate_state(state)
    settings = protocol()
    settings["training"]["epochs"] = 2
    with pytest.raises(ValueError, match="protocol fields"):
        initialize_state(settings)


@pytest.mark.parametrize("changes", [
    {"base_checkpoint_sha256": TRAINED}, {"training_request_sha256": "0" * 64}, {"checkpoint_sha256": BASE},
])
def test_training_result_cannot_continue_previous_weights_or_change_request(changes):
    state = accept(executed_state())
    values = {
        "checkpoint_path": "/home/sbq/sbq/new.pt", "checkpoint_sha256": TRAINED,
        "training_request_sha256": sha256_json(training_request(state)), "base_checkpoint_sha256": BASE,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        register_training_result(state, **values)


def test_resealed_empty_state_cannot_invent_training_eligibility():
    state = initialize_state(protocol())
    state["status"] = "awaiting_training_request"
    state["latest_label"] = {"artifact_sha256": "0" * 64, "label": {"forces_eV_per_A": [[0.0] * 3] * 3}}
    with pytest.raises(ValueError, match="latest label"):
        training_request(reseal(state))


def test_resealed_execution_state_cannot_skip_accepted_label_stage():
    state = executed_state()
    state["status"] = "awaiting_training_request"
    with pytest.raises(ValueError, match="evaluation phase"):
        training_request(reseal(state))


@pytest.mark.parametrize("field,value", [
    ("candidate_structure_sha256", NEXT_STRUCTURE), ("search_checkpoint_sha256", TRAINED),
    ("evaluation_index", 2), ("protocol_sha256", "0" * 64), ("compatibility_sha256", "0" * 64),
])
def test_resealed_nested_request_changes_cannot_keep_stale_hash(field, value):
    state = executed_state()
    state["evaluations"][0]["request"][field] = value
    with pytest.raises(ValueError, match="request hash"):
        validate_state(reseal(state))


def test_resealed_latest_label_must_come_from_last_accepted_evaluation():
    state = accept(executed_state())
    state["latest_label"]["raw_forces_eV_per_A"][1] = [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="latest label"):
        training_request(reseal(state))


def test_resealed_latest_label_cannot_exploit_boolean_numeric_equality():
    state = accept(executed_state(), forces=[[1.0, 0.0, 0.0], [0.10, 0.0, 0.0], [0.0, 0.0, 0.0]])
    state["latest_label"]["raw_forces_eV_per_A"][0][0] = True
    with pytest.raises(ValueError, match="latest label"):
        training_request(reseal(state))


@pytest.mark.parametrize("alteration", ["parsed_label", "stored_forces", "source_hash", "source_bytes", "row_hash"])
def test_resealed_accepted_data_must_match_original_label_bytes(alteration):
    state = accept(executed_state())
    record = state["evaluations"][0]["accepted_label"]
    if alteration == "parsed_label":
        record["label"]["structure"]["sha256"] = NEXT_STRUCTURE
    elif alteration == "stored_forces":
        record["raw_forces_eV_per_A"][1] = [0.0, 0.0, 0.0]
    elif alteration == "source_hash":
        record["artifact_sha256"] = "0" * 64
        state["evaluations"][0]["label_sha256"] = "0" * 64
    elif alteration == "source_bytes":
        record["raw_label_base64"] = "not base64!"
    else:
        state["evaluations"][0]["label_sha256"] = "0" * 64
    state["latest_label"] = copy.deepcopy(record)
    with pytest.raises(ValueError):
        training_request(reseal(state))


@pytest.mark.parametrize("field,value", [
    ("DFT_movable_fmax_eV_per_A", 0.0), ("force_converged_candidate", True),
    ("completed_label_count", 0), ("executed_dft_jobs", "1"),
])
def test_resealed_counts_and_residuals_are_checked_against_accepted_history(field, value):
    state = accept(executed_state())
    state[field] = value
    with pytest.raises(ValueError):
        validate_state(reseal(state))


def test_resealed_budget_status_cannot_resume_training():
    state = accept(executed_state(selected_protocol=protocol(maximum_dft_evaluations=1)))
    state["status"] = "awaiting_training_request"
    with pytest.raises(ValueError, match="evaluation phase"):
        training_request(reseal(state))


def test_historical_rounds_remain_valid_when_next_round_is_only_prepared():
    first = advance_training(accept(executed_state()))
    second = accept(executed_state(state=first, structure=NEXT_STRUCTURE, job="101"))
    second = advance_training(second, checkpoint_sha="4" * 64, name="round2.pt")
    third = prepare_dft_evaluation(second, candidate_structure_sha256="5" * 64, search_checkpoint_sha256="4" * 64)
    validate_state(third)
    assert third["reserved_dft_slots"] == 3
    assert third["executed_dft_jobs"] == third["completed_label_count"] == 2
    assert third["latest_label"] == third["evaluations"][1]["accepted_label"]
    assert len(third["evaluations"]) == 3


@pytest.mark.parametrize("field", ["base", "request", "search"])
def test_resealed_historical_training_chain_is_checked(field):
    first = advance_training(accept(executed_state()))
    state = accept(executed_state(state=first, structure=NEXT_STRUCTURE, job="101"))
    if field == "base":
        state["evaluations"][0]["training_result"]["base_checkpoint_sha256"] = TRAINED
    elif field == "request":
        state["evaluations"][0]["training_result"]["training_request_sha256"] = "0" * 64
    else:
        row = state["evaluations"][1]
        row["request"]["search_checkpoint_sha256"] = BASE
        row["request_sha256"] = sha256_json(row["request"])
    with pytest.raises(ValueError):
        training_request(reseal(state))


def test_resealed_history_cannot_append_an_evaluation_before_training_result():
    state = accept(executed_state())
    state["evaluations"].append(copy.deepcopy(state["evaluations"][0]))
    state["reserved_dft_slots"] = 2
    state["executed_dft_jobs"] = state["completed_label_count"] = 2
    with pytest.raises(ValueError, match="previous round"):
        training_request(reseal(state))


def test_failure_status_cannot_hide_forged_accepted_data():
    state = record_failure(executed_state(), "DFT failed")
    state["latest_label"] = {"invented": True}
    with pytest.raises(ValueError, match="latest label"):
        validate_state(reseal(state))


def recovery_material(failed=None, *, evidence_changes=None, authorization_changes=None):
    failed = failed or record_failure(executed_state(), "MPI hwloc failed before VASP", stage="mpi_prelaunch")
    raw_state = json.dumps(failed, indent=3).encode()
    current = failed["evaluations"][0]
    common = {"protocol_sha256": failed["protocol_sha256"], "evaluation_index": 1,
              "candidate_structure_sha256": current["request"]["candidate_structure_sha256"],
              "search_checkpoint_sha256": current["request"]["search_checkpoint_sha256"],
              "failed_execution": copy.deepcopy(current["execution"]), "failure_stage": "mpi_prelaunch",
              "failed_state_artifact_sha256": sha256_bytes(raw_state)}
    evidence = {**common, "document_kind": "paper_prelaunch_failure_evidence", "vasp_started": False,
                "dft_label_created": False, "scheduler_evidence_sha256": "4" * 64, "launcher_log_sha256": "5" * 64}
    evidence.update(evidence_changes or {})
    raw_evidence = json.dumps(evidence, indent=2).encode()
    authorization = {**common, "document_kind": "paper_prelaunch_recovery_authorization",
                     "decision": "approved_one_prelaunch_recovery", "automatic_retry": False,
                     "maximum_recoveries": 1, "failure_evidence_artifact_sha256": sha256_bytes(raw_evidence),
                     "reviewer": "unit-test-only review", "reviewed_at": "2026-11-12T00:00:00Z",
                     "recovery_bundle_sha256": "6" * 64, "recovery_gate_sha256": "7" * 64}
    authorization.update(authorization_changes or {})
    raw_authorization = json.dumps(authorization, indent=4).encode()
    return {"raw_failed_state": raw_state, "expected_failed_state_sha256": sha256_bytes(raw_state),
            "raw_failure_evidence": raw_evidence, "expected_failure_evidence_sha256": sha256_bytes(raw_evidence),
            "raw_reviewed_authorization": raw_authorization,
            "expected_reviewed_authorization_sha256": sha256_bytes(raw_authorization)}


def recovered_state(**changes):
    return recover_prelaunch_failure(**recovery_material(**changes))


def recovered_execution(**changes):
    return record_execution(recovered_state(**changes), job_id="101", bundle_sha256="6" * 64, gate_sha256="7" * 64)


def test_reviewed_prelaunch_recovery_preserves_raw_failure_and_actual_submissions():
    failed = record_failure(executed_state(selected_protocol=protocol(maximum_dft_evaluations=1)),
                            "MPI hwloc before VASP", stage="mpi_prelaunch")
    old = copy.deepcopy(failed)
    material = recovery_material(failed)
    recovered = recover_prelaunch_failure(**material)
    assert failed == old and sha256_bytes(material["raw_failed_state"]) == material["expected_failed_state_sha256"]
    assert recovered["status"] == "awaiting_execution_receipt"
    assert recovered["reserved_dft_slots"] == recovered["executed_dft_jobs"] == 1
    assert recovered["completed_label_count"] == 0 and recovered["latest_label"] is None
    assert recovered["evaluations"][0]["execution"] is None
    assert recovered["evaluations"][0]["execution_history"] == [old["evaluations"][0]["execution"]]
    event = recovered["evaluations"][0]["prelaunch_recovery"]
    assert base64.b64decode(event["failed_state"]["raw_base64"]) == material["raw_failed_state"]
    second = record_execution(recovered, job_id="101", bundle_sha256="6" * 64, gate_sha256="7" * 64)
    assert second["reserved_dft_slots"] == len(second["evaluations"]) == 1
    assert second["executed_dft_jobs"] == 2 and second["completed_label_count"] == 0
    assert [receipt["job_id"] for receipt in second["evaluations"][0]["execution_history"]] == ["100", "101"]
    assert second["evaluations"][0]["execution"] == second["evaluations"][0]["execution_history"][-1]
    assert second["evaluations"][0]["request"] == old["evaluations"][0]["request"]
    assert all(value is False for value in second["restrictions"].values())
    validate_state(second)


def test_only_latest_recovery_job_may_supply_a_label_and_training_can_continue():
    state = recovered_execution()
    with pytest.raises(ValueError):
        accept(state, changes={"scheduler_evidence": {"job_id": "100"}})
    completed = accept(state)
    assert completed["executed_dft_jobs"] == 2 and completed["completed_label_count"] == 1
    trained = advance_training(completed)
    validate_state(trained)
    next_round = prepare_dft_evaluation(trained, candidate_structure_sha256=NEXT_STRUCTURE, search_checkpoint_sha256=TRAINED)
    assert next_round["reserved_dft_slots"] == 2 and next_round["executed_dft_jobs"] == 2
    assert next_round["evaluations"][1]["request"]["evaluation_index"] == 2


@pytest.mark.parametrize("stage", ["SCF", "training", "prelaunch", ""])
def test_record_failure_does_not_offer_a_general_retry_stage(stage):
    with pytest.raises(ValueError, match="typed prelaunch"):
        record_failure(executed_state(), "not this recovery scope", stage=stage)


def test_prelaunch_classification_requires_submitted_receipt_and_no_label():
    prepared = prepare_dft_evaluation(initialize_state(protocol()), candidate_structure_sha256=STRUCTURE,
                                      search_checkpoint_sha256=BASE)
    for state in (prepared, accept(executed_state())):
        with pytest.raises(ValueError, match="typed prelaunch"):
            record_failure(state, "prelaunch", stage="mpi_prelaunch")
    generic = record_failure(executed_state(), "SCF failed")
    with pytest.raises(ValueError, match="typed prelaunch"):
        recovered_state(failed=generic)


@pytest.mark.parametrize("changes", [
    {"vasp_started": True}, {"dft_label_created": True}, {"failure_stage": "scf"},
    {"evaluation_index": 2}, {"candidate_structure_sha256": NEXT_STRUCTURE},
    {"failed_execution": {"job_id": "999", "bundle_sha256": "2" * 64, "gate_sha256": "3" * 64}},
    {"scheduler_evidence_sha256": "invalid"}, {"failed_state_artifact_sha256": "0" * 64},
])
def test_recovery_rejects_wrong_failure_stage_identity_and_started_vasp(changes):
    with pytest.raises(ValueError):
        recovered_state(evidence_changes=changes)


@pytest.mark.parametrize("changes", [
    {"automatic_retry": True}, {"maximum_recoveries": 2}, {"maximum_recoveries": True},
    {"decision": "automatic"}, {"reviewer": ""}, {"reviewed_at": ""},
    {"failure_evidence_artifact_sha256": "0" * 64}, {"recovery_gate_sha256": "invalid"},
    {"search_checkpoint_sha256": TRAINED},
])
def test_recovery_requires_the_exact_single_reviewed_authorization(changes):
    with pytest.raises(ValueError):
        recovered_state(authorization_changes=changes)


@pytest.mark.parametrize("raw_key,digest_key", [
    ("raw_failed_state", "expected_failed_state_sha256"),
    ("raw_failure_evidence", "expected_failure_evidence_sha256"),
    ("raw_reviewed_authorization", "expected_reviewed_authorization_sha256"),
])
def test_each_recovery_artifact_is_bound_to_original_bytes(raw_key, digest_key):
    material = recovery_material()
    material[raw_key] += b"\n"
    with pytest.raises(ValueError, match="original bytes hash mismatch"):
        recover_prelaunch_failure(**material)
    material[digest_key] = sha256_bytes(material[raw_key])
    # Rehashing one artifact cannot silently update the independently bound chain.
    if raw_key != "raw_reviewed_authorization":
        with pytest.raises(ValueError):
            recover_prelaunch_failure(**material)


@pytest.mark.parametrize("field,value", [("job_id", "100"), ("bundle_sha256", "8" * 64), ("gate_sha256", "8" * 64)])
def test_second_execution_cannot_reuse_a_job_or_escape_the_reviewed_bundle_gate(field, value):
    arguments = {"job_id": "101", "bundle_sha256": "6" * 64, "gate_sha256": "7" * 64}
    arguments[field] = value
    with pytest.raises(ValueError):
        record_execution(recovered_state(), **arguments)


def test_second_recovery_is_forbidden_even_with_fresh_self_consistent_metadata():
    failed_again = record_failure(recovered_execution(), "MPI failed again", stage="mpi_prelaunch")
    with pytest.raises(ValueError, match="only one original"):
        recover_prelaunch_failure(**recovery_material(failed_again))


@pytest.mark.parametrize("change", ["old_receipt", "latest_receipt", "extra_attempt", "counter", "candidate", "missing_event"])
def test_resealed_recovery_history_cannot_be_rewritten(change):
    state = recovered_execution()
    row = state["evaluations"][0]
    if change == "old_receipt":
        row["execution_history"][0]["job_id"] = "999"
    elif change == "latest_receipt":
        row["execution"]["job_id"] = "999"
    elif change == "extra_attempt":
        row["execution_history"].append(copy.deepcopy(row["execution"]))
    elif change == "counter":
        state["executed_dft_jobs"] = 1
    elif change == "candidate":
        row["request"]["candidate_structure_sha256"] = NEXT_STRUCTURE
        row["request_sha256"] = sha256_json(row["request"])
    else:
        del row["prelaunch_recovery"]
    with pytest.raises(ValueError):
        validate_state(reseal(state))


@pytest.mark.parametrize("artifact", ["failed_state", "failure_evidence", "reviewed_authorization"])
def test_outer_reseal_does_not_replace_any_original_recovery_artifact_bytes(artifact):
    state = recovered_execution()
    reference = state["evaluations"][0]["prelaunch_recovery"][artifact]
    raw = base64.b64decode(reference["raw_base64"])
    reference["raw_base64"] = base64.b64encode(raw + b"\n").decode()
    with pytest.raises(ValueError, match="original bytes hash mismatch"):
        validate_state(reseal(state))


def test_original_failed_job_cannot_be_reused_in_a_later_scientific_round():
    state = advance_training(accept(recovered_execution()))
    state = prepare_dft_evaluation(state, candidate_structure_sha256=NEXT_STRUCTURE, search_checkpoint_sha256=TRAINED)
    with pytest.raises(ValueError, match="already recorded"):
        record_execution(state, job_id="100", bundle_sha256="8" * 64, gate_sha256="9" * 64)
