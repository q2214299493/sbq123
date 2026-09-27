from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import scheduler_evidence
from scripts.execution_backends import (
    load_execution_backends,
    require_gpu_backend,
    require_gpu_write_path,
    require_vasp_backend,
)
from scripts.neb_agent import submission
from scripts.ts_strategy_engine.active_learning_common import load_policy
from scripts.vasp_result_gate import validate_lsf_done_evidence


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "execution_backends.yaml"
ACTIVE_LEARNING_POLICY = ROOT / "configs" / "aqcat25_ts_active_learning.yaml"


def test_runtime_backend_contract_loads_authoritative_values() -> None:
    backends = load_execution_backends()
    assert (backends.vasp.server_alias, backends.vasp.name) == (
        "sunboquan-codex",
        "LSF",
    )
    assert (backends.gpu.hostname, backends.gpu.scheduler) == ("MZ73", "Slurm")
    assert backends.gpu.remote_write_boundary == "/home/sbq/sbq"
    assert require_vasp_backend("sunboquan-codex", "LSF") == backends.vasp
    assert require_gpu_backend("MZ73", "Slurm") == backends.gpu
    assert require_gpu_write_path("/home/sbq/sbq/project/model.pt") == (
        "/home/sbq/sbq/project/model.pt"
    )
    with pytest.raises(ValueError, match="escapes"):
        require_gpu_write_path("/home/sbq/sbq-other/model.pt")


def test_runtime_backend_contract_rejects_weakened_authority(tmp_path: Path) -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    payload["authority"]["automatic_remote_submission"] = "allowed"
    changed = tmp_path / "execution_backends.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="automatic remote submission"):
        load_execution_backends(changed)
    with pytest.raises(ValueError, match="authoritative VASP backend"):
        require_vasp_backend("other-host", "LSF")
    with pytest.raises(ValueError, match="AQCat GPU backend"):
        require_gpu_backend("other-host", "Slurm")


def test_explicit_alternate_is_scoped_and_keeps_default(tmp_path: Path) -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    payload["backends"]["vasp"]["authorized_alternates"] = {
        "reviewed-temp": {"scheduler": "LSF", "scope": "reviewed-job"}
    }
    changed = tmp_path / "execution_backends.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_execution_backends(changed).vasp.server_alias == "sunboquan-codex"
    assert require_vasp_backend(
        "reviewed-temp", "LSF", path=changed, workdir_name="reviewed-job"
    ).server_alias == "reviewed-temp"
    with pytest.raises(ValueError, match="not authorized for this workdir"):
        require_vasp_backend("reviewed-temp", "LSF", path=changed, workdir_name="other-job")
    for host, scheduler in (("reviewed-temp", "Slurm"), ("unreviewed", "LSF")):
        with pytest.raises(ValueError, match="authoritative VASP backend"):
            require_vasp_backend(host, scheduler, path=changed)


def test_runtime_backend_contract_keeps_dimer_connectivity_diagnostic(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    rules = payload["scientific_rules"]
    assert rules["grade_a_requires_validated_vibrational_mode"] is True
    assert rules["dimer_grade_a_requires_bidirectional_connectivity"] is False
    assert rules["dimer_bidirectional_connectivity_role"] == (
        "optional_diagnostic_not_ts_acceptance_gate"
    )
    assert rules["neb_ci_neb_bidirectional_connectivity_policy"] == (
        "required_unchanged"
    )

    rules["dimer_grade_a_requires_bidirectional_connectivity"] = True
    changed = tmp_path / "execution_backends.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must not require bidirectional"):
        load_execution_backends(changed)


def test_active_learning_policy_cannot_override_backend_contract(tmp_path: Path) -> None:
    payload = yaml.safe_load(ACTIVE_LEARNING_POLICY.read_text(encoding="utf-8"))
    payload["vasp_force_label"]["backend"] = "other-host"
    changed = tmp_path / "active_learning.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="VASP backend conflicts"):
        load_policy(changed)


def test_scheduler_evidence_uses_configured_vasp_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def completed(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert argv == ["ssh", "sunboquan-codex", "bjobs", "-a", "123"]
        return subprocess.CompletedProcess(
            argv,
            0,
            "JOBID USER STAT\n123 user DONE\n",
            "",
        )

    monkeypatch.setattr(scheduler_evidence.subprocess, "run", completed)
    evidence = scheduler_evidence.query_lsf_job("123")
    assert (evidence["server_alias"], evidence["scheduler"]) == (
        "sunboquan-codex",
        "LSF",
    )
    validate_lsf_done_evidence(evidence)


def test_submission_rejects_unconfigured_host_before_filesystem_or_network(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="authoritative VASP backend"):
        submission.submit(
            tmp_path,
            tmp_path / "missing-decision.json",
            "other-host",
            "~/sbq/test/job",
            "~/sbq/potcars/POTCAR",
            "0" * 64,
            "SUBMIT_VASP",
        )


def test_remote_boundary_uses_canonical_home_and_keeps_symlink_guards() -> None:
    checks = submission._remote_path_checks("~/sbq/Fe110/ts/job")
    assert checks[0] == 'test "$(realpath -e ~/sbq)" = "$(realpath -e "$HOME")/sbq"'
    assert "test ! -L ~/sbq" in checks
    assert "test ! -L ~/sbq/Fe110/ts/job" in checks


def test_temporary_backend_scheduler_evidence_validates() -> None:
    from scripts.artifact_io import sha256_text
    from scripts.scheduler_evidence import validate_stored_lsf_evidence

    stdout = "JOBID USER STAT\n123 nsgkx_cdj1 PEND\n"
    evidence = {
        "schema_version": 1, "document_kind": "scheduler_job_evidence",
        "stage": "ordinary_neb", "scheduler": "LSF", "server_alias": "sunboquan-cdj1-temp",
        "job_id": "123", "status": "PEND", "checked_at": "2026-09-28T00:00:00Z",
        "source_command": "ssh sunboquan-cdj1-temp bjobs -a 123",
        "query": {"argv": ["ssh", "sunboquan-cdj1-temp", "bjobs", "-a", "123"],
                  "returncode": 0, "stdout": stdout, "stderr": "", "stdout_sha256": sha256_text(stdout)},
    }
    validate_stored_lsf_evidence(evidence)
    evidence["server_alias"] = "unreviewed-host"
    with pytest.raises(ValueError):
        validate_stored_lsf_evidence(evidence)
