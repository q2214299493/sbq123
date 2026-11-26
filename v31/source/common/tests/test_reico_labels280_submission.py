import pytest

from archive.fe110_reico_sampling93_20261022 import submit as runner
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    dest = tmp_path / "batch"
    rows, ready = [], []
    for name in ("one", "two"):
        directory = dest / name
        directory.mkdir(parents=True)
        (directory / "POSCAR").write_text("unit fixture;not scientific input\n")
        (directory / "frame.json").write_text("{}\n")
        (directory / "execution_decision.json").write_text("{}\n")
        rows.append({"sample_id": name, "directory": str(directory), "cores": 32,
                     "input_hashes": {"POSCAR": sha256_file(directory / "POSCAR")},
                     "structure_path": str(directory / "POSCAR"), "structure_sha256": sha256_file(directory / "POSCAR"),
                     "frame_metadata_path": str(directory / "frame.json"),
                     "frame_metadata_sha256": sha256_file(directory / "frame.json")})
        ready.append({"sample_id": name, "decision_sha256": sha256_file(directory / "execution_decision.json"),
                      "potcar_source": "~/sbq/unit/POTCAR", "potcar_sha256": "a" * 64})
    write_json_exclusive(dest / "batch_request.json", {"samples": rows, "selection_sha256": runner.SELECTION_SHA})
    batch_sha = sha256_file(dest / "batch_request.json")
    write_json_exclusive(dest / "ready_for_submission.json", {"batch_sha256": batch_sha, "samples": ready})
    for name, value in {"ROOT": tmp_path, "DEST": dest, "BATCH_SHA": batch_sha, "COUNT": 2}.items():
        monkeypatch.setattr(runner, name, value)
    return dest, ready


def test_exact_batch(prepared):
    assert len(runner.checked_ready()) == 2


@pytest.mark.parametrize("relative", ["one/POSCAR", "one/frame.json", "two/execution_decision.json"])
def test_changed_bytes_rejected_before_remote_work(prepared, monkeypatch, relative):
    dest, _ = prepared
    (dest / relative).write_text("changed\n")
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("remote mutation must not occur"))
    with pytest.raises(ValueError, match="changed"):
        runner.submit_batch(0, 1)


def test_bounded_tranches_and_successful_receipts_are_reused(prepared, monkeypatch):
    dest, ready = prepared
    calls = []

    def state(directory):
        path = directory / "submission_record.json"
        return load_json_object(path) if path.exists() else {"status": "NOT_RESERVED"}

    def fake_submit(directory, decision, host, remote, potcar, potcar_sha, action):
        calls.append(directory.name)
        receipt = {"status": "SUBMITTED", "job_id": "123" if directory.name == "one" else "456",
                   "gate_decision_sha256": sha256_file(decision), "remote_dir": remote}
        write_json_exclusive(directory / "submission_record.json", receipt)
        return receipt

    monkeypatch.setattr(runner, "submission_status", state)
    monkeypatch.setattr(runner, "submit", fake_submit)
    runner.submit_batch(0, 1)
    assert calls == ["one"]
    assert not (dest / "two/submission_record.json").exists()
    runner.submit_batch(0, 1)
    assert calls == ["one"]
    runner.submit_batch(1, 1)
    assert calls == ["one", "two"]


def test_unknown_reservation_is_never_retried(prepared, monkeypatch):
    monkeypatch.setattr(runner, "submission_status", lambda d: {"status": "UNKNOWN_NEEDS_RECONCILIATION"})
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("unknown submission must not be repeated"))
    with pytest.raises(RuntimeError, match="unknown reservation"):
        runner.submit_batch(0, 1)


def test_foreign_success_receipt_is_rejected(prepared, monkeypatch):
    dest, ready = prepared
    receipt = {"status": "SUBMITTED", "job_id": "123", "gate_decision_sha256": ready[0]["decision_sha256"],
               "remote_dir": runner.REMOTE + "/foreign"}
    write_json_exclusive(dest / "one/submission_record.json", receipt)
    monkeypatch.setattr(runner, "submission_status", lambda d: receipt)
    with pytest.raises(ValueError, match="receipt does not match"):
        runner.submit_batch(0, 1)
    assert not (dest / "submission_tranche_000_001.json").exists()


@pytest.mark.parametrize("start,count", [(-1, 1), (0, 0), (0, 3), (2, 1)])
def test_invalid_tranche_has_no_remote_side_effect(prepared, monkeypatch, start, count):
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("out-of-range submission"))
    with pytest.raises(ValueError, match="invalid bounded"):
        runner.submit_batch(start, count)


def test_changed_master_scope_rejected(prepared):
    dest, _ = prepared
    (dest / "batch_request.json").write_text('{"samples": []}\n')
    with pytest.raises(ValueError, match="authorized batch changed"):
        runner.checked_batch()
