"""Saddle-energy review must not accept a stale output or another claim."""
import sqlite3
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.ts_validation.saddle_energy import _require_registered_saddle, _saddle_sources


@pytest.mark.parametrize("method", ["dimer", "ci_neb"])
def test_saddle_output_resolution_and_mutation_rejection(tmp_path: Path, method):
    run = tmp_path / "run"
    image = run if method == "dimer" else run / "04"
    image.mkdir(parents=True)
    paths = (image / "CONTCAR", image / "OUTCAR", run / "INCAR", image / "OSZICAR")
    for path in paths:
        path.write_text(path.name, encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    write_json_exclusive(handoff, {"source_ts_candidate": str(paths[0])})
    state = {"source_method": method, "vfa_handoff": handoff.name,
             "source_files": [{"path": str(p), "sha256": sha256_file(p)} for p in paths]}
    assert _saddle_sources(state, tmp_path / "analysis.json")[0] == paths
    state["source_files"] = [item for item in state["source_files"] if item["path"] != str(paths[1])]
    with pytest.raises(ValueError, match="unbound or stale"):
        _saddle_sources(state, tmp_path / "analysis.json")


def test_changed_saddle_claim_refused_before_registry_query():
    with sqlite3.connect(":memory:") as db:
        with pytest.raises(ValueError, match="does not name this saddle energy"):
            _require_registered_saddle(db,
                {"barrier_claim": {"ts_result_id": "original", "source_calculation_id": "saddle"}},
                {"calculation_id": "saddle", "result_id": "other"}, {})
