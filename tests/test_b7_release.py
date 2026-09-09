from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts import artifact_io, runtime_resources
from scripts.optional_dependencies import require_optional
from scripts.release_smoke import run_smoke
from scripts.state_manager.stale_items import build_stale_item_event

ROOT = Path(__file__).resolve().parents[1]


def test_reviewed_resource_manifest_is_complete_and_safe():
    manifest = json.loads((ROOT / "configs/release_resources.json").read_text(encoding="utf-8"))
    names = manifest["package_runtime_resources"]
    assert names == sorted(set(names))
    for name in names:
        assert runtime_resources.resource_path(name).is_file()
        assert name.startswith(("configs/", "scripts/", "modules/calculation_registry/", "skills/catalysis-data-retrieval/references/"))
        assert Path(name).suffix in {".json", ".yaml", ".sql", ".sh", ".mjs", ".lsf"}
        assert not any(part in {"POTCAR", "WAVECAR", "CHGCAR", "events", "outputs", "calculations"} for part in Path(name).parts)
    assert "configs/execution_backends.yaml" in names
    assert "modules/calculation_registry/migrations/009_registry_governance.sql" in names
    assert "skills/catalysis-data-retrieval/references/record_schema.json" in names


@pytest.mark.parametrize("name", ["../escape", "/escape", "C:/escape", "C:escape", "\\\\server\\share\\file"])
def test_resource_paths_reject_cross_platform_escapes(name):
    with pytest.raises(ValueError, match="RESOURCE_PATH_INVALID"):
        runtime_resources.resource_path(name)


def test_resource_resolution_has_no_cwd_dependency(tmp_path, monkeypatch):
    expected = runtime_resources.resource_path("configs/execution_backends.yaml").read_bytes()
    monkeypatch.chdir(tmp_path)
    assert runtime_resources.resource_path("configs\\execution_backends.yaml").read_bytes() == expected
    with pytest.raises(ValueError, match="REPOSITORY_CONTEXT_REQUIRED"):
        runtime_resources.require_repository_context(tmp_path)


def test_explicit_repository_resource_cannot_escape_symlink(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/state_handoff.yaml").write_text("{}")
    (tmp_path / "pyproject.toml").write_text("")
    try:
        (tmp_path / "escape").symlink_to(ROOT / "README.md")
    except OSError:
        pytest.skip("symlink creation unavailable on this Windows account")
    with pytest.raises(ValueError, match="RESOURCE_UNAVAILABLE"):
        runtime_resources.resource_path("escape", repository=tmp_path)


def test_optional_dependency_message_is_capability_specific(monkeypatch):
    import scripts.optional_dependencies as dependencies
    def missing(name):
        raise ModuleNotFoundError(name)
    monkeypatch.setattr(dependencies, "import_module", missing)
    with pytest.raises(RuntimeError, match=r"CAPABILITY_UNAVAILABLE: semantic retrieval.*\[retrieval\]"):
        require_optional("sentence_transformers", "semantic retrieval")


@pytest.mark.parametrize("directory", ["sample.egg-info", "other.dist-info", "__pycache__"])
def test_generated_build_metadata_cannot_become_new_managed_state(tmp_path, directory):
    path = tmp_path / directory / "PKG-INFO"
    path.parent.mkdir()
    path.write_text("generated fixture")
    with pytest.raises(ValueError, match="GENERATED_BUILD_METADATA"):
        build_stale_item_event(project_root=tmp_path, path=path, disposition="keep", content_class="regenerable",
                               reason="release test", schema_path=ROOT / "configs/state_handoff_event.schema.json")


def test_repeated_atomic_publications_are_complete_or_explicit_conflicts(tmp_path):
    target = tmp_path / "shared.json"
    def publish(number):
        try:
            artifact_io.write_json_atomic(target, {"number": number, "body": str(number) * 5000})
        except PermissionError:
            return "sharing_conflict"
        return "published"
    with ThreadPoolExecutor(8) as pool:
        statuses = list(pool.map(publish, range(80)))
    assert "published" in statuses
    value = json.loads(target.read_text(encoding="utf-8"))
    assert value["body"] == str(value["number"]) * 5000
    assert not list(tmp_path.glob("*.tmp"))


def test_sharing_failure_preserves_previous_document_and_reservation(tmp_path, monkeypatch):
    target, reservation = tmp_path / "state.json", tmp_path / "reservation.json"
    artifact_io.write_json_atomic(target, {"old": True})
    artifact_io.write_json_exclusive(reservation, {"reserved": True})
    before = target.read_bytes(), reservation.read_bytes()
    def sharing_violation(*args):
        raise PermissionError("injected Windows sharing conflict")
    monkeypatch.setattr(artifact_io.os, "replace", sharing_violation)
    with pytest.raises(PermissionError, match="sharing conflict"):
        artifact_io.write_json_atomic(target, {"new": True})
    assert (target.read_bytes(), reservation.read_bytes()) == before
    assert not list(tmp_path.glob("*.tmp"))


def test_release_smoke_has_no_external_actions(tmp_path, monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError("release smoke attempted an external action")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = run_smoke(tmp_path)
    assert result["external_actions"] == 0 and not result["scientific_acceptance"]
    assert result["schema_version"] == 9 and result["idempotent"]


def test_clean_export_uses_index_not_untracked_or_modified_runtime(tmp_path):
    import subprocess
    from scripts.validate_release import clean_source
    source, destination = tmp_path / "source tree", tmp_path / "export tree"
    source.mkdir()
    subprocess.run(["git", "init", "--quiet", str(source)], check=True)
    (source / "tracked.txt").write_bytes(b"indexed\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=source, check=True)
    (source / "tracked.txt").write_bytes(b"unreviewed working change\n")
    (source / "runtime.db").write_bytes(b"must not be copied")
    clean_source(source, destination)
    assert (destination / "tracked.txt").read_text() == "indexed\n"
    assert not (destination / "runtime.db").exists()


def test_wheel_inspection_rejects_unreviewed_data_without_false_key_alarm(tmp_path):
    import zipfile
    from scripts.validate_release import audit_wheel
    wheel = tmp_path / "fixture.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("fixture.dist-info/WHEEL", "Wheel-Version: 1.0\n")
        archive.writestr("scripts/check.py", 'example = "-----BEGIN ' + 'PRIVATE KEY-----"\n')
    assert audit_wheel(wheel, [])["excluded_artifacts"] == []
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("data/private.sqlite3", "synthetic rejected fixture")
    with pytest.raises(ValueError, match="unreviewed wheel member"):
        audit_wheel(wheel, [])
