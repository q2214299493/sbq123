from __future__ import annotations

import pytest

from archive.fe110_reico_remaining_20261024 import submit as runner


def fixture(monkeypatch, tmp_path, status="NOT_RESERVED"):
    monkeypatch.setattr(runner.original,"DEST",tmp_path)
    row={"sample_id":"family_0015_step000","decision_sha256":"gatehash",
         "potcar_source":"~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR","potcar_sha256":"a"*64}
    receipt={"status":"SUBMITTED","job_id":"123456","gate_decision_sha256":"gatehash",
             "remote_dir":runner.original.REMOTE+"/"+row["sample_id"]}
    monkeypatch.setattr(runner,"submission_status",lambda path: receipt if status == "SUBMITTED" else {"status":status})
    return row,receipt


def test_only_never_reserved_case_reaches_native_executor(monkeypatch,tmp_path):
    row,receipt=fixture(monkeypatch,tmp_path)
    calls=[]

    def execute(*args):
        calls.append(args)
        return receipt

    monkeypatch.setattr(runner,"submit",execute)
    assert runner.submit_one(row)["job_id"] == "123456"
    assert len(calls)==1 and calls[0][-1] == "SUBMIT_DIAGNOSTIC_VASP"


def test_success_is_reused_without_second_submit(monkeypatch,tmp_path):
    row,_=fixture(monkeypatch,tmp_path,"SUBMITTED")
    monkeypatch.setattr(runner,"submit",lambda *args: pytest.fail("duplicate submit"))
    assert runner.submit_one(row)["job_id"] == "123456"


def test_unknown_attempt_is_not_retried(monkeypatch,tmp_path):
    row,_=fixture(monkeypatch,tmp_path,"UNKNOWN_NEEDS_RECONCILIATION")
    monkeypatch.setattr(runner,"submit",lambda *args: pytest.fail("unknown retry"))
    with pytest.raises(ValueError,match="must not be retried"):
        runner.submit_one(row)


def test_foreign_success_target_rejected(monkeypatch,tmp_path):
    row,receipt=fixture(monkeypatch,tmp_path)
    receipt["remote_dir"] += "_different"
    monkeypatch.setattr(runner,"submit",lambda *args: receipt)
    with pytest.raises(ValueError,match="exact approved scope"):
        runner.submit_one(row)


@pytest.mark.parametrize("limit",[0,-1])
def test_invalid_budget_never_loads_or_submits(monkeypatch,limit):
    monkeypatch.setattr(runner,"checked_scope",lambda: pytest.fail("invalid budget"))
    with pytest.raises(ValueError,match="must be positive"):
        runner.run(limit)


def test_serial_continuation_excludes_all_unknown_and_successful_cases(monkeypatch,tmp_path):
    from archive.fe110_reico_remaining_20261024 import continue_serial as serial
    rows=[{"sample_id":name} for name in ("already","unknown","untouched")]
    statuses={"already":"SUBMITTED","unknown":"UNKNOWN_NEEDS_RECONCILIATION","untouched":"NOT_RESERVED"}
    monkeypatch.setattr(serial,"OUTPUT",tmp_path)
    monkeypatch.setattr(serial.original,"DEST",tmp_path)
    monkeypatch.setattr(serial,"checked_scope",lambda:rows)
    monkeypatch.setattr(serial,"submission_status",lambda path:{"status":statuses[path.name]})
    calls=[]

    def execute(row):
        calls.append(row["sample_id"])
        statuses[row["sample_id"]]="SUBMITTED"
        return {"job_id":"123456"}

    monkeypatch.setattr(serial,"submit_one",execute)
    serial.run()
    assert calls == ["untouched"]
    serial.run()
    assert calls == ["untouched"]


def test_serial_failure_stops_before_next_untouched_case(monkeypatch,tmp_path):
    from archive.fe110_reico_remaining_20261024 import continue_serial as serial
    rows=[{"sample_id":name} for name in ("first","second")]
    monkeypatch.setattr(serial,"OUTPUT",tmp_path)
    monkeypatch.setattr(serial.original,"DEST",tmp_path)
    monkeypatch.setattr(serial,"checked_scope",lambda:rows)
    monkeypatch.setattr(serial,"submission_status",lambda path:{"status":"NOT_RESERVED"})
    calls=[]

    def failure(row):
        calls.append(row["sample_id"])
        raise RuntimeError("connection lost")

    monkeypatch.setattr(serial,"submit_one",failure)
    with pytest.raises(RuntimeError,match="connection lost"):
        serial.run()
    assert calls == ["first"]


def test_recovery_refuses_confirmation_without_human_duplicate_check(monkeypatch, tmp_path):
    from archive.fe110_reico_remaining_20261024 import recover16 as recovery
    monkeypatch.setattr(recovery, "sha256_file", lambda path: recovery.PROPOSAL_SHA)
    monkeypatch.setattr(recovery, "load_json_object", lambda path: {
        "proposal_sha256": recovery.PROPOSAL_SHA,
        "authorization_sha256": recovery.PROPOSAL_SHA,
        "user_reply": "确认16份无重复，提交新尝试",
        "no_matching_job_confirmed_by_human": False,
    })
    with pytest.raises(ValueError, match="explicit human recovery confirmation"):
        recovery.checked_cases()


def test_recovery_does_not_retry_unknown_new_attempt(monkeypatch, tmp_path):
    from archive.fe110_reico_remaining_20261024 import recover16 as recovery
    monkeypatch.setattr(recovery, "sha256_file", lambda path: "gatehash")
    monkeypatch.setattr(recovery, "submission_status", lambda path: {"status": "UNKNOWN_NEEDS_RECONCILIATION"})
    monkeypatch.setattr(recovery, "submit", lambda *args: pytest.fail("unknown new attempt retried"))
    with pytest.raises(ValueError, match="unknown fresh attempt must not be retried"):
        recovery.submit_one({"proposed_workdir": str(tmp_path), "decision_sha256": "gatehash"})
