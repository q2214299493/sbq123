"""Stage and verify one matched relaxation comparison using frozen candidates."""

from __future__ import annotations

import argparse
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

import numpy as np
import yaml
from ase.io import read

from archive.fe110_adsorption_validation_20261018.runtime import load_atoms
from archive.fe110_c2_c3_pathgap_20261119.batch import RUN, load, save, sha
from archive.fe110_force580_execution_20261120 import run as training
from archive.fe110_joint_priority_20261117.analyze import ROOT, SLAB
from archive.fe110_pair2_20261027.review import audit_frames, post_relaxation_geometry, surface_metrics
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries

OUT = RUN.parent / "force545_580_relax_20261120_v1"
REMOTE = f"/home/sbq/sbq/{OUT.name}"
CANONICAL = f"/home/ubuntu/hdd/sbq/sbq/{OUT.name}"
PAYLOAD = OUT / "payload"
LIMITS = {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.20}
RULES = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
NATIVE = "/home/sbq/sbq/aqcat25/vendor/fairchem/core/common/relaxation/ase_utils.py"


def local_models(comparison):
    runs = training.BASELINE / "increment545", training.OUT / "increment580"
    models = dict(zip(("545", "580"), (path / "candidate.pt" for path in runs), strict=True))
    assert {name: sha(path) for name, path in models.items()} == {
        name: item["candidate_sha256"] for name, item in comparison["arms"].items()
    }
    return models


def stage_file(source, relative):
    path = PAYLOAD / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(source.read_bytes())
    assert sha(source) == sha(path)
    return sha(path)


def capture(name, result):
    for suffix, data in (("stdout", result.stdout), ("stderr", result.stderr)):
        with (OUT / (name + "." + suffix)).open("xb") as stream:
            stream.write(data)
    if result.returncode:
        raise RuntimeError(f"{name}: {result.stderr.decode('utf-8', 'replace')[-1200:]}")
    return result.stdout


def prepare(user_request):
    comparison_path = training.OUT / "comparison_summary.json"
    comparison = load(comparison_path)
    models = local_models(comparison)
    lock_path = RUN / "locked_optimization_starts.json"
    locked = load(lock_path)
    assert locked["models"]["increment545"]["sha256"] == sha(models["545"])
    assert locked["fixed_Fe_count"] == 18
    starts = {"11_B": ("common_start_11B", "C2H3"), "05_cfg2": ("common_start_complete_C3_05_cfg2", "C3H2O")}
    for key, composition in starts.values():
        source = Path(locked[key]["path"])
        assert sha(source) == locked[key]["sha256"] and load_atoms(source)[45:].get_chemical_formula() == composition
    remote_binding = load(training.OUT / "increment580/candidate_binding.json")
    path580 = remote_binding["path"]
    assert (
        path580.startswith("increment580_18125/checkpoints/") and path580.endswith("/best_checkpoint.pt") and ".." not in path580.split("/")
    )
    model580 = training.REMOTE + "/" + path580
    OUT.mkdir()
    PAYLOAD.mkdir()
    provenance = capture(
        "host_preflight",
        training.ssh(
            f'test "$(hostname)" = MZ73 && test "$(realpath -e /home/sbq/sbq)" = /home/ubuntu/hdd/sbq/sbq && '
            f"test ! -e {REMOTE} && test ! -L {REMOTE} && sha256sum {training.RUNTIME} {NATIVE} {shlex.quote(model580)}",
            timeout=25,
        ),
    ).decode("utf-8")
    python, native, remote_model = (line.split()[0] for line in provenance.splitlines())
    assert python == training.RUNTIME_SHA and remote_model == sha(models["580"])
    structures = {}
    for name, (key, composition) in starts.items():
        source = locked[key]
        relative = f"structures/{name}.vasp"
        assert stage_file(Path(source["path"]), relative) == source["sha256"]
        structures[name] = {"path": relative, "composition": composition, "source_sha256": source["sha256"]}
    for filename in ("worker.py", "job.sh"):
        stage_file(Path(__file__).with_name(filename), filename)
    for filename in ("runtime.py", "validation_helpers.py"):
        stage_file(ROOT / "archive/fe110_adsorption_validation_20261018" / filename, filename)
    files = {p.relative_to(PAYLOAD).as_posix(): sha(p) for p in PAYLOAD.rglob("*") if p.is_file()}
    binding = {
        "action": "PAIRWISE_AQCAT25_RELAXATION_ONLY",
        "user_request": user_request,
        "host": "MZ73",
        "canonical_root": CANONICAL,
        "start_lock_sha256": sha(lock_path),
        "prior_comparison_sha256": sha(comparison_path),
        "geometry_rules_sha256": sha(RULES),
        "starts": structures,
        "models": {"545": "model545.pt", "580": "model580.pt"},
        "existing_580_remote_path": model580,
        "files": {**files, **{f"model{name}.pt": sha(path) for name, path in models.items()}},
        "native_calc_sha256": native,
        "python_sha256": python,
        "limit": LIMITS,
        "cpu_cores": 8,
        "scheduler_minutes": 9,
        "training": False,
        "new_DFT": False,
        "model_promotion": False,
        "automatic_retries": False,
    }
    save(PAYLOAD / "request.json", binding)
    print("Frozen start and model hashes verified for all four arms.", flush=True)


def stage():
    request = PAYLOAD / "request.json"
    doc = load(request)
    models = local_models(load(training.OUT / "comparison_summary.json"))
    package = BytesIO()
    with tarfile.open(fileobj=package, mode="w:gz") as tar:
        for p in sorted(PAYLOAD.rglob("*")):
            if p.is_file():
                tar.add(p, arcname=p.relative_to(PAYLOAD).as_posix(), recursive=False)
    capture(
        "stage",
        training.ssh(
            f'test "$(hostname)" = MZ73 && mkdir {REMOTE} && tar -xzf - --keep-old-files -C {REMOTE} && '
            f"bash -n {REMOTE}/job.sh && cp --reflink=auto {shlex.quote(doc['existing_580_remote_path'])} {REMOTE}/model580.pt",
            package.getvalue(),
            timeout=55,
        ),
    )
    opts, host = training.endpoint("-P")
    capture(
        "upload545",
        subprocess.run(
            ["scp", "-q", *opts, "--", str(models["545"]), f"{host}:{REMOTE}/model545.pt"],
            capture_output=True,
            timeout=180,
        ),
    )
    wanted = {**doc["files"], "request.json": sha(request)}
    recorded = capture("remote_hashes", training.ssh("cd " + REMOTE + " && sha256sum -- " + shlex.join(sorted(wanted)), timeout=35))
    assert {name: digest for digest, name in (line.split() for line in recorded.decode().splitlines())} == wanted
    print("Both staged model checkpoints and all remote inputs verified.", flush=True)


def submit():
    request = PAYLOAD / "request.json"
    digest = sha(request)
    assert (OUT / "remote_hashes.stdout").is_file()
    save(OUT / "submission_reservation.json", {"request_sha256": digest, "no_retry": True})
    code = rf"""
import hashlib, json, re, socket, subprocess
from pathlib import Path
root=Path({REMOTE!r})
digest={digest!r}
assert socket.gethostname()=="MZ73" and root.resolve()==Path({CANONICAL!r})
assert hashlib.sha256((root/"request.json").read_bytes()).hexdigest()==digest
config=subprocess.check_output(["scontrol","show","config"],text=True,timeout=10)
wait=re.search(r"(?m)^\s*KillWait\s*=\s*(\d+) sec",config)
assert wait and int(wait[1])<=30
with (root/"submit_attempt.json").open("x") as f:
    json.dump({{"request_sha256":digest}},f)
p=subprocess.run(["sbatch","--parsable","--chdir="+str(root),"--output="+str(root/"slurm-%j.log"),
                  str(root/"job.sh"),digest],capture_output=True,text=True,timeout=15)
job=p.stdout.strip().split(";")[0]
assert p.returncode==0 and job.isdecimal(), p.stderr
with (root/"submission.json").open("x") as f:
    json.dump({{"job_id":job,"request_sha256":digest}},f)
print(job)
"""
    job = capture("submit", training.ssh(training.prior.scoped_python(code), timeout=32)).decode().strip()
    assert job.isdecimal()
    save(OUT / "submission.json", {"job_id": job, "request_sha256": digest})
    print("Matched CPU optimization submitted as Slurm job", job, flush=True)


def receive():
    sub = load(OUT / "submission.json")
    job = sub["job_id"]
    assert job.isdecimal()
    name = f"job_{job}"
    target = OUT / "returned"
    target.mkdir()
    header = capture("remote_result", training.ssh(f"cat {REMOTE}/{name}/result.json", timeout=15))
    verified = json.loads(header)
    paths = set(verified["produced_files"])
    assert all(Path(p).name in {"POSCAR", "case_record.json", "optimization.traj", "optimizer.log"} for p in paths)
    assert len(paths) == 16 and all(".." not in p.split("/") and not p.startswith("/") for p in paths)
    names = paths | {"exit.json", "result.json"}
    raw = training.ssh(f"cd {REMOTE}/{name} && tar -czf - -- " + shlex.join(sorted(names)), timeout=42)
    if raw.returncode or len(raw.stdout) > 16 * 1024 * 1024:
        raise ValueError("Missing or invalid optimization return archive")
    with tarfile.open(fileobj=BytesIO(raw.stdout), mode="r:gz") as tar:
        copied = set()
        for item in tar:
            assert item.isfile() and item.name in names - copied and item.size < 8 * 1024 * 1024
            path = target / item.name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                f.write(tar.extractfile(item).read())
            copied.add(item.name)
        assert copied == names
    final = load(target / "result.json")
    assert (target / "result.json").read_bytes() == header
    assert final["request_sha256"] == sub["request_sha256"] == sha(PAYLOAD / "request.json")
    assert load(target / "exit.json") == {"job_id": job, "exit_code": 0, "request_sha256": sub["request_sha256"]}
    assert final["job_id"] == job and final["device"] == "CPU FP32" and final["cuda_initialized"] is False
    for path, checksum in verified["produced_files"].items():
        assert sha(target / path) == checksum


def relative_geometry(reference, pose, slab, operations):
    details = surface_metrics(reference, pose, slab, operations)
    details["same_graph_as_reference"] = details.pop("same_graph_as_DFT")
    return details


def review():
    doc = load(PAYLOAD / "request.json")
    returned = OUT / "returned"
    record = load(returned / "result.json")
    assert doc["geometry_rules_sha256"] == sha(RULES)
    assert doc["start_lock_sha256"] == sha(RUN / "locked_optimization_starts.json")
    assert doc["prior_comparison_sha256"] == sha(training.OUT / "comparison_summary.json")
    local_models(load(training.OUT / "comparison_summary.json"))
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    pairs = {}
    for name, item in doc["starts"].items():
        original = PAYLOAD / item["path"]
        assert sha(original) == item["source_sha256"]
        seed = read_poscar(original)
        symbols = load_atoms(original).get_chemical_symbols()
        poses, arms = {}, {}
        for model in ("545", "580"):
            folder = returned / model / name / "seed"
            r = load(folder / "case_record.json")
            assert r in record["results"][model] and r["source_structure_sha256"] == item["source_sha256"]
            assert r["error"] is None and r["max_steps"] == 80
            pose = read_poscar(folder / "POSCAR")
            frames = read(folder / "optimization.traj", index=":")
            assert all(atoms.get_chemical_symbols() == symbols for atoms in frames)
            a = audit_frames(seed, frames, pose)
            assert len(frames) == r["optimizer_steps"] + 1 and a["maximum_adjacent_atom_displacement_A"] <= 0.20 + 1e-10
            hist = a["ML_fmax_history_eV_A"]
            # ASE reloads the originally FP32 force arrays in double precision.
            assert np.isclose(hist[-1], r["ML_movable_fmax_eV_A"], atol=1e-8, rtol=1e-7)
            assert r["converged"] == (hist[-1] <= LIMITS["fmax_eV_per_A"])
            geom = post_relaxation_geometry(seed, pose, a, rules)
            contacts = relative_geometry(seed, pose, slab, operations)
            poses[model] = pose
            arms[model] = {
                "run": r,
                "trajectory": a,
                "geometry": geom,
                "C_O_and_Fe_contacts": contacts,
                "first_fmax_eV_A": hist[0],
                "final_fmax_eV_A": hist[-1],
            }
        pairs[name] = {
            "composition": item["composition"],
            "arms": arms,
            "final_pose_comparison": relative_geometry(poses["545"], poses["580"], slab, operations),
        }
    save(
        OUT / "comparison_summary.json",
        {
            "status": "MATCHED_ML_ONLY_OPTIMIZATION_COMPLETE",
            "job_id": record["job_id"],
            "settings": deepcopy(doc["limit"]),
            "device": record["device"],
            "elapsed_seconds": record["elapsed_seconds"],
            "pairs": pairs,
            "new_DFT": False,
            "training": False,
            "promoted": False,
            "scientific_acceptance": False,
        },
    )
    for name, pair in pairs.items():
        for model, r in pair["arms"].items():
            print(
                name,
                model,
                r["run"]["optimizer_steps"],
                r["run"]["converged"],
                r["final_fmax_eV_A"],
                r["geometry"]["fragment_formulas_from_connectivity"],
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "stage", "submit", "receive", "review"))
    a = parser.parse_args()
    if a.phase == "prepare":
        user_request = sys.stdin.read().strip()
        if not user_request:
            parser.error("an exact user request is required")
        prepare(user_request)
    else:
        globals()[a.phase]()
