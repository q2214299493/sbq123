from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.document_governance import (
    broken_links, classify_data, is_current_authority, read_document, wording_findings,
)
from scripts.generate_capability_readiness import build_readiness, generate
from scripts.registry_schema import CURRENT_VERSION

ROOT = Path(__file__).resolve().parents[1]


def fixture_root(tmp_path):
    payload = build_readiness(ROOT)
    for relative in payload["source_sha256"]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def test_supported_schema_and_production_are_separate():
    payload = build_readiness(ROOT)
    assert payload["supported_code_schema"] == CURRENT_VERSION == 9
    assert payload["production_schema_version"] == "NOT_VERIFIED_IN_B6"
    for name in ("README.md", "docs/02_CURRENT_STATE.md", "docs/06_MODULE_MAP.md", "docs/PUBLIC_RELEASE.md"):
        _, text = read_document(ROOT / name)
        assert "NOT_VERIFIED_IN_B6" in text
        assert not wording_findings(read_document(ROOT / name)[0], text)


def test_recorded_scheduler_observation_is_explicit():
    _, text = read_document(ROOT / "docs/02_CURRENT_STATE.md")
    assert "Last recorded scheduler status: PEND" in text
    assert "observed_at: 2026-09-07T11:15:50Z" in text
    assert "LAST_RECORDED_OBSERVATION" in text
    assert len(text.splitlines()) < 110


@pytest.mark.parametrize("name", ["FINAL_ARCHITECTURE.md", "FINAL_VERIFICATION_REPORT.md", "TS_ENDPOINT_CURRENT_ARCHITECTURE.md", "ARCHITECTURE.md"])
def test_historical_filenames_do_not_confer_authority(name):
    metadata, _ = read_document(ROOT / name)
    assert metadata["document_class"] == "HISTORICAL_SNAPSHOT"
    assert not is_current_authority(ROOT, name)


def test_one_authority_model_and_classification_for_root_reports():
    models = []
    for path in (ROOT / "docs").glob("*.md"):
        metadata, _ = read_document(path)
        if metadata.get("authority_model_id"):
            models.append(path.name)
    assert models == ["DOCUMENT_GOVERNANCE.md"]
    assert is_current_authority(ROOT, "docs/06_MODULE_MAP.md")
    for path in ROOT.glob("*.md"):
        metadata, _ = read_document(path)
        assert metadata["document_class"] != "UNKNOWN_REVIEW_REQUIRED", path


def test_readiness_generation_is_deterministic_and_matches_checked_in_view(tmp_path):
    root = fixture_root(tmp_path)
    first = {p.name: p.read_bytes() for p in generate(root)}
    second = {p.name: p.read_bytes() for p in generate(root)}
    assert first == second
    assert first == {name: (ROOT / "reports" / name).read_bytes() for name in first}
    assert json.loads(first["capability_readiness.json"])["authority"] == "DERIVED_NOT_AUTHORITATIVE"


def test_tests_and_status_do_not_invent_maturity_or_science():
    payload = build_readiness(ROOT)
    for row in payload["modules"]:
        assert row["scientific_validation"] not in {"validated", "partial"}
        assert row["production_readiness"] != "ready"
        if not row["evidence"]:
            assert row["implementation"] == "unknown"
            assert row["tests"] == ["unknown"]
    expected = {"kinetic_data": "Planned", **{name: "Blocked" for name in (
        "thermochemistry", "reaction_network", "baseline_mkm", "coverage_mkm", "surface_kmc",
        "reactor_simulation", "sensitivity_uncertainty")}}
    statuses = {row["module"]: row["module_status"] for row in payload["modules"]}
    assert {name: statuses[name] for name in expected} == expected


def test_scientific_validation_cannot_be_inferred_from_test_annotations(tmp_path):
    root = fixture_root(tmp_path)
    path = root / "docs/06_MODULE_MAP.md"
    text = path.read_text(encoding="utf-8").replace("scientific_validation: unknown", "scientific_validation: validated", 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="scientific evidence"):
        build_readiness(root)


@pytest.mark.parametrize("claim", [
    "The DIMER is currently running.",
    "The chemistry is validated because 1054 tests passed.",
    "This module is production ready.",
    "SUPPORTED_CODE_SCHEMA: 8",
    "Current code uses schema 8.",
    "The production registry has been migrated to v9.",
    "production_schema_version: 9",
    "The FINAL filename proves this is current.",
])
def test_current_claims_need_the_correct_evidence_but_history_is_allowed(claim):
    assert wording_findings({"document_class": "CURRENT_AUTHORITY"}, claim)
    assert not wording_findings({"document_class": "HISTORICAL_SNAPSHOT"}, claim)


def test_scoped_wording_is_allowed_without_global_word_bans():
    for line in ["Last recorded scheduler status: RUN; observed_at: 2026-08-27T00:00:00Z; source: recorded report",
                 "Currently running; observed_at: 2026-09-09T00:00:00Z; source: live scheduler evidence",
                 "Software tests passed; science is not validated.",
                 "This module is not production ready.", "HISTORICAL_SCHEMA: 8"]:
        assert not wording_findings({"document_class": "CURRENT_AUTHORITY"}, line)


def test_data_policy_covers_required_classes_and_locations():
    policy = yaml.safe_load((ROOT / "configs/data_governance.yaml").read_text(encoding="utf-8"))
    assert set(policy["classes"]) == {"SOURCE_CODE", "CONFIGURATION", "SCIENTIFIC_INPUT", "SCIENTIFIC_RAW_EVIDENCE",
        "SCIENTIFIC_ACCEPTED_RECORD", "PREDICTION", "DERIVED_REPORT", "RUNTIME_STATE", "HISTORICAL",
        "GENERATED_BUILD_METADATA", "SENSITIVE_EXCLUDED", "LARGE_EXTERNAL_ARTIFACT"}
    for definition in policy["classes"].values():
        assert {"allowed_locations", "git_tracking", "ai_scientific_evidence", "automatic_modification",
                "archive_policy", "public_snapshot", "evidence_condition"} <= definition.keys()
    expected = {"calculations/test/POSCAR": "SCIENTIFIC_INPUT", "calculations/test/OUTCAR": "SCIENTIFIC_RAW_EVIDENCE",
                "data/project_registry.sqlite3": "RUNTIME_STATE", "outputs/example/report.json": "DERIVED_REPORT",
                "reports/audit.md": "DERIVED_REPORT", "archive/old.json": "HISTORICAL",
                "configs/test.yaml": "CONFIGURATION", "tasks/current_task.md": "RUNTIME_STATE",
                "sbq_catalyst_agent_workflow.egg-info/PKG-INFO": "GENERATED_BUILD_METADATA"}
    for path, category in expected.items():
        assert classify_data(path, policy) == category
    assert "SCIENTIFIC_ACCEPTED_RECORD" not in {rule["class"] for rule in policy["rules"]}


def test_predictions_and_sensitive_artifacts_are_not_public_scientific_evidence():
    policy = yaml.safe_load((ROOT / "configs/data_governance.yaml").read_text(encoding="utf-8"))
    for path in ["outputs/predictions/data.json", "calculations/run/gpu_result_manifest.json", "data/candidates/structure.vasp"]:
        assert classify_data(path, policy) == "PREDICTION"
        assert policy["classes"]["PREDICTION"]["ai_scientific_evidence"] is False
    for path, expected in [("calculations/test/POTCAR", "SENSITIVE_EXCLUDED"), ("outputs/model.ckpt", "LARGE_EXTERNAL_ARTIFACT")]:
        assert classify_data(path, policy) == expected
        assert policy["classes"][expected]["public_snapshot"] == "no"
    assert classify_data("scripts/candidate_generation.py", policy) == "SOURCE_CODE"


def test_generation_cannot_touch_production_or_calculation_paths(tmp_path, monkeypatch):
    import sqlite3
    import subprocess
    root = fixture_root(tmp_path)
    outcar = root / "calculations/active/OUTCAR"
    outcar.parent.mkdir(parents=True)
    outcar.write_bytes(b"preserved raw evidence\r\n")
    database = root / "data/project_registry.sqlite3"
    database.parent.mkdir()
    database.write_bytes(b"do not open")
    def forbidden(*args, **kwargs):
        raise AssertionError("no database/remote/process access is allowed")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    generate(root)
    for name, data in before.items():
        assert (root / name).read_bytes() == data
    assert {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {p.as_posix() for p in before} == {
        "reports/capability_readiness.json", "reports/capability_readiness.md"}


def test_chronology_preserved_and_managed_gate_not_rewritten():
    metadata, history = read_document(ROOT / "docs/history/current_state_chronology_before_B6_20260909.md")
    _, current = read_document(ROOT / "docs/02_CURRENT_STATE.md")
    gate = re.search(r"<!-- state-handoff:start.*?<!-- state-handoff:end.*?-->", current, re.S).group()
    original = history.removeprefix("\n").replace("<!-- B6_MANAGED_GATE_RETAINED_IN_CURRENT_STATE -->", gate)
    assert hashlib.sha256(original.encode()).hexdigest() == metadata["original_current_state_sha256_lf"]
    assert "C₂**/η²-CC/C₂-2-diagonal" in history


def test_current_and_new_historical_links_resolve():
    for name in ["README.md", "docs/DOCUMENT_GOVERNANCE.md", "docs/02_CURRENT_STATE.md", "docs/06_MODULE_MAP.md",
                 "docs/PUBLIC_RELEASE.md", "reports/capability_readiness.md",
                 "docs/history/current_state_chronology_before_B6_20260909.md"]:
        assert broken_links(ROOT, name) == [], name


def test_unknown_document_does_not_gain_authority_by_filename(tmp_path):
    path = tmp_path / "LATEST_FINAL_CURRENT_VERIFIED_PASS.md"
    path.write_text("# Current\nCurrently running.\n")
    metadata, _ = read_document(path)
    assert metadata["document_class"] == "UNKNOWN_REVIEW_REQUIRED"


def test_software_only_source_cannot_validate_science_without_tests_in_sentence():
    assert wording_findings({"document_class": "CURRENT_REFERENCE", "evidence_kind": "SOFTWARE_TEST_RECORD"},
                            "The Fe chemistry is validated.")
