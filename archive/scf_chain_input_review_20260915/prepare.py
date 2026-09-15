"""One-case input review, using canonical builders; no submission operation."""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.scf_chain_bundle import build_runtime, launcher
from scripts.neb_agent.scf_chain_evidence import collect, geometry_error, structure
from scripts.neb_agent.scf_repair_chain import INPUTS
from scripts.neb_agent.submission import preflight
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.scf_chain_gate import STAGES

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
SOURCE = BASE / "h_migration_int06_mid_fixed_density_20260914"
BASELINE = BASE / "h_migration_int06_mid_scf_normal_20260912/completed_20260912"
DEST = BASE / "h_migration_int06_mid_scf_chain_20260915"
REVIEW = ROOT / "docs/reviews/scf_chain_input_review_20260915"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def remote():
    REVIEW.mkdir(parents=True, exist_ok=True)
    target = REVIEW / "remote_preflight.json"
    if target.exists():
        raise FileExistsError("Existing runtime evidence; review it, do not overwrite")
    script = Path(__file__).with_name("remote_preflight.py").read_bytes()
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex",
               "bash -c 'source /home_gkx/env/intel/intel2016.sh >/dev/null 2>&1; /home_gkn/users/nsgkn_chengdj3/bin/python3 -'"]
    completed = subprocess.run(command, input=script, capture_output=True, timeout=90, check=True)
    # Preserve transport bytes before parsing; never recover JSON by cutting a
    # plausible fragment out of console output.
    with (REVIEW / "remote_preflight_clean.stdout").open("xb") as handle:
        handle.write(completed.stdout)
    evidence = json.loads(completed.stdout)
    write_json_exclusive(target, evidence)
    print(json.dumps({"remote_writes": False, "python": evidence["python"],
                      "scheduler": evidence["scheduler"], "target_exists": evidence["target_exists"]}))


def prepare():
    if DEST.exists():
        raise FileExistsError("Input package already exists; inspect before any retry")
    remote = load_json_object(REVIEW / "remote_preflight.json")
    assert not remote["target_exists"] and remote["parent_writable"]
    assert remote["libraries"]["exit_code"] == 0 and "not found" not in remote["libraries"]["stdout"]
    assert remote["executable_sha256"] == "bda029d99f505f136ddaeb13aa38d15ac2ae5d1369d7432c533f75c78416cbfa"
    auth = load_json_object(SOURCE / "user_execution_authorization.json")
    assert remote["potcar_sha256"] == auth["potcar"]["sha256"]
    hashes = load_json_object(SOURCE / "submission_preflight.json")["files"]
    for name in ("INCAR", "POSCAR", "KPOINTS"):
        assert sha256_file(SOURCE / name) == hashes[name] == remote["source_input_hashes"][name]
    assert sha256_file(SOURCE / "POTCAR.spec") == hashes["POTCAR.spec"]
    validation = load_json_object(BASELINE / "scf_validation.json")
    for source in validation["source_files"]:
        assert sha256_file(Path(source["path"])) == source["sha256"]
    assert sha256_file(BASELINE / "POSCAR") == hashes["POSCAR"]
    old_gate = load_json_object(SOURCE / "execution_gate_decision.json")
    geometry_binding = old_gate["EVIDENCE"]["source_bindings"]["geometry"]
    assert sha256_file(Path(geometry_binding["path"])) == geometry_binding["sha256"]
    assert old_gate["EVIDENCE"]["geometry"]["status"] == "PASS"
    geom = structure(BASELINE / "POSCAR")
    geometry_error(geom, structure(SOURCE / "POSCAR"), 1e-10)
    assert geom["symbols"] == ["Fe", "C", "O", "H"] and geom["counts"] == [45, 2, 1, 2]
    fixed = [i for i, flag in enumerate(geom["flags"]) if flag == ["F", "F", "F"]]
    assert fixed == list(range(18))
    baseline = collect(BASELINE, {"NCORE": 1., "NBANDS": 320., "ENCUT": 400., "ISTART": 0., "ICHARG": 2.},
                       geom, 2e-5, exit_code=0)
    assert baseline["electronic_pass"] and baseline["normal_end"] and not baseline["errors"] and baseline["runtime_matches"]
    assert all(x > 0 for x in baseline["state"]["moments"][:45])
    original = Incar.from_file(SOURCE / "INCAR")
    assert original["ISMEAR"] == 1 and original["SIGMA"] == .2 and original["ENCUT"] == 400
    assert original["MAGMOM"] == baseline["state"]["moments"]
    DEST.mkdir()
    for name in ("POSCAR", "KPOINTS", "POTCAR.spec"):
        shutil.copyfile(SOURCE / name, DEST / name)
    changes = {}
    for letter, (start, charge) in zip("ABC", ((0, 12), (0, 2), (1, 1))):
        incar = Incar({**original, "NCORE": 8, "NBANDS": 320, "ISTART": start, "ICHARG": charge})
        changes[letter] = {key: {"source": original.get(key), "candidate": incar[key]}
                           for key in incar if original.get(key) != incar[key]}
        incar.write_file(DEST / (letter + ".INCAR"))
    shutil.copyfile(DEST / "A.INCAR", DEST / "INCAR")
    baseline_payload = {"state": baseline["state"], "geometry": geom,
                        "source_files": {str(p.relative_to(ROOT)): sha256_file(p) for p in
                                         [BASELINE / n for n in ("INCAR", "POSCAR", "OUTCAR", "OSZICAR", "vasp.out", "scf_validation.json")]},
                        "review_status": "REVIEWED"}
    write_json_exclusive(DEST / "baseline.json", baseline_payload)
    def limits(energy, force, local, total):
        return {key: {"warning": values[0], "stop": values[1]} for key, values in zip(
            ("energy_eV", "force_vector_eV_A", "local_moment_muB", "total_moment_muB"),
            (energy, force, local, total))}
    policy = {"geometry_A": 2e-5,
              "baseline": limits((.01, .05), (.01, .05), (.1, .3), (.5, 2.)),
              "restart": limits((.001, .01), (.005, .02), (.02, .1), (.1, .5))}
    manifest = {"schema_version": 1, "stages": list(STAGES), "inputs": {name: sha256_file(DEST/name) for name in INPUTS},
                "potcar_sha256": remote["potcar_sha256"], "policy": policy,
                "runtime": {**{k: remote[k] for k in ("executable", "executable_sha256", "mpirun", "mpirun_sha256")},
                            "ranks": 80, "stage_timeout_seconds": 10800}}
    write_json_exclusive(DEST / "scf_chain.json", manifest)
    (DEST / "script.lsf").write_text(launcher(80), encoding="utf-8", newline="\n")
    build_runtime(DEST / "scf_chain_runtime.pyz")
    custody = {}
    for letter in "ABC":
        command = [sys.executable, str(CUSTODIAN), "--mode", "validate", "--workdir", str(DEST),
                   "--incar", str(DEST / (letter + ".INCAR")), "--poscar", str(DEST / "POSCAR"),
                   "--calculation-type", "adsorption_static", "--surface-family", "metal_fe",
                   "--material", "Fe110", "--read-only"]
        cp = subprocess.run(command, capture_output=True, text=True, timeout=45, check=True)
        custody[letter] = json.loads(cp.stdout)
        assert not custody[letter]["blockers"]
    write_json_exclusive(REVIEW / "incar_validation.json", custody)
    report = preflight(DEST, "scf_repair_chain")
    write_json_exclusive(REVIEW / "input_review.json", {
        "status": "PREPARED_FOR_USER_REVIEW", "execution_authorized": False,
        "source_bindings": {"geometry": geometry_binding, "input_files": hashes},
        "baseline": {"job_id": "9752745", "state": baseline["state"], "fixed_indices": fixed},
        "incar_changes": changes, "candidate_policy": policy,
        "manifest_sha256": sha256_file(DEST / "scf_chain.json"), "bundle_sha256": report["bundle_sha256"],
        "preflight_passed": report["passed"], "preflight_errors": report["errors"],
        "new_external_structure": False, "retrieval_scope": "VERIFIED_LOCAL_EXACT_GEOMETRY_REUSE",
        "gpu_executed": False, "vasp_executed": False,
    })
    gate = decide_execution(old_gate["EVIDENCE"]["geometry"], {"status": "NO_OUTPUT", "images": []},
                            policy, climb=False, path_reviewed=True, preflight=report)
    write_json_exclusive(DEST / "execution_gate_review_only.json", gate)
    assert not gate["ALLOWED_ACTIONS"]
    print(json.dumps({"prepared": str(DEST), "preflight_passed": report["passed"], "errors": report["errors"],
                      "gate": gate["DECISION"], "allowed": gate["ALLOWED_ACTIONS"],
                      "manifest_sha256": sha256_file(DEST / "scf_chain.json")}))


def verify():
    target = REVIEW / "runtime_syntax_check.json"
    if target.exists():
        raise FileExistsError("Runtime syntax evidence already exists")
    program = (
        "import sys,io,zipfile,json,hashlib; data=sys.stdin.buffer.read(); "
        "z=zipfile.ZipFile(io.BytesIO(data)); "
        "[compile(z.read(n),n,'exec') for n in z.namelist() if n.endswith('.py')]; "
        "print(json.dumps({'runtime_sha256':hashlib.sha256(data).hexdigest(),"
        "'compiled_members':len(z.namelist()),'executed':False,'writes':False}))"
    )
    command = ["ssh", "-o", "BatchMode=yes", "sunboquan-codex",
               shlex.join(["/home_gkn/users/nsgkn_chengdj3/bin/python3", "-c", program])]
    completed = subprocess.run(command, input=(DEST / "scf_chain_runtime.pyz").read_bytes(),
                               capture_output=True, timeout=45, check=True)
    result = json.loads(completed.stdout)
    assert result["runtime_sha256"] == sha256_file(DEST / "scf_chain_runtime.pyz")
    shell = subprocess.run(["ssh", "-o", "BatchMode=yes", "sunboquan-codex", "bash -n"],
                           input=(DEST / "script.lsf").read_bytes(), capture_output=True, timeout=30, check=True)
    result.update(shell_syntax_exit_code=shell.returncode, script_sha256=sha256_file(DEST / "script.lsf"))
    write_json_exclusive(target, result)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("remote", "prepare", "verify"))
    {"remote": remote, "prepare": prepare, "verify": verify}[parser.parse_args().stage]()
