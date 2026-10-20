from unittest.mock import Mock

import pytest

from archive.fe110_adsorption_paired_vasp3_20261020 import submit as adapter
from scripts.artifact_io import load_json_object


def test_scope_change_rejected(monkeypatch):
    monkeypatch.setattr(adapter, "load_json_object", lambda p: {"jobs": []})
    with pytest.raises(ValueError, match="scope"):
        adapter.verified_manifest()


def test_reservation_blocks_retry(monkeypatch):
    monkeypatch.setattr(adapter, "submission_status", lambda p: {"status": "UNKNOWN_NEEDS_RECONCILIATION"})
    with pytest.raises(ValueError, match="reservation"):
        adapter.verified_manifest()


def test_all_gates_before_first_submission(monkeypatch):
    manifest = load_json_object(adapter.DEST / "batch_manifest.json")
    send = Mock()
    check = Mock(side_effect=[None, PermissionError("stale")])
    monkeypatch.setattr(adapter, "load_json_object", lambda p: {"state_sha256": "x"})
    monkeypatch.setattr(adapter, "require_action", check)
    monkeypatch.setattr(adapter, "submit", send)
    with pytest.raises(PermissionError, match="stale"):
        adapter.launch(manifest)
    send.assert_not_called()


def test_snapshot_does_not_infer_partial_submission(monkeypatch):
    monkeypatch.setattr(adapter, "submission_status", lambda p: {"status": "NOT_RESERVED"})
    query = Mock()
    monkeypatch.setattr(adapter, "query_lsf_job", query)
    with pytest.raises(ValueError, match="partial"):
        adapter.snapshot()
    query.assert_not_called()
