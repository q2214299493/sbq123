"""Offline launcher resolution; never executes Codex or starts a model turn."""
from pathlib import Path

import pytest

from scripts.ts_strategy_engine.review_app_server import executable


SHIM = '''@echo off
set "CODEX_CONFIG=%USERPROFILE%\\.codex\\config.toml"
for /f "tokens=2 delims='" %%I in ('findstr CODEX_CLI_PATH') do set "CODEX_REAL=%%I"
if not defined CODEX_REAL set "CODEX_REAL=%~dp0..\\bin\\codex.exe"
"%CODEX_REAL%" %*
'''


def launcher(tmp_path, monkeypatch):
    root = tmp_path / "App With Spaces"
    path = root / "cli" / "codex.cmd"
    path.parent.mkdir(parents=True)
    path.write_text(SHIM, encoding="utf-8")
    profile = tmp_path / "user"
    (profile / ".codex").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(profile))
    return path, profile / ".codex" / "config.toml"


def native(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"offline fixture, not an executable")
    return path


def point(config, target):
    config.write_text(f"CODEX_CLI_PATH = '{target}'\n", encoding="utf-8")


def test_current_target_wins_over_multiple_retained_versions(tmp_path, monkeypatch):
    shim, config = launcher(tmp_path, monkeypatch)
    target = native(tmp_path / "WindowsApps" / "new-version" / "codex.exe")
    for name in ("old-a", "old-b"):
        native(shim.parent.parent / "bin" / name / "codex.exe")
    point(config, target)
    assert executable(str(shim)) == target.resolve()


def test_update_is_resolved_again_without_changing_entry(tmp_path, monkeypatch):
    shim, config = launcher(tmp_path, monkeypatch)
    first = native(tmp_path / "v1" / "codex.exe")
    second = native(tmp_path / "v2" / "codex.exe")
    point(config, first)
    assert executable(str(shim)) == first.resolve()
    point(config, second)
    assert executable(str(shim)) == second.resolve()


@pytest.mark.parametrize("configured", [True, False])
def test_modern_launcher_uses_its_exact_unversioned_fallback(tmp_path, monkeypatch, configured):
    shim, config = launcher(tmp_path, monkeypatch)
    if configured:
        point(config, tmp_path / "removed-version" / "codex.exe")
    target = native(shim.parent.parent / "bin" / "codex.exe")
    assert executable(str(shim)) == target.resolve()


def test_modern_launcher_never_guesses_a_retained_old_version(tmp_path, monkeypatch):
    shim, config = launcher(tmp_path, monkeypatch)
    point(config, tmp_path / "removed-version" / "codex.exe")
    native(shim.parent.parent / "bin" / "old" / "codex.exe")
    with pytest.raises(FileNotFoundError, match="no current target"):
        executable(str(shim))


@pytest.mark.parametrize("target", ["relative/codex.exe", "absolute.cmd"])
def test_reject_nonabsolute_or_nonnative_target(tmp_path, monkeypatch, target):
    shim, config = launcher(tmp_path, monkeypatch)
    point(config, tmp_path / target if target == "absolute.cmd" else Path(target))
    with pytest.raises(ValueError, match="absolute native"):
        executable(str(shim))


def test_changed_modern_launcher_requires_review(tmp_path, monkeypatch):
    shim, config = launcher(tmp_path, monkeypatch)
    point(config, native(tmp_path / "v1" / "codex.exe"))
    shim.write_text("CODEX_CLI_PATH with unknown launch behavior", encoding="utf-8")
    with pytest.raises(ValueError, match="layout changed"):
        executable(str(shim))


def test_large_launcher_is_rejected_before_parsing(tmp_path, monkeypatch):
    shim, _ = launcher(tmp_path, monkeypatch)
    shim.write_text("x" * 65537, encoding="ascii")
    with pytest.raises(ValueError, match="unexpectedly large"):
        executable(str(shim))


def test_explicit_native_path_keeps_existing_contract(tmp_path):
    target = native(tmp_path / "v1" / "codex.exe")
    assert executable(str(target)) == target.resolve()
    with pytest.raises(FileNotFoundError):
        executable(str(tmp_path / "missing" / "codex.exe"))


def test_legacy_launcher_keeps_ambiguity_guard(tmp_path):
    shim = tmp_path / "cli" / "codex.cmd"
    shim.parent.mkdir()
    shim.write_text("@echo off", encoding="ascii")
    first = native(tmp_path / "bin" / "one" / "codex.exe")
    assert executable(str(shim)) == first.resolve()
    native(tmp_path / "bin" / "two" / "codex.exe")
    with pytest.raises(ValueError, match="actual codex.exe"):
        executable(str(shim))


def test_path_discovery_uses_the_same_resolver(tmp_path, monkeypatch):
    shim, config = launcher(tmp_path, monkeypatch)
    target = native(tmp_path / "v1" / "codex.exe")
    point(config, target)
    monkeypatch.setattr("scripts.ts_strategy_engine.review_app_server.shutil.which", lambda _: str(shim))
    assert executable(None) == target.resolve()
