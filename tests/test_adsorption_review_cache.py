from __future__ import annotations

import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.adsorption import review_completed_batch as review
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json


@pytest.fixture
def batch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    policy = tmp_path / "configs/adsmind_lite/analysis_rules.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("duplicate_detection: {}\n", encoding="utf-8")
    slab = tmp_path / "slab.POSCAR"
    slab.write_text("synthetic slab", encoding="utf-8")
    candidate = tmp_path / "input/candidate_manifest.json"
    candidate.parent.mkdir()
    write_json(candidate, {"invalid": False})
    sources = tmp_path / "sources"
    directory = sources / "case_01"
    directory.mkdir(parents=True)
    for name in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "KPOINTS"):
        (directory / name).write_text("synthetic " + name, encoding="utf-8")
    receipt = {"submission": {"workdir": str(candidate.parent)},
               "remote": {"files": {path.name: {"sha256": sha256_file(path)} for path in directory.iterdir()}}}
    write_json(directory / "collection.json", receipt)
    calls = []
    control = {"during_analysis": None}

    def analyze(directory, slab, analysis):
        calls.append(directory)
        invalid = load_json_object(candidate)["invalid"]
        record = {"name": directory.name, "directory": str(directory.resolve()),
                  "candidate_manifest_sha256": sha256_file(candidate),
                  "collection_sha256": sha256_file(directory / "collection.json"),
                  "ionic_steps": 1, "fmax_movable_eV_A": 0.01, "final_toten_eV": -1.0,
                  "blockers": ["fixture_manifest_blocker"] if invalid else [],
                  "eligible_for_review": not invalid, "scientific_acceptance": False, "duplicate_of": None}
        if control["during_analysis"]:
            control["during_analysis"]()
        return record

    monkeypatch.setattr(review, "read_poscar", lambda path: object())
    monkeypatch.setattr(review, "analyze_one", analyze)
    monkeypatch.setattr(review, "mark_duplicates", lambda records, slab, rules: [])
    outputs = []

    def run(source=sources):
        output = tmp_path / f"review_{len(outputs)}.json"
        outputs.append(output)
        monkeypatch.setattr(sys, "argv", ["review_completed_batch", "--sources", str(source),
                                         "--slab", str(slab), "--output", str(output)])
        review.main()
        return load_json_object(output)

    return SimpleNamespace(run=run, calls=calls, control=control, outputs=outputs, sources=sources,
                           directory=directory, candidate=candidate, slab=slab, policy=policy,
                           caches=tmp_path / "parsed")


def test_unchanged_inputs_reuse_bound_cache_without_acceptance(batch):
    first = batch.run()
    cache = next(batch.caches.glob("*.json"))
    original = cache.read_bytes()
    second = batch.run()
    assert len(batch.calls) == 1
    assert first["cache_misses"] == second["cache_hits"] == 1
    assert first["records"] == second["records"]
    assert second["scientific_acceptance"] is second["registry_written"] is False
    assert cache.read_bytes() == original


def test_candidate_manifest_change_invalidates_old_eligibility(batch):
    first = batch.run()
    old = {path: path.read_bytes() for path in batch.caches.glob("*.json")}
    receipt = (batch.directory / "collection.json").read_bytes()
    write_json(batch.candidate, {"invalid": True})
    second = batch.run()
    assert first["records"][0]["eligible_for_review"] is True
    assert second["records"][0]["eligible_for_review"] is False
    assert second["cache_misses"] == 1 and len(batch.calls) == 2
    assert (batch.directory / "collection.json").read_bytes() == receipt
    assert all(path.read_bytes() == data for path, data in old.items())


def test_imported_parser_object_change_invalidates_cache(batch, monkeypatch):
    batch.run()

    def changed_parser(path):
        return {"changed parser": str(path)}

    monkeypatch.setattr(review, "parse_final_outcar", changed_parser)
    assert batch.run()["cache_misses"] == 1
    assert len(batch.calls) == 2


def test_parser_source_bytes_change_without_reimport_invalidates_cache(batch, tmp_path, monkeypatch):
    path = tmp_path / "test_parser_owner.py"
    text = "def parser(path):\n    return 1\n"
    path.write_text(text, encoding="utf-8")
    namespace = {"__name__": "cache_test_parser"}
    exec(compile(text, str(path), "exec"), namespace)
    monkeypatch.setattr(review, "parse_final_outcar", namespace["parser"])
    batch.run()
    path.write_text(text.replace("return 1", "return 2"), encoding="utf-8")
    assert batch.run()["cache_misses"] == 1
    assert len(batch.calls) == 2


@pytest.mark.parametrize("field", ["slab", "policy"])
def test_reference_or_policy_change_invalidates_cache(batch, field):
    batch.run()
    path = getattr(batch, field)
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    assert batch.run()["cache_misses"] == 1
    assert len(batch.calls) == 2


@pytest.mark.parametrize("damage", ["legacy", "malformed", "record_hash", "binding", "manifest", "collection", "directory", "acceptance", "duplicate"])
def test_unbound_damaged_or_promoted_cache_is_not_reused_and_is_preserved(batch, damage):
    batch.run()
    cache = next(batch.caches.glob("*.json"))
    payload = load_json_object(cache)
    if damage == "legacy":
        payload = payload["record"]
    elif damage == "binding":
        payload["binding"]["cache_version"] = 1
    elif damage == "record_hash":
        payload["record"]["eligible_for_review"] = False
    elif damage in {"manifest", "collection"}:
        payload["record"]["candidate_manifest_sha256" if damage == "manifest" else "collection_sha256"] = "0" * 64
    elif damage == "directory":
        payload["record"]["directory"] = "another directory"
    elif damage == "acceptance":
        payload["record"]["scientific_acceptance"] = True
    elif damage == "duplicate":
        payload["record"]["duplicate_of"] = "prior-batch-only"
    if damage not in {"legacy", "record_hash"}:
        payload["record_sha256"] = sha256_json(payload["record"])
    if damage == "malformed":
        cache.write_text("{broken", encoding="utf-8")
    else:
        write_json(cache, payload)
    before = cache.read_bytes()
    result = batch.run()
    assert result["cache_misses"] == 1 and len(batch.calls) == 2
    assert result["records"][0]["scientific_acceptance"] is False
    assert result["records"][0]["duplicate_of"] is None
    assert cache.read_bytes() == before


@pytest.mark.parametrize("change", ["manifest_missing", "collected_changed"])
def test_missing_or_changed_current_evidence_blocks_cache_reuse(batch, change):
    batch.run()
    if change == "manifest_missing":
        batch.candidate.unlink()
    else:
        (batch.directory / "OUTCAR").write_text("changed", encoding="utf-8")
    with pytest.raises((FileNotFoundError, ValueError)):
        batch.run()
    assert len(batch.calls) == 1 and not batch.outputs[-1].exists()


def test_manifest_change_during_analysis_publishes_neither_cache_nor_output(batch):
    batch.control["during_analysis"] = lambda: write_json(batch.candidate, {"invalid": True})
    with pytest.raises(ValueError, match="changed while reading"):
        batch.run()
    assert not list(batch.caches.glob("*.json"))
    assert not batch.outputs[-1].exists()


def test_same_receipt_at_different_collected_directory_cannot_reuse_wrong_provenance(batch):
    batch.run()
    other = batch.sources.parent / "other_sources"
    shutil.copytree(batch.sources, other)
    result = batch.run(other)
    assert len(batch.calls) == 2 and result["cache_misses"] == 1
    assert result["records"][0]["directory"] == str((other / "case_01").resolve())


def test_batch_duplicate_marking_does_not_leak_into_cached_record(batch, monkeypatch):
    def mark(records, slab, rules):
        records[0]["duplicate_of"] = "only-in-this-batch"
        return []

    monkeypatch.setattr(review, "mark_duplicates", mark)
    assert batch.run()["records"][0]["duplicate_of"] == "only-in-this-batch"
    monkeypatch.setattr(review, "mark_duplicates", lambda records, slab, rules: [])
    result = batch.run()
    assert result["cache_hits"] == 1 and result["records"][0]["duplicate_of"] is None


def test_parser_change_during_batch_review_blocks_output(batch, monkeypatch):
    def changed(path):
        return {"another parser": str(path)}

    def mark(records, slab, rules):
        monkeypatch.setattr(review, "parse_final_outcar", changed)
        return []

    monkeypatch.setattr(review, "mark_duplicates", mark)
    with pytest.raises(ValueError, match="parser code changed"):
        batch.run()
    assert not batch.outputs[-1].exists()


def test_manifest_change_during_duplicate_review_blocks_output(batch, monkeypatch):
    def mark(records, slab, rules):
        write_json(batch.candidate, {"invalid": True})
        return []

    monkeypatch.setattr(review, "mark_duplicates", mark)
    with pytest.raises(ValueError, match="candidate evidence changed"):
        batch.run()
    assert not batch.outputs[-1].exists()


def test_real_parser_binding_is_stable_across_fresh_processes(batch):
    code = ("from pathlib import Path; import sys; "
            "from scripts.adsorption.review_completed_batch import analysis_binding; "
            "from scripts.artifact_io import sha256_json; "
            "print(sha256_json(analysis_binding(Path(sys.argv[1]),Path(sys.argv[2]))))")
    results = [subprocess.run([sys.executable, "-c", code, str(batch.slab), str(batch.policy)],
                             cwd=review.Path(review.__file__).resolve().parents[2],
                             text=True, capture_output=True, check=True).stdout.strip() for _ in range(2)]
    assert results[0] == results[1] and len(results[0]) == 64
