from pathlib import Path

import pytest

from archive.fe110_reico_sampling6_20261022 import submit as runner
from scripts.artifact_io import sha256_file, write_json_exclusive


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    dest = tmp_path / "batch"
    names = ["one", "two"]
    rows, ready = [], []
    for name in names:
        directory = dest / name
        directory.mkdir(parents=True)
        (directory / "POSCAR").write_text("unit fixture;not scientific input\n")
        (directory / "execution_decision.json").write_text("{}\n")
        rows.append({"sample_id": name, "directory": str(Path("batch") / name),
                     "input_hashes": {"POSCAR": sha256_file(directory / "POSCAR")}})
        ready.append({"sample_id": name, "decision_sha256": sha256_file(directory / "execution_decision.json"),
                      "potcar_source": "~/sbq/unit/POTCAR", "potcar_sha256": "a" * 64})
    write_json_exclusive(dest / "batch_request.json", {"samples": rows})
    batch_sha = sha256_file(dest / "batch_request.json")
    write_json_exclusive(dest / "ready_for_submission.json", {"batch_sha256": batch_sha, "samples": ready})
    for name, value in {"ROOT": tmp_path, "DEST": dest, "BATCH_SHA": batch_sha, "SAMPLES": names}.items():
        monkeypatch.setattr(runner, name, value)
    return dest, ready


def test_exact_batch_hash_and_inputs(prepared):
    assert len(runner.checked_batch()["samples"]) == 2


def test_changed_input_rejected_without_submission(prepared, monkeypatch):
    dest, _ = prepared
    (dest / "one/POSCAR").write_text("changed\n")
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("remote mutation must not occur"))
    with pytest.raises(ValueError, match="input bytes"):
        runner.submit_batch()


def test_existing_submission_is_not_repeated(prepared, monkeypatch):
    dest, ready = prepared
    calls = []
    monkeypatch.setattr(runner, "submission_status", lambda directory: {"status": "SUBMITTED" if directory.name == "one" else "NOT_RESERVED"})

    def receipt(name):
        return {"status": "SUBMITTED", "job_id": "123" if name == "one" else "456",
                "gate_decision_sha256": ready[0]["decision_sha256"], "remote_dir": runner.REMOTE + "/" + name}

    write_json_exclusive(dest / "one/submission_record.json", receipt("one"))

    def fake_submit(directory, *args):
        calls.append(directory.name)
        return receipt(directory.name)

    monkeypatch.setattr(runner, "submit", fake_submit)
    runner.submit_batch()
    assert calls == ["two"]


def test_unknown_reservation_is_never_retried(prepared, monkeypatch):
    monkeypatch.setattr(runner, "submission_status", lambda directory: {"status": "UNKNOWN_SUBMISSION_OUTCOME"})
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("unknown submission must not be repeated"))
    with pytest.raises(RuntimeError, match="unknown reservation"):
        runner.submit_batch()


def test_stale_gate_is_rejected_before_submission(prepared, monkeypatch):
    dest, _ = prepared
    (dest / "one/execution_decision.json").write_text('{"changed":true}\n')
    monkeypatch.setattr(runner, "submit", lambda *a: pytest.fail("stale gate must not be submitted"))
    with pytest.raises(ValueError, match="gate changed"):
        runner.submit_batch()
