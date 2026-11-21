from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.document_governance import (
    broken_links, classify_data, is_current_authority, read_document, wording_findings,
)
from scripts.generate_capability_readiness import build_readiness, generate
from scripts.registry_schema import CURRENT_VERSION

ROOT = Path(__file__).resolve().parents[1]


B6_STATE = ROOT / "tests/fixtures/document_governance/b6_publication_current_state.md"


def fixture_root(tmp_path):
    payload = build_readiness(ROOT)
    for relative in [*payload["source_sha256"], payload["module_map_projection"]["manifest"]]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def test_supported_schema_and_production_are_separate():
    payload = build_readiness(ROOT)
    assert payload["supported_code_schema"] == CURRENT_VERSION == 9
    assert payload["production_schema_version"] == "NOT_VERIFIED_IN_B6"
    governance, _ = read_document(ROOT / "docs/DOCUMENT_GOVERNANCE.md")
    assert governance["owners"]["production_schema"] == payload["production_schema_version"]
    for name in public_documents():
        meta, text = read_document(ROOT / name)
        if "production_schema_version" in meta:
            assert meta["production_schema_version"] == payload["production_schema_version"]
        assert not wording_findings(meta, text)


def public_documents():
    names = ["README.md", "docs/02_CURRENT_STATE.md", "docs/06_MODULE_MAP.md"]
    # Publication checkouts also have a release mapping linked from their README.
    if (ROOT / "docs/PUBLIC_RELEASE.md").is_file():
        names.append("docs/PUBLIC_RELEASE.md")
    return names


def test_recorded_scheduler_observation_is_explicit():
    _, text = read_document(B6_STATE)
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
    # Classify the versioned repository documents; local untracked drafts are review inputs.
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", ":(top,glob)*.md"], cwd=ROOT)
    model, _ = read_document(ROOT / "docs/DOCUMENT_GOVERNANCE.md")
    names = set(tracked.decode("utf-8").strip("\0").split("\0")) | set(model["preserved_historical_documents"])
    for name in names:
        path = ROOT / name
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
    governance, _ = read_document(ROOT / "docs/DOCUMENT_GOVERNANCE.md")
    _, text = read_document(ROOT / governance["owners"]["module_status"])
    expected = dict(re.findall(r"(?m)^\| `([^`]+)` \| (\w+) \|", text))
    statuses = {row["module"]: row["module_status"] for row in payload["modules"]}
    assert statuses == expected


def test_historical_b6_status_belongs_to_its_recorded_sources():
    snapshot = ROOT / "reports/multiphase/stage_a2_4/history/publication/capability_readiness.json"
    data = snapshot.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "21c83a36f9fb2c94995a9dd61cc73aa46cc1276cc1511224c1a2f116e2c4be9b"
    historical = json.loads(data)
    assert historical["source_version"] == "3a1bb3f461147a7dc9b5df5efca89de621d27f38"
    statuses = {row["module"]: row["module_status"] for row in historical["modules"]}
    assert statuses["thermochemistry"] == "Blocked"
    assert statuses["kinetic_data"] == "Planned"


def test_missing_project_evidence_blocks_execution_even_for_implemented_modules(tmp_path):
    from scripts.baseline_mkm.single_point import IncompleteKinetics, qualify

    root = fixture_root(tmp_path)
    path = root / "docs/06_MODULE_MAP.md"
    meta, _ = read_document(path)
    _, header, _ = path.read_text("utf8").split("---\n", 2)
    assert meta["document_class"] == "CURRENT_AUTHORITY"
    # Fixed synthetic lifecycle and evidence, independent of any current project.
    path.write_text("---\n" + header + "---\n"
                    "| `baseline_mkm` | Active | inputs | execution gate |\n"
                    "| `ts_library` | Completed | inputs | software only |\n"
                    "```capability-evidence\nts_library:\n  implementation: 'yes'\n  tests: [unit]\n"
                    "  evidence: [scripts/registry_schema.py]\n```\n", encoding="utf8")
    manifest = root / build_readiness(ROOT)["module_map_projection"]["manifest"]
    manifest.write_text('{"projections": {}}', encoding="utf8")
    report = build_readiness(root)
    mkm, ts = report["modules"]
    assert mkm["module_status"] == "Active" and ts["implementation"] == "yes"
    assert ts["module_status"] == "Completed" and ts["scientific_validation"] == "unknown"
    assert report["project_execution_eligibility"] == "not_assessed"
    assert all(row["production_readiness"] == "unverified" for row in (mkm, ts))
    directory = ROOT / "reports/multiphase"
    dataset = json.loads((directory / "phase2_4/fe110_parameters.json").read_bytes())
    network = json.loads((directory / "networks" / f"network-{dataset['network_version']}.json").read_bytes())
    with pytest.raises(IncompleteKinetics) as exc:
        qualify(network, dataset, {})
    assert exc.value.missing == {r["reaction_id"]: r["missing"] for r in dataset["reactions"] if not r["export_eligible"]}


def test_managed_row_drift_is_reported_without_changing_the_binding(tmp_path):
    root = fixture_root(tmp_path)
    original = build_readiness(root)
    projection = original["module_map_projection"]
    name = next(iter(projection["rows"]))
    path = root / original["module_status_source"]
    lines = path.read_text("utf8").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"| `{name}` |"))
    lines[index] = lines[index].rstrip("|") + " fixture edit |"
    path.write_text("\n".join(lines) + "\n", encoding="utf8")
    manifest = root / projection["manifest"]
    before = manifest.read_bytes()
    changed = build_readiness(root)
    row = changed["module_map_projection"]["rows"][name]
    assert row["state"] == "review_required"
    assert row["expected_sha256"] == projection["rows"][name]["expected_sha256"] != row["observed_sha256"]
    assert changed["input_sha256"] != original["input_sha256"]
    assert manifest.read_bytes() == before


def test_scientific_validation_cannot_be_inferred_from_test_annotations(tmp_path):
    root = fixture_root(tmp_path)
    path = root / "docs/06_MODULE_MAP.md"
    text = path.read_text(encoding="utf-8")
    annotation = {"implementation": "yes", "tests": ["unit", "integration"],
                  "evidence": ["scripts/registry_schema.py"], "scientific_validation": "validated"}
    start, rest = text.split("```capability-evidence\n", 1)
    _, end = rest.split("```", 1)
    path.write_text(start + "```capability-evidence\n" + yaml.safe_dump({"baseline_mkm": annotation}) + "```" + end,
                    encoding="utf-8")
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
    database.parent.mkdir(exist_ok=True)
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
    _, current = read_document(B6_STATE)
    gate = re.search(r"<!-- state-handoff:start.*?<!-- state-handoff:end.*?-->", current, re.S).group()
    original = history.removeprefix("\n").replace("<!-- B6_MANAGED_GATE_RETAINED_IN_CURRENT_STATE -->", gate)
    assert hashlib.sha256(original.encode()).hexdigest() == metadata["original_current_state_sha256_lf"]
    assert "C₂**/η²-CC/C₂-2-diagonal" in history


def test_current_and_new_historical_links_resolve():
    for name in [*public_documents(), "docs/DOCUMENT_GOVERNANCE.md", "reports/capability_readiness.md",
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
