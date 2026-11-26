from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent.submission import InputBundle, preflight
from scripts.registry_schema import migrate_registry
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from tests.test_execution_lifecycle import authorize_evidence
from tests.test_vasp_inputs import ADSORPTION_POSCAR


def prepare(tmp_path: Path):
    workdir = tmp_path / "job"
    workdir.mkdir()
    (workdir / "POSCAR").write_text(ADSORPTION_POSCAR, encoding="ascii")
    (workdir / "candidate_manifest.json").write_text("{}", encoding="ascii")
    build_fe110_adsorption_relaxation(workdir)
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    return workdir, database


def test_adapter_reuses_adsorption_preflight_without_writing_in_read_mode(tmp_path):
    workdir, database = prepare(tmp_path)
    report = preflight(workdir, "adsorption_relaxation", learning_database=database, write_report=False)
    assert report["passed"] and report["adsorption_hard_gate_passed"]
    assert not (workdir / "submission_preflight.json").exists()
    assert not (workdir / "adsorption_submission_preflight.json").exists()
    bundle = InputBundle.from_preflight(report)
    bundle.verify(workdir)
    (workdir / "candidate_manifest.json").write_text('{"changed": true}', encoding="ascii")
    with pytest.raises(ValueError, match="bundle changed"):
        bundle.verify(workdir)


@pytest.mark.parametrize("fault", ["sigma", "manifest", "fixed"])
def test_adapter_rejects_incompatible_or_incomplete_inputs(tmp_path, fault):
    workdir, database = prepare(tmp_path)
    if fault == "sigma":
        p = workdir / "INCAR"
        p.write_text(p.read_text().replace("SIGMA = 0.2", "SIGMA = 0.1"), encoding="ascii")
    elif fault == "manifest":
        (workdir / "candidate_manifest.json").unlink()
    else:
        p = workdir / "POSCAR"
        p.write_text(p.read_text().replace("F F F", "T T T", 1), encoding="ascii")
    report = preflight(workdir, "adsorption_relaxation", learning_database=database)
    assert not report["passed"]
    decision = decide_execution({}, {}, {}, climb=False, path_reviewed=True, preflight=report)
    assert not decision["scientific_readiness"]["eligible_actions"]


def test_gate_requires_exact_authorization_and_rejects_stale_evidence(tmp_path):
    workdir, database = prepare(tmp_path)
    report = preflight(workdir, "adsorption_relaxation", learning_database=database)
    decision = decide_execution({}, {}, {"test": True}, climb=False, path_reviewed=True, preflight=report)
    assert decision["scientific_readiness"]["eligible_actions"] == ["SUBMIT_VASP"]
    assert decision["ALLOWED_ACTIONS"] == []
    evidence = decision["EVIDENCE"]
    for name in ("preflight", "thresholds"):
        path = workdir / (name + ".json")
        write_json(path, evidence[name])
        evidence["source_bindings"][name] = {"path": str(path), "sha256": sha256_file(path)}
    decision = authorize_evidence(workdir, evidence, action="SUBMIT_VASP")
    path = workdir / "decision.json"
    write_json(path, decision)
    require_action(path, "SUBMIT_VASP", decision["state_sha256"])
    (workdir / "approval.txt").write_text("changed", encoding="ascii")
    with pytest.raises(ValueError):
        require_action(path, "SUBMIT_VASP", decision["state_sha256"])
