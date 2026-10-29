"""Budget and scheduler-stage checks without SSH or calculation execution."""
from pathlib import Path
import shutil

import pytest

from scripts.adsorption.preflight_fe110_adsorption import preflight
from scripts.aqcat25_ts_schema import validate_document
from scripts.artifact_io import sha256_text
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.vasp_result_gate import read_incar_values


def test_production_300_changes_only_nsw(tmp_path):
    root = Path(__file__).resolve().parents[1]
    seed = root / "calculations/fe110_c2_adsorption_11_15_20261020/candidates_v5/11_A/POSCAR"
    shutil.copyfile(seed, tmp_path / "POSCAR")
    build_fe110_adsorption_relaxation(tmp_path, screening=True, write_local_moments=True)
    old = read_incar_values(tmp_path / "INCAR")
    build_fe110_adsorption_relaxation(tmp_path, screening=False, write_local_moments=True)
    new = read_incar_values(tmp_path / "INCAR")
    assert old.pop("NSW") == "80" and new.pop("NSW") == "300"
    assert old == new
    (tmp_path / "candidate_manifest.json").write_text('{"relaxation_stage":"routine_production","write_local_moments":true}', encoding="ascii")
    assert preflight(tmp_path, write_report=False)["passed"]


@pytest.mark.parametrize("stage,allowed", [("adsorption_relaxation", True), ("ordinary_neb", True), ("invented", False)])
def test_adsorption_scheduler_schema_is_explicit(stage, allowed):
    stdout = "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n123 user RUN q host node job today\n"
    doc = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": stage,
        "scheduler": "LSF", "server_alias": "sunboquan-codex", "job_id": "123", "status": "RUN",
        "checked_at": "2026-10-29T07:00:00Z", "source_command": "ssh sunboquan-codex bjobs -a -w 123",
        "query": {"argv": ["ssh", "sunboquan-codex", "bjobs", "-a", "-w", "123"], "returncode": 0,
            "stdout": stdout, "stderr": "", "stdout_sha256": sha256_text(stdout)}}
    if allowed:
        assert validate_document(doc, expected_kind="scheduler_job_evidence") == doc
    else:
        with pytest.raises(ValueError):
            validate_document(doc, expected_kind="scheduler_job_evidence")
