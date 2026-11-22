"""Observe the complete temporary store independently of State Manager's success reports."""
import hashlib
import json
import os
import sqlite3

import pytest

from scripts.state_manager import cli
from scripts.state_manager.proposals import ProposalStore
from scripts.state_manager.state_compaction import build_state_history_compaction_event
from tests.test_state_manager import (
    END_MARKER,
    START_MARKER,
    file_evidence,
    init_repository,
    registered_projection,
    store,
    task_event,
)


def tree_hashes(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in root.rglob("*")
    }


def command(root, capsys, *args):
    result = cli.main(["--root", str(root), *args])
    return result, capsys.readouterr()


def assert_read_only(root, capsys, expected_code):
    initial = tree_hashes(root)
    previous = None
    for _ in range(2):
        code, output = command(root, capsys, "sync", "--safe-only")
        assert tree_hashes(root) == initial
        assert code == expected_code, output
        if previous is not None:
            assert output == previous
        previous = output
    return output


def task_fixture(root, *, managed):
    _, schema = init_repository(root)
    evidence = root / "source.txt"
    evidence.write_bytes(b"source observation\n")
    event = task_event("test-preview", evidence=file_evidence(evidence, root))
    target = root / "tasks/current_task.md"
    if managed:
        target.write_text(
            START_MARKER.format(block_id="current_task") + "\nold\n"
            + END_MARKER.format(block_id="current_task") + "\n", encoding="utf-8",
        )
    else:
        target.write_bytes(b"# Existing user task\n")
    source = root / "event-input.json"
    source.write_text(json.dumps(event.payload), encoding="utf-8")
    return source, target, event, store(root, schema)


@pytest.mark.parametrize("case", ["safe", "pending", "approved", "rejected", "stale", "drift"])
def test_preview_preserves_all_state(tmp_path, capsys, case):
    source, target, event, events = task_fixture(tmp_path, managed=case in {"safe", "stale", "drift"})
    if case in {"safe", "stale", "pending"}:
        events.record(event)  # No proposal cache exists on entry.
    else:
        code, out = command(tmp_path, capsys, "propose", "--event", str(source))
        info = json.loads(out.out)
        proposal_id = info["proposal_id"]
        assert code == int(case != "drift")
        if case == "drift":
            assert command(tmp_path, capsys, "apply", "--proposal", proposal_id)[0] == 0
            target.write_bytes(target.read_bytes().replace(b"Run one read-only audit.", b"manual change"))
            assert b"manual change" in target.read_bytes()
        else:
            decision = "approve" if case == "approved" else "reject"
            assert command(tmp_path, capsys, "review", "--proposal", proposal_id, "--decision", decision)[0] == 0

    if case == "stale":
        (tmp_path / "source.txt").write_bytes(b"changed observation")
        assert "evidence hash changed" in assert_read_only(tmp_path, capsys, 2).err
        return

    report = json.loads(assert_read_only(tmp_path, capsys, int(case == "pending")).out)
    assert report["applied"] == []
    if case == "pending":
        assert len(report["pending_review"]) == 1
    else:
        assert report["pending_review"] == []
    if case == "approved":
        assert report["preview"][0]["proposal_id"] == proposal_id
        code, out = command(tmp_path, capsys, "apply", "--proposal", proposal_id)
        assert code == 0 and "tasks/current_task.md" in json.loads(out.out)["changed"]
        assert event.payload["payload"]["objective"] in target.read_text(encoding="utf-8")
        cache = ProposalStore(tmp_path, tmp_path / "configs/state_handoff.yaml")
        receipt = cache.cache_dir / "applications" / f"{proposal_id}.json"
        assert json.loads(receipt.read_bytes())["status"] == "APPLIED"


@pytest.mark.parametrize("evidence", ["registry_only", "excel_only", "both"])
def test_safe_only_never_consults_or_consumes_receipts(tmp_path, capsys, monkeypatch, evidence):
    _, _, events, event = registered_projection(tmp_path)
    db = tmp_path / "data/project_registry.sqlite3"
    if evidence != "both":
        with sqlite3.connect(db) as conn:
            if evidence == "registry_only":
                conn.execute("DELETE FROM excel_promotions")
                (tmp_path / "data/registry_promotion_receipts/barrier.json").unlink()
            else:
                conn.execute("DELETE FROM ts_barriers")

    def unexpected_receipt_lookup(*args, **kwargs):
        pytest.fail("read-only sync entered receipt reuse")

    output = json.loads(assert_read_only(tmp_path, capsys, 1).out)
    with monkeypatch.context() as patch:
        patch.setattr(cli, "registry_excel_review_is_reusable", unexpected_receipt_lookup)
        assert command(tmp_path, capsys, "sync", "--safe-only")[0] == 1
    assert events.event_decision(event.event_id) is None
    assert len(output["pending_review"]) == 1
    proposal_id = output["pending_review"][0]["proposal_id"]
    code, out = command(tmp_path, capsys, "sync")
    report = json.loads(out.out)
    if evidence == "both":
        assert code == 0 and "tasks/current_task.md" in report["applied"]
        reviews = [item.payload["payload"] for item in events.history(proposal_id)]
        assert any(item.get("reviewer") == "registry_excel_receipt" and item["decision"] == "approve" for item in reviews)
    else:
        assert code == 1 and report["applied"] == []
        assert events.event_decision(event.event_id) is None


def test_blocked_later_compaction_leaves_earlier_safe_task_unapplied(tmp_path, capsys):
    _, _, task, events = task_fixture(tmp_path, managed=True)
    events.record(task)
    source = tmp_path / "docs/02_CURRENT_STATE.md"
    source.write_bytes(b"## Gate\n\n### Historical Evidence\n\nEarlier evidence.\n")
    # Compaction uses the file mtime as its recorded_at. Fix the event order.
    os.utime(source, (1893456000, 1893456000))
    compaction = build_state_history_compaction_event(
        project_root=tmp_path, section_heading="## Gate", archive_path="docs/history/previous.md",
    )
    events.record(compaction)
    assert task.payload["recorded_at"] < compaction.payload["recorded_at"]
    source.write_bytes(source.read_bytes() + b"Later evidence.\n")
    assert "state history source changed" in assert_read_only(tmp_path, capsys, 2).err
