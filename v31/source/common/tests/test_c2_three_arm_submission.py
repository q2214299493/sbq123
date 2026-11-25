"""The human's three-arm DFT submission cannot expand or reuse reservations."""
from pathlib import Path

import pytest

from archive.fe110_scratch512_20261028 import submit_c2_dft as adapter
from scripts.artifact_io import sha256_file, write_json_exclusive


def fixture_plan(tmp_path, monkeypatch):
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    auth = tmp_path / "authorization.md"
    auth.write_text("> 提交\n", encoding="utf-8")
    jobs = []
    for arm in adapter.ARMS:
        directory = prepared / arm
        directory.mkdir()
        (directory / "POSCAR").write_text("scope fixture;not a structure", encoding="ascii")
        jobs.append({"arm": arm, "path": str(directory.relative_to(tmp_path)), "files": {"POSCAR": sha256_file(directory / "POSCAR")}})
    plan = {"job_count": 3, "jobs": jobs, "budget": {"cores_each": 32, "NSW_each": 300,
        "DFT_force_criterion_eV_A": .02, "automatic_retry_or_continuation": False}}
    write_json_exclusive(prepared / "input_verification.json", {"core_inputs_hash_verified": 18, "direct_arm_original_bytes_and_no_ML_verified": True})
    for name, value in [("ROOT", tmp_path), ("PREP", prepared), ("AUTH", auth)]:
        monkeypatch.setattr(adapter, name, value)
    monkeypatch.setattr(adapter, "source_file_manifest_valid", lambda _: True)
    return prepared, auth, plan


def test_only_exact_three_reviewed_arms_normalized(tmp_path, monkeypatch):
    prepared, _, plan = fixture_plan(tmp_path, monkeypatch)
    write_json_exclusive(prepared / "plan.json", plan)
    accepted = adapter.approved_plan()
    assert [(row["name"], row["model"]) for row in accepted["jobs"]] == [("10_A", arm) for arm in adapter.ARMS]


@pytest.mark.parametrize("change", ["count", "cores", "steps", "force", "retry", "human", "input", "C3"])
def test_stale_inputs_or_scope_expansion_rejected(tmp_path, monkeypatch, change):
    prepared, auth, plan = fixture_plan(tmp_path, monkeypatch)
    if change == "count":
        plan["jobs"].pop()
    elif change in ["cores", "steps", "force"]:
        key = {"cores": "cores_each", "steps": "NSW_each", "force": "DFT_force_criterion_eV_A"}[change]
        plan["budget"][key] = 999
    elif change == "retry":
        plan["budget"]["automatic_retry_or_continuation"] = True
    elif change == "human":
        auth.write_text("no authorization", encoding="ascii")
    elif change == "C3":
        plan["jobs"][0]["arm"] = "C3_05"
    else:
        (Path(adapter.ROOT) / plan["jobs"][0]["path"] / "POSCAR").write_text("changed", encoding="ascii")
    write_json_exclusive(prepared / "plan.json", plan)
    with pytest.raises(ValueError):
        adapter.approved_plan()


def test_existing_or_ambiguous_submission_blocks_before_any_write(tmp_path, monkeypatch):
    folder = tmp_path / "arm"
    folder.mkdir()
    write_json_exclusive(tmp_path / "ready_for_submission.json", {"jobs": [{"directory": str(folder)}]})
    monkeypatch.setattr(adapter, "OUTPUT", tmp_path)
    monkeypatch.setattr(adapter, "approved_plan", lambda: None)
    monkeypatch.setattr(adapter, "source_file_manifest_valid", lambda _: True)
    monkeypatch.setattr(adapter, "submission_status", lambda _: {"status": "SUBMITTED"})
    submitted = []
    monkeypatch.setattr(adapter, "submit", lambda *args: submitted.append(args))
    with pytest.raises(ValueError, match="prior or ambiguous"):
        adapter.execute()
    assert not submitted
