"""Synthetic only. No test invokes SSH, bsub, MPI, or VASP."""
from __future__ import annotations

import copy
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent import scf_repair_chain as chain
from scripts.neb_agent.scf_chain_bundle import build_runtime, check_bundle, launcher
from scripts.neb_agent.scf_chain_evidence import geometry_error, structure
from scripts.ts_strategy_engine.scf_chain_gate import ACTION, LIMITS, STAGES, scope_matches
from scripts.ts_strategy_engine.execution_gate import progress_decision

POSCAR = "test\n1\n4 0 0\n0 4 0\n0 0 4\nFe\n2\nSelective dynamics\nDirect\n0 0 0 F F F\n.5 .5 .5 T T T\n"


def build_case(path: Path) -> tuple[dict, dict]:
    path.mkdir(exist_ok=True)
    for name, text in {"POSCAR": POSCAR, "KPOINTS": "Gamma\n0\nGamma\n1 1 1\n0 0 0\n",
                       "POTCAR.spec": "Fe", "POTCAR": "synthetic only"}.items():
        (path / name).write_text(text)
    common = ("NSW=0\nIBRION=-1\nISPIN=2\nALGO=Normal\nNCORE=8\nNBANDS=320\n"
              "ENCUT=400\nLMAXMIX=4\nNELM=200\nEDIFF=1e-7\nSIGMA=.2\nLORBIT=11\n"
              "LWAVE=.TRUE.\nLCHARG=.TRUE.\nMAGMOM=2*2.2\n")
    for letter, (start, charge) in zip("ABC", ((0, 12), (0, 2), (1, 1))):
        (path / (letter + ".INCAR")).write_text(common + f"ISTART={start}\nICHARG={charge}\n")
    (path / "INCAR").write_bytes((path / "A.INCAR").read_bytes())
    state = {"energy": -10.0, "forces": [[0., 0., .1], [0., 0., -.1]], "moments": [2., 2.], "total_moment": 4.}
    write_json(path / "baseline.json", {"state": state, "geometry": structure(path / "POSCAR"),
                                       "source_files": {"OUTCAR": "a"*64}, "review_status": "REVIEWED"})
    executable = path / "fake_executable"
    executable.write_text("not executable")
    absolute = executable.as_posix()
    if os.name == "nt":
        absolute = absolute[2:]
    manifest = {
        "schema_version": 1, "stages": list(STAGES),
        "inputs": {name: sha256_file(path / name) for name in chain.INPUTS},
        "potcar_sha256": sha256_file(path / "POTCAR"),
        "runtime": {"executable": absolute, "executable_sha256": sha256_file(executable),
                    "mpirun": absolute, "mpirun_sha256": sha256_file(executable),
                    "ranks": 80, "stage_timeout_seconds": 60},
        "policy": {"geometry_A": 1e-5,
                   **{group: {key: {"warning": .01, "stop": .1} for key in LIMITS}
                      for group in ("baseline", "restart")}},
    }
    write_json(path / "scf_chain.json", manifest)
    permit = {"schema_version": 1, "action": ACTION, "stages": list(STAGES),
              "manifest_sha256": sha256_file(path / "scf_chain.json"), "runtime_sha256": "b"*64,
              "gate_sha256": "c"*64, "bundle_sha256": "d"*64,
              "target": {"server_alias": "sunboquan-codex", "remote_dir": "~/sbq/" + path.name}}
    return manifest, permit


def outputs(directory: Path, *, error: str = "", delta: float = 1e-8, energy: float = -10.,
            code: int = 0, ncore: int = 8, normal: bool = True, restarted: bool = True) -> int:
    root = directory.parent
    expected = chain.expected_runtime(root, STAGES.index(directory.name))
    expected["NCORE"] = ncore
    (directory / "OSZICAR").write_text(f"DAV: 1 -10 -.1 -.1 20 .1\nDAV: 2 -10 {delta} {delta} 20 .001\n 1 F= {energy} E0= {energy} mag= 4.0\n")
    text = f"vasp.5.4.1\ndistr: one band on NCORES_PER_BAND= {ncore} cores, 10 groups\n"
    text += "| For optimal performance NCORE= 4 - approx SQRT(number of cores) |\n"
    text += "\n".join(f"{k} = {v}" for k, v in expected.items() if k != "NCORE")
    text += ("\nIteration 1( 1)\nIteration 1( 2)\naborting loop because EDIFF is reached\n"
             f"free energy TOTEN = {energy} eV\nnumber of electron 16.0 magnetization 4.0\n"
             "magnetization (x)\n# of ion s p d tot\n---\n1 0 0 2 2\n2 0 0 2 2\n\n"
             "POSITION TOTAL-FORCE (eV/Angst)\n---\n0 0 0 0 0 .1\n2 2 2 0 0 -.1\n---\n")
    if normal:
        text += "General timing and accounting informations for this job\n"
    (directory / "OUTCAR").write_text(text)
    restart_text = "the WAVECAR file was read successfully\ncharge-density read from file: CHGCAR\n" if restarted else ""
    (directory / "vasp.out").write_text(error + restart_text)
    (directory / "CONTCAR").write_text(POSCAR)
    # Real-format minimal headers and two complete collinear charge grids.
    with (directory / "WAVECAR").open("wb") as handle:
        handle.write(struct.pack("<3d", 128., 2., 45200.))
        handle.seek(128)
        handle.write(struct.pack("<12d", 1., 320., 400., 4., 0., 0., 0., 4., 0., 0., 0., 4.))
        handle.truncate(128 * (2 + 2 * 321))
    (directory / "CHGCAR").write_text(POSCAR + "\n2 2 2\n1 1 1 1 1\n1 1 1\n\n2 2 2\n0 0 0 0 0\n0 0 0\n")
    return code


def run(path: Path, permit: dict) -> dict:
    return chain.run_chain(path, permit, job_id="12345", hosts=["node"]*80)


def test_three_stages_and_idempotent_resume(tmp_path, monkeypatch):
    _, permit = build_case(tmp_path)
    calls = []
    def fake(command, directory, timeout):
        calls.append(directory.name)
        if directory.name == STAGES[1]:
            assert not (directory / "WAVECAR").exists()
            assert not (directory / "CHGCAR").exists()
        if directory.name == STAGES[2]:
            assert (directory / "WAVECAR").read_bytes() == (tmp_path / STAGES[1] / "WAVECAR").read_bytes()
        return outputs(directory)
    monkeypatch.setattr(chain, "launch", fake)
    result = run(tmp_path, permit)
    assert calls == list(STAGES)
    assert result["status"] == "NUMERICAL_REPAIR_VERIFIED"
    assert result["scientific_acceptance"] is False
    assert run(tmp_path, permit) == result
    assert calls == list(STAGES)


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("failure", ["fatal", "nelm", "no_footer", "exit", "runtime", "empty_wave", "wrong_branch", "restart_not_read"])
def test_failed_stage_never_launches_next(tmp_path, monkeypatch, stage, failure):
    if stage == STAGES[0] and failure in {"empty_wave", "wrong_branch", "restart_not_read"}:
        pytest.skip("A is non-selfconsistent and cannot supply a restart")
    if stage != STAGES[2] and failure == "restart_not_read":
        pytest.skip("only C reads restart inputs")
    _, permit = build_case(tmp_path)
    calls = []
    def fake(command, directory, timeout):
        calls.append(directory.name)
        kwargs = {}
        if directory.name == stage:
            kwargs = {"fatal": {"error": "EDDDAV ZHEGV failed"}, "nelm": {"delta": 12.},
                      "no_footer": {"normal": False}, "exit": {"code": 1}, "runtime": {"ncore": 1},
                      "wrong_branch": {"energy": -6.}, "restart_not_read": {"restarted": False}}.get(failure, {})
        code = outputs(directory, **kwargs)
        if directory.name == stage and failure == "empty_wave":
            (directory / "WAVECAR").write_bytes(b"")
        return code
    monkeypatch.setattr(chain, "launch", fake)
    result = run(tmp_path, permit)
    assert result["status"] == "STOP"
    assert calls == list(STAGES[:STAGES.index(stage)+1])


def test_soft_warning_advances_and_no_zero_tolerance(tmp_path, monkeypatch):
    manifest, permit = build_case(tmp_path)
    monkeypatch.setattr(chain, "launch", lambda command, directory, timeout: outputs(directory, energy=-9.98))
    result = run(tmp_path, permit)
    assert result["status"] == "NUMERICAL_REPAIR_VERIFIED"
    assert result["stages"][1]["status"] == "PASS_WITH_WARNING"
    manifest["policy"]["baseline"]["energy_eV"]["warning"] = 0
    write_json(tmp_path / "scf_chain.json", manifest)
    with pytest.raises(ValueError):
        chain.precheck(tmp_path)


@pytest.mark.parametrize("what", ["input", "permit", "reservation", "lock", "wrong_slots"])
def test_no_launch_on_bad_bindings_or_uncertain_attempt(tmp_path, monkeypatch, what):
    _, permit = build_case(tmp_path)
    monkeypatch.setattr(chain, "launch", lambda *args: pytest.fail("must not launch"))
    if what == "input":
        (tmp_path / "B.INCAR").write_text("changed")
    elif what == "permit":
        permit["manifest_sha256"] = "e"*64
    elif what == "reservation":
        (tmp_path / STAGES[0]).mkdir()
    elif what == "lock":
        (tmp_path / "scf_chain.lock").write_text("existing")
    with pytest.raises((ValueError, PermissionError, RuntimeError, FileExistsError)):
        if what == "wrong_slots":
            chain.run_chain(tmp_path, permit, job_id="12345", hosts=["node"])
        else:
            run(tmp_path, permit)


def test_tampered_completed_output_blocks_resume(tmp_path, monkeypatch):
    _, permit = build_case(tmp_path)
    monkeypatch.setattr(chain, "launch", lambda command, directory, timeout: outputs(directory))
    run(tmp_path, permit)
    (tmp_path / STAGES[0] / "OUTCAR").write_text("tampered")
    monkeypatch.setattr(chain, "launch", lambda *args: pytest.fail("no retry"))
    with pytest.raises(ValueError, match="completed output changed"):
        run(tmp_path, permit)


def test_geometry_accepts_periodic_equivalence_not_drift(tmp_path):
    build_case(tmp_path)
    ref = structure(tmp_path / "POSCAR")
    other = copy.deepcopy(ref)
    other["positions"][1][0] += 4
    assert geometry_error(ref, other, 1e-5) < 1e-12
    other["positions"][1][0] += .02
    with pytest.raises(ValueError, match="drift"):
        geometry_error(ref, other, 1e-5)


def test_zipapp_precheck_does_not_execute(tmp_path):
    build_case(tmp_path)
    output = tmp_path / "scf_chain_runtime.pyz"
    build_runtime(output)
    (tmp_path / "script.lsf").write_text(launcher(80))
    assert check_bundle(tmp_path, 80)["passed"]
    result = subprocess.run([sys.executable, str(output), "--precheck", "--workdir", str(tmp_path)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["executed"] is False
    assert not any((tmp_path / stage).exists() for stage in STAGES)
    result = subprocess.run([sys.executable, str(output), "--workdir", str(tmp_path)],
                            capture_output=True, text=True, timeout=20,
                            env={k: v for k, v in os.environ.items() if k != "SCF_CHAIN_PERMIT"})
    assert result.returncode != 0


def test_initial_gate_requires_three_stage_scope():
    pre = {"kind": "scf_repair_chain", "passed": True, "files": {"scf_chain.json": "a"*64},
           "scf_chain": {"passed": True}}
    evidence = {"preflight": pre, "authorization": {"calculation_kind": "scf_repair_chain"}}
    analysis = {"status": "NO_OUTPUT"}
    assert not scope_matches(evidence)
    decision = progress_decision(analysis, {}, pre, {}, evidence, False, True)
    assert decision["ALLOWED_ACTIONS"] == []
    evidence["authorization"]["scf_chain_scope"] = {
        "manifest_sha256": "a"*64, "stages": list(STAGES), "max_allocations": 1, "retry": False}
    decision = progress_decision(analysis, {}, pre, {}, evidence, False, True)
    assert decision["ALLOWED_ACTIONS"] == [ACTION]


def test_canonical_preflight_gate_and_submission_permit(tmp_path, monkeypatch):
    import base64
    import re
    from functools import partial
    from types import SimpleNamespace
    from scripts.neb_agent import submission
    from scripts.registry_schema import migrate_registry
    from scripts.ts_strategy_engine.execution_evidence import TRUSTED_ARTIFACTS
    from scripts.ts_strategy_engine.execution_gate import decide_execution
    from tests.test_execution_lifecycle import authorize_evidence

    manifest, _ = build_case(tmp_path)
    build_runtime(tmp_path / "scf_chain_runtime.pyz")
    (tmp_path / "script.lsf").write_text(launcher(80))
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    monkeypatch.setattr(submission, "preflight", partial(submission.preflight, learning_database=database))
    report = submission.preflight(tmp_path, "scf_repair_chain")
    assert report["passed"], report["errors"]
    assert set(chain.INPUTS) <= set(report["files"])
    evidence = decide_execution({"status": "PASS"}, {"status": "NO_OUTPUT", "images": []},
                                {"test": True}, climb=False, path_reviewed=True, preflight=report)["EVIDENCE"]
    for name in ("geometry", "analysis", "thresholds", "preflight"):
        if name in TRUSTED_ARTIFACTS:
            kind, producer = TRUSTED_ARTIFACTS[name]
            evidence[name].update(document_kind=kind, producer=producer, source_files=[{
                "path": str(tmp_path / "INCAR"), "sha256": sha256_file(tmp_path / "INCAR"),
            }])
        path = tmp_path / ("submission_preflight.json" if name == "preflight" else name + ".json")
        write_json(path, evidence[name])
        evidence["source_bindings"][name] = {"path": str(path), "sha256": sha256_file(path)}
    denied = authorize_evidence(tmp_path, evidence)
    assert ACTION not in denied["ALLOWED_ACTIONS"]
    auth = evidence["authorization"]
    auth["scf_chain_scope"] = {"manifest_sha256": sha256_file(tmp_path / "scf_chain.json"),
                               "stages": list(STAGES), "max_allocations": 1, "retry": False}
    auth["potcar"]["sha256"] = manifest["potcar_sha256"]
    auth_path = tmp_path / "user_execution_authorization.json"
    write_json(auth_path, auth)
    evidence["source_bindings"]["authorization"]["sha256"] = sha256_file(auth_path)
    decision = decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                                climb=False, path_reviewed=True, preflight=report,
                                authorization=auth, source_bindings=evidence["source_bindings"])
    assert decision["ALLOWED_ACTIONS"] == [ACTION], decision.get("execution_authorization_error")
    decision_path = tmp_path / "decision.json"
    write_json(decision_path, decision)
    commands = []
    def fake_run(command):
        commands.append(command)
        return SimpleNamespace(stdout="Job <12345> is submitted to queue <test>.", returncode=0)
    monkeypatch.setattr(submission, "_run", fake_run)
    monkeypatch.setattr(submission, "_upload_manifest_files", lambda *args: None)
    result = submission.submit(tmp_path, decision_path, host="sunboquan-codex",
                               remote_dir="~/sbq/" + tmp_path.name, potcar_source="~/sbq/POTCAR",
                               potcar_sha256=manifest["potcar_sha256"], action=ACTION)
    assert result["job_id"] == "12345"
    command = commands[-1][-1]
    token = re.search(r"SCF_CHAIN_PERMIT=([A-Za-z0-9+/=]+)", command)[1]
    permit = json.loads(base64.b64decode(token))
    assert permit["manifest_sha256"] == sha256_file(tmp_path / "scf_chain.json")
    assert permit["gate_sha256"] == sha256_file(decision_path)
    with pytest.raises(FileExistsError, match="already has a submission record"):
        submission.submit(tmp_path, decision_path, host="sunboquan-codex",
                          remote_dir="~/sbq/" + tmp_path.name, potcar_source="~/sbq/POTCAR",
                          potcar_sha256=manifest["potcar_sha256"], action=ACTION)
