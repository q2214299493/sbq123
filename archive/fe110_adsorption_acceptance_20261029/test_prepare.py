"""Negative admission and resumable-collection checks for this reviewed handoff."""
import json

import pytest

from archive.fe110_adsorption_acceptance_20261029 import collect
from archive.fe110_adsorption_acceptance_20261029.prepare import checked_decision


def test_converged_state_without_scheduler_done_cannot_be_accepted():
    record = {"name": "a", "job_id": "1", "blockers": []}
    with pytest.raises(ValueError, match="scheduler DONE"):
        checked_decision(record, {"decision": "accept"}, {"scheduler_evidence": {}}, {})


def test_done_does_not_override_scientific_failure():
    record = {"name": "a", "job_id": "1", "blockers": ["convergence"]}
    with pytest.raises(ValueError, match="blocked"):
        checked_decision(record, {"decision": "accept"},
                         {"scheduler_evidence": {"1": {"status": "DONE"}}}, {})


def test_duplicate_requires_an_accepted_matched_representative():
    record = {"name": "a", "job_id": "1", "blockers": []}
    analysis = {"scheduler_evidence": {}, "comparisons": [
        {"first": "a", "second": "b", "duplicate": True}]}
    decision = {"decision": "duplicate", "duplicate_of": "b"}
    with pytest.raises(ValueError, match="accepted representative"):
        checked_decision(record, decision, analysis, {"b": {"decision": "needs_review"}})
    assert checked_decision(record, decision, analysis, {"b": {"decision": "accept"}}) == "duplicate"


def test_cached_collection_rejects_changed_source_before_remote_access(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT", tmp_path)
    directory = tmp_path / "sources/a"
    directory.mkdir(parents=True)
    (directory / "INCAR").write_text("changed")
    (directory / "collection.json").write_text(json.dumps({"job_id": "1", "remote": {
        "files": {"INCAR": {"sha256": "0" * 64}}}}))
    with pytest.raises(ValueError, match="changed collected evidence"):
        collect.collect_snapshot({"name": "a", "job_id": "1"})
