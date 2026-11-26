from pathlib import Path

import pytest

from archive.fe110_pair2_submission_20261027 import submit as adapter
from scripts.artifact_io import sha256_file, write_json_exclusive


def scoped_plan(monkeypatch, tmp_path):
    source = tmp_path / "prepared"
    source.mkdir()
    auth = tmp_path / "authorization.md"
    auth.write_text("> 提交全部4项（推荐，完成C₂/C₃配对诊断）", encoding="utf-8")
    jobs = []
    for name, model in sorted(adapter.EXPECTED):
        folder = source / name / model
        folder.mkdir(parents=True)
        (folder / "POSCAR").write_text("synthetic scope fixture;not a structure", encoding="ascii")
        jobs.append({"name": name, "model": model, "path": str(folder.relative_to(tmp_path)), "files": {"POSCAR": sha256_file(folder / "POSCAR")}})
    plan = {"jobs": jobs, "budget": {"cores_each": 32, "NSW_each": 80, "force_criterion_eV_A": .02, "automatic_continuation_or_retry": False}}
    monkeypatch.setattr(adapter, "ROOT", tmp_path)
    monkeypatch.setattr(adapter, "PREP", source)
    monkeypatch.setattr(adapter, "AUTH", auth)
    monkeypatch.setattr(adapter, "source_file_manifest_valid", lambda _: True)
    return source, auth, plan


def test_exact_four_approved_inputs_accepted_without_computation(monkeypatch, tmp_path):
    source, _, plan = scoped_plan(monkeypatch, tmp_path)
    write_json_exclusive(source / "plan.json", plan)
    assert adapter.approved_plan() == plan


@pytest.mark.parametrize("change", ["count", "cores", "steps", "force", "retry", "human", "input"])
def test_scope_or_authority_expansion_rejected(monkeypatch, tmp_path, change):
    source, auth, plan = scoped_plan(monkeypatch, tmp_path)
    if change == "count":
        plan["jobs"].pop()
    elif change in ["cores", "steps", "force"]:
        key = {"cores": "cores_each", "steps": "NSW_each", "force": "force_criterion_eV_A"}[change]
        plan["budget"][key] = 999
    elif change == "retry":
        plan["budget"]["automatic_continuation_or_retry"] = True
    elif change == "human":
        auth.write_text("no authorization", encoding="ascii")
    else:
        (Path(adapter.ROOT) / plan["jobs"][0]["path"] / "POSCAR").write_text("changed", encoding="ascii")
    write_json_exclusive(source / "plan.json", plan)
    with pytest.raises(ValueError):
        adapter.approved_plan()


def test_existing_reservation_blocks_batch_without_duplicate_submit(monkeypatch, tmp_path):
    folder = tmp_path / "one"
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
    assert submitted == []
