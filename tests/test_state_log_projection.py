from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.state_manager.audit import audit_repository
from scripts.state_manager.models import StateEvent
from scripts.state_manager.projections import log_entry_text
from scripts.state_manager.proposals import apply_proposal, build_proposal, StaleProposal
from tests.test_state_manager import event_payload, file_evidence, init_repository, store


@pytest.fixture
def log(tmp_path):
    policy, schema = init_repository(tmp_path)
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("synthetic reviewed error evidence\n", encoding="utf-8")
    ledger = store(tmp_path, schema)
    target = tmp_path / "docs/04_ERROR_LOG.md"
    manifest = tmp_path / "data/state_handoff/projection_manifest.json"

    def prepare(identifier="error-one"):
        event = StateEvent.from_mapping(event_payload(
            identifier, "error_opened", "error", identifier,
            {"markdown": f"### {identifier}\n\nReviewed original body.\n- source detail."},
            evidence=file_evidence(evidence, tmp_path), review_required=True), schema_path=schema)
        ledger.record(event)
        proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
        ledger.record_review(proposal_id=proposal["proposal_id"], decision="approve", reviewer="user",
                             reviewed_event_id=event.event_id, reviewed_event_sha256=event.digest)
        return event, proposal

    event, proposal = prepare()
    apply_proposal(proposal, event_store=ledger, project_root=tmp_path, policy_path=policy)
    return tmp_path, policy, ledger, target, manifest, event, prepare


def drift(root: Path, policy: Path) -> set[str]:
    return {row["code"] for row in audit_repository(project_root=root, policy_path=policy)["findings"]
            if "docs/04_ERROR_LOG.md" in row["paths"]}


def make_legacy(manifest: Path, event: StateEvent):
    payload = load_json_object(manifest)
    record = payload["projections"].pop(f"docs/04_ERROR_LOG.md#event_entry:{event.event_id}")
    record.pop("managed_unit")
    record.pop("managed_unit_sha256")
    payload["projections"]["docs/04_ERROR_LOG.md"] = record
    write_json(manifest, payload)


@pytest.mark.parametrize("legacy", [False, True])
def test_unrelated_append_preserves_valid_event_projection_without_rehashing(log, legacy):
    root, policy, ledger, target, manifest, event, _ = log
    if legacy:
        make_legacy(manifest, event)
    target.write_text(target.read_text(encoding="utf-8") + "\n## Another manual record\n\nUnmanaged text.\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (target, manifest)}
    assert "managed_projection_drift" not in drift(root, policy)
    assert all(path.read_bytes() == data for path, data in before.items())
    if not legacy:
        record = next(iter(load_json_object(manifest)["projections"].values()))
        assert record["managed_unit"] == {"kind": "event_entry", "id": event.event_id}
        assert sha256_file(target) != record["target_sha256_after"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("damage", ["body", "marker", "duplicate", "delete", "suffix"])
def test_owned_entry_edits_remain_drift(log, legacy, damage):
    root, policy, ledger, target, manifest, event, _ = log
    if legacy:
        make_legacy(manifest, event)
    text = target.read_text(encoding="utf-8")
    entry = log_entry_text(text, event)
    if damage == "body":
        text = text.replace("Reviewed original body.", "Changed body.")
    elif damage == "marker":
        text = text.replace(f"event {event.event_id}", "event another-id")
    elif damage == "duplicate":
        text += "\n" + entry
    elif damage == "delete":
        text = text.replace(entry, "")
    else:
        text = text.replace("- source detail.\n", "- source detail. appended forged content\n")
    target.write_text(text, encoding="utf-8")
    assert "managed_projection_drift" in drift(root, policy)


@pytest.mark.parametrize("damage", ["hash", "missing_event", "rejected", "wrong_target", "unit_id", "missing_unit_hash"])
def test_unknown_unapproved_or_misbound_source_is_not_accepted(log, damage, monkeypatch):
    root, policy, ledger, target, manifest, event, _ = log
    payload = load_json_object(manifest)
    key = f"docs/04_ERROR_LOG.md#event_entry:{event.event_id}"
    record = payload["projections"][key]
    if damage == "hash":
        record["source_event_sha256"] = "0" * 64
    elif damage == "missing_event":
        (ledger.events_dir / f"{event.event_id}.json").unlink()
    elif damage == "rejected":
        from scripts.state_manager import store as store_module
        latest = max(row.payload["recorded_at"] for row in ledger.load_all())
        later = (datetime.fromisoformat(latest.replace("Z", "+00:00")) + timedelta(seconds=1)).isoformat()
        monkeypatch.setattr(store_module, "utc_now", lambda: later)
        ledger.record_review(proposal_id="synthetic-rejection", decision="reject", reviewer="user",
                             reviewed_event_id=event.event_id, reviewed_event_sha256=event.digest)
        assert ledger.event_decision(event.event_id) == "reject"
    elif damage == "wrong_target":
        other = root / "docs/03_DECISIONS_LOG.md"
        other.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        payload["projections"][f"docs/03_DECISIONS_LOG.md#event_entry:{event.event_id}"] = payload["projections"].pop(key)
    elif damage == "unit_id":
        record["managed_unit"]["id"] = "another-event"
    else:
        record.pop("managed_unit_sha256")
    write_json(manifest, payload)
    codes = {row["code"] for row in audit_repository(project_root=root, policy_path=policy)["findings"]}
    assert codes & {"managed_projection_drift", "projection_manifest_invalid"}


def test_legacy_fallback_requires_source_digest_and_approval(log):
    root, policy, ledger, target, manifest, event, _ = log
    make_legacy(manifest, event)
    payload = load_json_object(manifest)
    payload["projections"]["docs/04_ERROR_LOG.md"]["source_event_sha256"] = "0" * 64
    write_json(manifest, payload)
    target.write_text(target.read_text(encoding="utf-8") + "\nUnrelated addition.\n", encoding="utf-8")
    assert "managed_projection_drift" in drift(root, policy)


def test_new_entry_retains_previous_legacy_entry_coverage(log):
    root, policy, ledger, target, manifest, event, prepare = log
    make_legacy(manifest, event)
    second, proposal = prepare("error-two")
    apply_proposal(proposal, event_store=ledger, project_root=root, policy_path=policy)
    keys = load_json_object(manifest)["projections"]
    assert "docs/04_ERROR_LOG.md" in keys
    assert f"docs/04_ERROR_LOG.md#event_entry:{second.event_id}" in keys
    assert "managed_projection_drift" not in drift(root, policy)
    target.write_text(target.read_text(encoding="utf-8").replace("### error-one", "### Changed first entry"), encoding="utf-8")
    assert "managed_projection_drift" in drift(root, policy)


def test_whole_file_preapply_concurrency_check_is_preserved(log):
    root, policy, ledger, target, manifest, event, prepare = log
    second, proposal = prepare("error-two")
    target.write_text(target.read_text(encoding="utf-8") + "\nConcurrent manual entry.\n", encoding="utf-8")
    original = target.read_bytes()
    with pytest.raises(StaleProposal):
        apply_proposal(proposal, event_store=ledger, project_root=root, policy_path=policy)
    assert target.read_bytes() == original
    assert f"state-handoff:event {second.event_id}" not in target.read_text(encoding="utf-8")
