"""Scientific evidence boundaries for the read-only path label audit."""
import pytest

from archive.fe110_c2_path_reuse_20261118.audit import classification, magnetic_decision
from archive.fe110_c2_path_reuse_20261118.review import scheduler_summary


def row(tables=(), **changes):
    return {"coordinate_force_match": True, "electronic_pass": True, "compatibility_pass": True,
            "protected_overlap": False, "magnetic": magnetic_decision(tables, 49), **changes}


def test_positive_total_cannot_replace_missing_local_moments():
    sample = row(total_magnetization_muB=105.)
    assert classification(sample) == "DIAGNOSTIC_REUSE_ONLY_MAGNETIC_BLOCKED"
    assert sample["magnetic"]["local_magnetization_muB"] is None


def test_nonpositive_iron_cannot_be_hidden_by_later_positive_table():
    first, last = [2.2] * 45 + [0.] * 4, [2.3] * 45 + [0.] * 4
    first[18] = -.2
    assert classification(row([first, last])) == "DIAGNOSTIC_REUSE_ONLY_MAGNETIC_BLOCKED"
    assert not magnetic_decision([last], 49)["magnetic_global_ground_state_verified"]


def test_protected_label_stays_outside_training():
    assert classification(row([[2.2] * 45 + [0.] * 4], protected_overlap=True)) == "BLOCKED_TRAINING_PROTECTED_SOURCE"


@pytest.mark.parametrize("failed", ["coordinate_force_match", "electronic_pass", "compatibility_pass"])
def test_magnetism_cannot_override_failed_force_or_method_binding(failed):
    assert classification(row([[2.2] * 45 + [0.] * 4], **{failed: False})) == "BLOCKED_SOURCE_OR_COMPATIBILITY"


def test_controller_success_never_fabricates_scheduler_completion():
    result = scheduler_summary({"document_kind": "slurm_native_controller_exit_events", "controller_exit_status": 0})
    assert result["recorded_scheduler_state"] is None
    assert result["controller_exit_status"] == 0


def test_native_job_state_is_preserved_in_its_own_schema():
    result = scheduler_summary({"document_kind": "slurm_force_label_scheduler_evidence", "job_state": "COMPLETED", "exit_code": "0:0"})
    assert result["recorded_scheduler_state"] == "COMPLETED"
    assert result["recorded_exit_code"] == "0:0"
