from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_bytes, canonical_json
from scripts.state_manager.proposals import apply_proposal, build_proposal, ProposalStore
from scripts.state_manager.models import StateEvent
from tests.test_state_manager import init_repository, store, task_event


def proposal_fixture(tmp_path):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    event = task_event("b4-task-001", objective="Implement B4")
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    event_store.record_review(proposal_id=proposal["proposal_id"], decision="approve", reviewer="reviewer")
    return proposal, dict(event_store=event_store, project_root=tmp_path, policy_path=policy)


def test_review_requirement_cannot_be_toggled(tmp_path):
    proposal, args = proposal_fixture(tmp_path)
    proposal["review_required"] = False
    with pytest.raises(ValueError, match="review"):
        apply_proposal(proposal, **args)
    assert not (tmp_path / "tasks/current_task.md").exists()


def test_rehashed_arbitrary_actions_do_not_gain_authority(tmp_path):
    proposal, args = proposal_fixture(tmp_path)
    proposal["actions"][0]["new_content"] = "unapproved replacement"
    core = {key: proposal[key] for key in ("schema_version", "event_id", "event_sha256", "actions")}
    proposal["plan_sha256"] = sha256_bytes(canonical_json(core))
    proposal["proposal_id"] = "proposal-" + proposal["plan_sha256"][:24]
    with pytest.raises(RuntimeError, match="authoritative"):
        apply_proposal(proposal, **args)


def test_state_mid_apply_failure_rolls_back_and_records_failure(tmp_path, monkeypatch):
    import scripts.state_manager.proposals as owner
    proposal, args = proposal_fixture(tmp_path)
    manifest = tmp_path / "data/state_handoff/projection_manifest.json"
    before = manifest.read_bytes()
    execute = owner._execute_action
    count = 0
    def fail(*a, **kw):
        nonlocal count
        count += 1
        execute(*a, **kw)
        if count == 2:
            raise OSError("injected second write failure")
    monkeypatch.setattr(owner, "_execute_action", fail)
    with pytest.raises(OSError, match="injected"):
        apply_proposal(proposal, **args)
    assert manifest.read_bytes() == before
    assert not (tmp_path / "tasks/current_task.md").exists()
    cache = ProposalStore(project_root=tmp_path, policy_path=args["policy_path"]).cache_dir
    failures = list((cache / "applications").glob("*.failed.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())["status"] == "FAILED"
    monkeypatch.setattr(owner, "_execute_action", execute)
    assert apply_proposal(proposal, **args)
    assert apply_proposal(proposal, **args) == []


def test_receipt_failure_rolls_back_state_files(tmp_path, monkeypatch):
    import scripts.state_manager.application_log as log
    proposal, args = proposal_fixture(tmp_path)
    write = log._write_immutable_json
    def fail(target, payload):
        if payload.get("status") == "APPLIED":
            raise OSError("receipt unavailable")
        return write(target, payload)
    monkeypatch.setattr(log, "_write_immutable_json", fail)
    with pytest.raises(OSError, match="receipt"):
        apply_proposal(proposal, **args)
    assert not (tmp_path / "tasks/current_task.md").exists()


def test_crashed_state_attempt_is_unknown_and_not_retried(tmp_path):
    from scripts.state_manager.application_log import reserved_application
    cache = tmp_path / "cache"
    script = """import os,sys
from pathlib import Path
from scripts.state_manager.application_log import reserved_application
p={'proposal_id':'proposal-crash','event_sha256':'a'*64,'actions':[],'review_required':False}
with reserved_application(Path(sys.argv[1]), p): os._exit(77)
"""
    result = subprocess.run([sys.executable, "-c", script, str(cache)], cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 77
    proposal = {"proposal_id": "proposal-crash", "event_sha256": "a" * 64, "actions": [], "review_required": False}
    with pytest.raises(RuntimeError, match="UNKNOWN_NEEDS_RECONCILIATION"):
        with reserved_application(cache, proposal):
            pytest.fail("must not retry a crashed attempt")
    assert json.loads((cache / "application.lock").read_text())["status"] == "UNKNOWN_NEEDS_RECONCILIATION"


def test_existing_event_cannot_be_rewritten(tmp_path):
    proposal, args = proposal_fixture(tmp_path)
    event = args["event_store"].get(proposal["event_id"])
    changed = copy.deepcopy(event.payload)
    changed["summary"] = "replace history"
    with pytest.raises(ValueError, match="immutable"):
        args["event_store"].record(StateEvent.from_mapping(changed))


def test_move_rollback_preserves_unrelated_sibling_manifest(tmp_path):
    from scripts.state_manager.proposals import _rollback
    source, target = tmp_path / "source.txt", tmp_path / "moved.txt"
    target.write_text("original content")
    manifest = tmp_path / "archive_manifest.json"
    manifest.write_text("unrelated existing manifest")
    _rollback(backups={}, archived=[(source, target)])
    assert source.read_text() == "original content"
    assert manifest.read_text() == "unrelated existing manifest"
    assert not target.exists()


def test_failed_rollback_retains_unknown_reservation(tmp_path, monkeypatch):
    import scripts.state_manager.proposals as owner
    proposal, args = proposal_fixture(tmp_path)
    execute = owner._execute_action
    def fail(*a, **kw):
        execute(*a, **kw)
        raise OSError("apply failure")
    def rollback_fails(**kw):
        raise OSError("rollback storage unavailable")
    monkeypatch.setattr(owner, "_execute_action", fail)
    monkeypatch.setattr(owner, "_rollback", rollback_fails)
    with pytest.raises(RuntimeError, match="UNKNOWN_NEEDS_RECONCILIATION"):
        apply_proposal(proposal, **args)
    cache = ProposalStore(project_root=tmp_path, policy_path=args["policy_path"]).cache_dir
    assert (cache / "application.lock").exists()
    with pytest.raises(RuntimeError, match="UNKNOWN_NEEDS_RECONCILIATION"):
        apply_proposal(proposal, **args)
