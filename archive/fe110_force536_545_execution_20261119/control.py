"""Prepare, dispatch once, and recover the two user-authorized BUCT2 arms."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

import yaml

from archive.fe110_force545_increment_20261119.prepare import BATCH, FROZEN, MODEL, OUT as INCREMENT
from archive.fe110_force545_package_20261119.build import OUT as PACKAGE545
from archive.fe110_joint_priority_20261117.analyze import BASE, ROOT, guard_hashes
from scripts.adsorption.force_finetune import verify_request
from scripts.adsorption.force_training_preflight import check_database_labels
from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive as save

OUT = BASE / "force536_545_comparison_20261119_v1"
STAGE = OUT / "payload"
REMOTE = "/home/sbq/sbq/force536_545_comparison_20261119_v1"
RUNTIME = "/home/sbq/sbq/compute_pool_20261117/deployed/runtime/python"
RUNTIME_SHA = "67d372f4548c1411fb41b282d6d093ed7677b1edef9dc80663c86a525d9b2b4f"
MODEL_SHA = "2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0"
HOST = "buct2-gpu"
OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
ARMS = {"control536": (FROZEN, 536), "increment545": (PACKAGE545, 545)}


def ssh(command, stdin=None, timeout=55):
    return subprocess.run(["ssh", "-T", *OPTIONS, "--", HOST, command], input=stdin, capture_output=True, timeout=timeout)


def scoped_python(code):
    return "python3 -B -c " + shlex.quote(code)


def record_run(name, result):
    for suffix, output in (("stdout", result.stdout), ("stderr", result.stderr)):
        with (OUT / f"{name}.{suffix}").open("xb") as stream:
            stream.write(output)
    if result.returncode:
        raise RuntimeError(f"{name} failed with code {result.returncode}: {result.stderr.decode('utf-8', 'replace')[-1600:]}")
    return result.stdout


def copy_checked(src, relative):
    name = STAGE / relative
    name.parent.mkdir(parents=True, exist_ok=True)
    with name.open("xb") as dest:
        dest.write(src.read_bytes())
    if sha(src) != sha(name):
        raise RuntimeError(f"Package file changed during staging: {relative}")


def make_arms(added, comparison):
    arms = {}
    for name, (pkg, count) in ARMS.items():
        check_database_labels(pkg, {"manifest_path": "training_manifest.json"})
        copy_checked(pkg / "train.db", f"{name}.db")
        copy_checked(pkg / "train_metadata.npz", f"{name}_metadata.npz")
        config_name = "increment545" if count == 545 else "control536"
        config = yaml.safe_load((INCREMENT / f"review_configs/{config_name}.yml").read_text(encoding="utf-8"))
        source_files = {"train": name, "val": "development"}
        for split, file in source_files.items():
            config["dataset"][split].update(src=f"{REMOTE}/payload/{file}.db", metadata_path=f"{REMOTE}/payload/{file}_metadata.npz")
        with (STAGE / f"{name}.yml").open("x", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(config, stream, sort_keys=False)
        arms[name] = {
            "manifest_sha256": sha(pkg / "training_manifest.json"),
            "limits": comparison["arms"][config_name]["limits"],
            "new_ids": added if count == 545 else [],
        }
    return arms


def prepare(user_request):
    guard = load(BATCH / "final_submission_list.json")["frozen_hashes"]
    if guard_hashes() != guard or sha(MODEL) != MODEL_SHA:
        raise ValueError("Protected package or frozen model identity changed")
    request = PACKAGE545 / "training_request.review.json"
    if verify_request(request)["training_authorized"] is not False:
        raise ValueError("The immutable 545 review should remain unauthorized")
    proof = load(PACKAGE545 / "two_epoch_replay.json")
    added = sorted(proof["native_new_samples_first_draw_step_by_epoch_1based"]["1"])
    if len(added) != 9 or set(added) != set(proof["native_new_samples_first_draw_step_by_epoch_1based"]["2"]):
        raise ValueError("The nine-frame sampling scope changed")
    files = ("development.db", "development_metadata.npz")
    if any(sha(PACKAGE545 / name) != sha(FROZEN / name) for name in files):
        raise ValueError("The two arms do not have byte-identical development inputs")
    OUT.mkdir()
    STAGE.mkdir()
    arms = make_arms(added, load(INCREMENT / "comparison_preflight.json"))
    for name in files:
        copy_checked(FROZEN / name, name)
    for name in ("worker.py", "job.sh"):
        copy_checked(Path(__file__).with_name(name), name)
    copy_checked(ROOT / "archive/fe110_training536_execution_20261113/entry.py", "allocation_owner.py")
    runtime_files = (
        "scripts/__init__.py",
        "scripts/artifact_io.py",
        "scripts/adsorption/__init__.py",
        "scripts/adsorption/force_finetune.py",
        "scripts/adsorption/force_training_preflight.py",
        "scripts/adsorption/force_role_data.py",
        "scripts/adsorption/force_role_runtime.py",
        "scripts/adsorption/role_force_trainer.py",
        "scripts/adsorption/direct_training_arm.py",
        "scripts/adsorption/direct_force_training.py",
        "scripts/adsorption/direct_gpu_batch.py",
    )
    for relative in runtime_files:
        copy_checked(ROOT / relative, relative)
    save(
        STAGE / "user_authorization.json",
        {
            "user_authorized": True,
            "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
            "backend": "buct2_gpu",
            "user_request": user_request,
            "arms": {name: count for name, (_, count) in ARMS.items()},
            "no_new_dft": True,
            "no_requeue_or_retries": True,
        },
    )
    save(
        STAGE / "contract.json",
        {
            "checkpoint_sha256": MODEL_SHA,
            "runtime_sha256": RUNTIME_SHA,
            "arms": arms,
            "files": {p.relative_to(STAGE).as_posix(): sha(p) for p in sorted(STAGE.rglob("*")) if p.is_file()},
            "scheduler_seconds": 1740,
            "killwait_seconds": 30,
            "per_arm_user_budget_seconds": 1800,
            "frozen_protected_input_hashes": guard,
        },
    )
    if guard_hashes() != guard:
        raise ValueError("Protected source bytes changed while preparing")
    print("Local two-arm payload and exact user authorization are ready.", flush=True)


def stage():
    root, contract = repr(REMOTE), STAGE / "contract.json"
    expected = sha(contract)
    files = {**load(contract)["files"], "contract.json": expected}
    code = f"""
import hashlib,pathlib,socket,sys,tarfile
root=pathlib.Path({root})
assert root.resolve()==root and socket.gethostname()=="pc-G7466-M6"
assert root.is_dir() and (root/"frozen536.pt").is_file()
payload=root/"payload"; payload.mkdir()
expected={files!r}
seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as tar:
 for entry in tar:
  target=(payload/entry.name).resolve()
  assert entry.isfile() and target.is_relative_to(payload) and entry.name in expected and entry.name not in seen
  data=tar.extractfile(entry).read()
  assert hashlib.sha256(data).hexdigest()==expected[entry.name]
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open("xb") as stream: stream.write(data)
  seen.add(entry.name)
assert seen==set(expected)
print("All payload bytes verified.")
"""
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz", compresslevel=3) as archive:
        for name in files:
            archive.add(STAGE / name, arcname=name, recursive=False)
    syntax = f"bash -n {REMOTE}/payload/job.sh"
    result = ssh(scoped_python(code) + " && " + syntax, content.getvalue(), timeout=85)
    print(record_run("stage", result).decode(), end="")


def cpu():
    expected = sha(STAGE / "contract.json")
    root = f"{REMOTE}/cpucheck"
    command = (
        f"mkdir {root} && cd {root} && "
        f"env CUDA_VISIBLE_DEVICES=-1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 "
        f"TMPDIR={root} XDG_CACHE_HOME={root}/cache TORCH_HOME={root}/torch HF_HOME={root}/hf "
        f"MPLCONFIGDIR={root}/mpl TORCH_EXTENSIONS_DIR={root}/extensions HF_HUB_OFFLINE=1 WANDB_MODE=disabled "
        f"timeout --kill-after=5s 85s {RUNTIME} -B {REMOTE}/payload/worker.py preflight --contract-sha256 {expected}"
    )
    print(record_run("cpu", ssh(command, timeout=100)).decode(), end="")
    pull("cpu_preflight.json", OUT / "cpu_preflight.json")
    proof = load(OUT / "cpu_preflight.json")
    assert proof["contract_sha256"] == expected and not proof["cuda_initialized"]


def submit(arm):
    expected = sha(STAGE / "contract.json")
    proof = load(OUT / "cpu_preflight.json")
    assert proof["contract_sha256"] == expected
    if arm == "increment545":
        control = load(OUT / "control536_report.json")
        assert control["producer_exit_code"] == 0 and control["native_iterations"] == 1072
    save(OUT / f"{arm}_submission_reservation.json", {"arm": arm, "contract_sha256": expected})
    code = f"""
from pathlib import Path
import hashlib,json,os,re,socket,subprocess
root=Path({REMOTE!r})
arm={arm!r}; digest={expected!r}
payload=root/"payload"
assert socket.gethostname()=="pc-G7466-M6" and root.resolve()==root
assert hashlib.sha256((payload/"contract.json").read_bytes()).hexdigest()==digest
assert json.loads((root/"cpu_preflight.json").read_text())["contract_sha256"]==digest
conf=subprocess.check_output(["scontrol","show","config"],text=True,timeout=8)
wait=re.search(r"(?m)^\\s*KillWait\\s*=\\s*(\\d+) sec",conf)
assert wait and int(wait[1])<=30
with (root/(arm+"_submit_attempt.json")).open("x") as f:
 json.dump({{"arm":arm,"contract_sha256":digest}},f)
args=["sbatch","--parsable","--job-name=force-"+arm,"--chdir="+str(root),
      "--output="+str(root/(arm+"-slurm-%j.log")),"--error="+str(root/(arm+"-slurm-%j.log")),
      str(payload/"job.sh"),arm,digest]
p=subprocess.run(args,capture_output=True,text=True,timeout=12)
job=p.stdout.strip().split(";")[0] if p.returncode==0 else None
if not job or not job.isdecimal():job=None
result={{"arm":arm,"job_id":job,"contract_sha256":digest,"sbatch_returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}}
with (root/(arm+"_submission.json")).open("x") as f:json.dump(result,f,indent=2)
print(json.dumps(result),flush=True)
if not job:raise SystemExit(1)
"""
    content = record_run(arm + "_sbatch", ssh(scoped_python(code), timeout=28))
    receipt = json.loads(content)
    if receipt["contract_sha256"] != expected or not receipt["job_id"]:
        raise ValueError("Ambiguous Slurm receipt; inspect without retry")
    pull(f"{arm}_submission.json", OUT / f"{arm}_submission.json")
    assert receipt == load(OUT / f"{arm}_submission.json")
    print(f"{arm} accepted as Slurm job {receipt['job_id']}", flush=True)


def pull(relative, local):
    if local.exists():
        raise FileExistsError(local)
    remote = f"{HOST}:{REMOTE}/{relative}"
    result = subprocess.run(["scp", "-q", *OPTIONS, "--", remote, str(local)], capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-1200:])


def collect(arm):
    available = load(OUT / f"{arm}_submission.json")
    job = available["job_id"]
    assert job.isdecimal()
    data = OUT / arm
    data.mkdir()
    base = f"{arm}_{job}"
    for name in (
        "job_exit_record.json",
        "allocation_preflight.json",
        "execution_device.json",
        "training_completed.json",
        "training_visits.jsonl",
        "candidate_binding.json",
        "native_two_backward_check.json",
    ):
        pull(f"{base}/{name}", data / name)
    pull(f"{arm}-slurm-{job}.log", data / "slurm.log")
    exit_record = load(data / "job_exit_record.json")
    recorded = load(data / "training_completed.json")
    binding = load(data / "candidate_binding.json")
    contract = sha(STAGE / "contract.json")
    if (
        exit_record["producer_exit_code"]
        or binding["contract_sha256"] != recorded["contract_sha256"]
        or recorded["contract_sha256"] != contract
    ):
        raise ValueError("Native producer completion or candidate binding failed")
    visits = [json.loads(line) for line in (data / "training_visits.jsonl").read_text(encoding="utf-8").splitlines()]
    size = ARMS[arm][1]
    proof = load(OUT / "cpu_preflight.json")
    expected = [sid for epoch in proof["arms"][arm]["epochs"] for sid in epoch]
    assert recorded["native_iterations"] == len(visits) == 2 * size
    assert [r["sample_id"] for r in visits] == expected
    assert [r["step"] for r in visits] == list(range(1, 2 * size + 1))
    assert sum(r["optimizer_update"] for r in visits) == recorded["optimizer_updates"]
    new_ids = set(load(STAGE / "contract.json")["arms"][arm]["new_ids"])
    covered = {
        str(epoch): sorted({r["sample_id"] for r in visits if r["epoch"] == epoch and r["optimizer_update"] and r["sample_id"] in new_ids})
        for epoch in (1, 2)
    }
    if any(set(ids) != new_ids for ids in covered.values()):
        raise ValueError("The GPU did not update on every new sample in both epochs")
    candidate_path = binding["path"]
    assert candidate_path.startswith(base + "/checkpoints/") and candidate_path.endswith("/best_checkpoint.pt")
    assert ".." not in candidate_path.split("/")
    pull(candidate_path, data / "candidate.pt")
    assert sha(data / "candidate.pt") == binding["sha256"]
    metrics = binding["metrics"]
    assert metrics["forces_role_vector_mae"]["numel"] == 78
    duration = exit_record["finished_unix"] - exit_record["started_unix"]
    assert 0 < duration <= 1800
    assert guard_hashes() == load(BATCH / "final_submission_list.json")["frozen_hashes"]
    report = {
        "arm": arm,
        "job_id": job,
        "producer_exit_code": 0,
        "native_iterations": len(visits),
        "optimizer_updates": recorded["optimizer_updates"],
        "new_samples_with_update_by_epoch": covered,
        "memory_and_device": load(data / "allocation_preflight.json")["gpu"],
        "producer_wall_seconds": duration,
        "candidate_sha256": binding["sha256"],
        "development_metrics": metrics,
        "dev_input_sha256": sha(STAGE / "development.db"),
    }
    save(OUT / f"{arm}_report.json", report)
    print(json.dumps({k: report[k] for k in ("arm", "job_id", "native_iterations", "optimizer_updates", "producer_wall_seconds")}))
    print("Dev force vector MAE", metrics["forces_role_vector_mae"]["metric"], "new frame counts", {k: len(v) for k, v in covered.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "stage", "cpu", "submit", "collect"))
    parser.add_argument("--arm", choices=tuple(ARMS))
    args = parser.parse_args()
    if args.phase == "prepare":
        request = sys.stdin.read().strip()
        if not request:
            raise ValueError("Exact explicit execution request required")
        prepare(request)
    elif args.phase in ("submit", "collect"):
        if args.arm is None:
            parser.error("--arm required for this phase")
        {"submit": submit, "collect": collect}[args.phase](args.arm)
    else:
        {"stage": stage, "cpu": cpu}[args.phase]()
