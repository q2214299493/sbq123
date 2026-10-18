import json

import pytest

from scripts.artifact_io import sha256_file
from scripts.ts_strategy_engine.execution_evidence import source_bindings_valid

from archive.fe110_adsorption_validation_20261018.submit_06c_boundary import evidence_path, write_bound_json


def test_json_bound_geometry_uses_the_saved_types(tmp_path):
    path = tmp_path / "review.json"
    original = {"graph_adsorbate_local": [(45, 46), (46, 47)]}
    saved = write_bound_json(path, original)
    binding = {"validation": {"path": str(path), "sha256": sha256_file(path)}}
    assert saved == json.loads(path.read_bytes())
    assert saved != original
    assert source_bindings_valid({"validation": saved, "source_bindings": binding}, ("validation",))
    assert not source_bindings_valid({"validation": original, "source_bindings": binding}, ("validation",))


def test_existing_evidence_is_never_overwritten(tmp_path):
    path = tmp_path / "review.json"
    write_bound_json(path, {"first": True})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_bound_json(path, {"replacement": True})
    assert path.read_bytes() == original


def test_failed_draft_and_revised_binding_have_different_paths(tmp_path):
    assert evidence_path(tmp_path, "execution_decision") != tmp_path / "execution_decision.json"
