"""Check that a reviewed diagnostic wall limit reaches the canonical executor."""
from pathlib import Path
import shlex

import pytest

from scripts.artifact_io import load_json_object, write_json, sha256_file
from scripts.neb_agent import submission
from tests.test_execution_lifecycle import authorize_evidence, launch, prepare_submission


@pytest.mark.parametrize("minutes", (90, 135))
def test_bound_rank_count_and_wall_limit_reach_bsub(tmp_path, monkeypatch, minutes):
    workdir, decision_path, _ = prepare_submission(tmp_path, monkeypatch)
    (workdir / "script.lsf").write_text(f"NP=32\n#BSUB -W {minutes}\n", encoding="ascii")
    report = submission.preflight(workdir, "diagnostic_static")
    assert report["passed"]
    assert report["cores"] == 32
    assert report["wall_limit_minutes"] == minutes
    evidence = load_json_object(decision_path)["EVIDENCE"]
    evidence["preflight"] = report
    evidence["source_bindings"]["preflight"]["sha256"] = sha256_file(workdir / "submission_preflight.json")
    write_json(decision_path, authorize_evidence(workdir, evidence))
    commands = []

    def fake_run(argv):
        commands.append(argv[-1])
        return type("Result", (), {"stdout": "Job <123> is submitted"})()

    monkeypatch.setattr(submission, "_run", fake_run)
    monkeypatch.setattr(submission, "_upload_manifest_files", lambda *args: None)
    assert launch(workdir, decision_path)["job_id"] == "123"
    assert f"bsub -n 32 -W {minutes} script.lsf" in shlex.split(commands[-1])[2]


@pytest.mark.parametrize("option", ["-W 0", "-W 90/otherhost", "-W 90\n#BSUB -W 135"])
def test_invalid_or_duplicate_wall_limits_are_rejected(tmp_path: Path, option):
    script = tmp_path / "script.lsf"
    script.write_text(f"NP=32\n#BSUB {option}\n", encoding="ascii")
    errors = []
    assert not submission._resource_preflight(script, errors, kind="diagnostic_static", cores=32)
    assert errors and errors[0].startswith("invalid_lsf_directive:")


def test_wall_limit_does_not_change_other_submission_kinds(tmp_path: Path):
    script = tmp_path / "script.lsf"
    script.write_text("NP=32\n#BSUB -W 90\n", encoding="ascii")
    errors = []
    assert not submission._resource_preflight(script, errors, kind="ordinary_neb", cores=32)
    assert errors and errors[0].startswith("invalid_lsf_directive:")
    assert submission._bsub_command({}) == "bsub script.lsf"
