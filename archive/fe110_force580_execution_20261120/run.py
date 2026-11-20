"""Dispatch one approved 580-frame trial using the validated native worker."""

from __future__ import annotations

import argparse
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile

import yaml

from archive.fe110_force536_545_execution_20261119 import control as prior
from archive.fe110_force580_package_20261120.build import OUT as PACKAGE, inventory_entries
from scripts.adsorption.force_finetune import verify_request
from scripts.adsorption.force_training_preflight import check_budget
from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive as save

BASELINE = prior.OUT
OUT = prior.BASE / "force580_smoke_20261120_v1"
STAGE = OUT / "payload"
NAME = "increment580"
COUNT = 580
BACKEND = "aqcat_gpu"
NODE = "MZ73"
REMOTE = f"/home/sbq/sbq/{OUT.name}"
CANONICAL = f"/home/ubuntu/hdd/sbq/sbq/{OUT.name}"
RUNTIME = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"
RUNTIME_SHA = "df23391eb5ab66f005be15f792d55766d7ce96198e9e10df2aea72aec8c686ea"
FROZEN_REMOTE_PATH = "/home/sbq/sbq/fe110_force_training536_execution_20261113_v4/checkpoints/2026-11-14-00-04-16/best_checkpoint.pt"
ENV = f"env PYTHONPATH={REMOTE}/payload:/home/sbq/sbq/aqcat25_ts_pilot:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"


def endpoint(port_flag):
    cfg = yaml.safe_load((prior.ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"][BACKEND]
    host = cfg["ssh"]
    assert cfg["observed_hostname"] == NODE and cfg["remote_write_boundary"] == "/home/sbq/sbq"
    return [*prior.OPTIONS, "-o", "IdentitiesOnly=yes", "-i", host["identity_file"], port_flag, str(host["port"])], host[
        "user"
    ] + "@" + host["host"]


def ssh(command, stdin=None, timeout=55):
    opts, host = endpoint("-p")
    return subprocess.run(["ssh", "-T", *opts, "--", host, command], input=stdin, capture_output=True, timeout=timeout)


def pull(relative, local):
    if local.exists():
        raise FileExistsError(local)
    if relative.startswith("/") or ".." in relative.split("/"):
        raise ValueError("Remote source escapes the bound trial directory")
    opts, host = endpoint("-P")
    result = subprocess.run(["scp", "-q", *opts, "--", f"{host}:{REMOTE}/{relative}", str(local)], capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-950:])


def replace_checked(text, pairs):
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError(f"Expected a unique unchanged native-worker anchor: {old}")
        text = text.replace(old, new)
    return text


def render_native():
    plain = BASELINE / "payload"
    worker = replace_checked(
        (plain / "worker.py").read_text(encoding="utf-8"),
        [
            (str(prior.REMOTE), CANONICAL),
            (str(prior.RUNTIME), RUNTIME),
            ('COUNTS = {"control536": 536, "increment545": 545}', 'COUNTS = {"increment580": 580}'),
            ('socket.gethostname() != "pc-G7466-M6"', 'socket.gethostname() != "MZ73"'),
            ('approval.get("arms") != COUNTS', 'approval.get("arms") != COUNTS or approval.get("remote_root") != str(ROOT)'),
            ('approval.get("backend") != "buct2_gpu"', 'approval.get("backend") != "aqcat_gpu"'),
            (
                'reviews["control536"]["development_ids"] != reviews["increment545"]["development_ids"]',
                'reviews["increment580"]["development_ids"] != contract["expected_development_ids"]',
            ),
            ("The two development sets are not identical", "The development order differs from the 545 baseline"),
            ("both arms and their retained checkpoints", "the warm start and retained checkpoints"),
            (
                "CPU preflight passed both arms; all nine increment IDs appear once in each replay epoch.",
                "CPU preflight passed; all 35 increment IDs appear once in each replay epoch.",
            ),
        ],
    )
    job = replace_checked(
        (plain / "job.sh").read_text(encoding="utf-8"),
        [
            (str(prior.REMOTE), CANONICAL),
            (str(prior.RUNTIME), RUNTIME),
            ("#SBATCH --nodelist=pc-G7466-M6", "#SBATCH --nodelist=MZ73"),
            ('[[ "$arm" == control536 || "$arm" == increment545 ]]', '[[ "$arm" == increment580 ]]'),
            ('"$(hostname)" == pc-G7466-M6', '"$(hostname)" == MZ73'),
            (
                "export WANDB_MODE=disabled HF_HUB_OFFLINE=1",
                f"export WANDB_MODE=disabled HF_HUB_OFFLINE=1\n{ENV.removeprefix('env ').replace('PYTHONPATH=', 'export PYTHONPATH=')}",
            ),
        ],
    )
    for name, text in (("worker.py", worker), ("job.sh", job)):
        with (STAGE / name).open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    compile(worker, str(STAGE / "worker.py"), "exec")


def only_training_size_diff(old, config):
    old = deepcopy(old)
    for group in ("train", "val"):
        old["dataset"][group].update({k: config["dataset"][group][k] for k in ("src", "metadata_path")})
    old["optim"].update(eval_every=COUNT, checkpoint_every=COUNT)
    if old != config:
        raise ValueError("Execution would change more than the already reviewed training set size")


def training_guards():
    preflight = load(PACKAGE / "cpu_data_preflight.json")
    before = preflight["protected_guards"]
    current = prior.guard_hashes()
    # The current protocol and backend documents govern this new execution binding.
    # They can change independently of the frozen labels, model and data partitions.
    fresh_documents = {prior.ROOT / "docs/01_METHOD_PROTOCOL.md", prior.ROOT / "configs/execution_backends.yaml"}
    assert all(current[path] == digest for path, digest in before.items() if Path(path) not in fresh_documents)
    return current


def prepare(user_request):
    inventory_entries(PACKAGE)
    guard = training_guards()
    request_path = PACKAGE / "training_request.review.json"
    request = load(request_path)
    assert verify_request(request_path)["training_authorized"] is False
    assert request["split_counts"] == {"train": COUNT, "development": 78, "heldout": 53}
    model = request["base_checkpoint"]
    native = load(PACKAGE / "provenance/cpu580/native_cpu.stdout.json")
    assert sha(Path(model["path"])) == model["sha256"] == prior.MODEL_SHA == native["checkpoint_sha256"]
    baseline = load(BASELINE / "comparison_summary.json")
    b545 = baseline["arms"]["increment545"]
    assert baseline["initialization_sha256"] == model["sha256"]
    assert sha(BASELINE / "increment545/candidate.pt") == b545["candidate_sha256"]
    proof = load(PACKAGE / "two_epoch_replay.json")
    assert proof["training_database"]["sha256"] == sha(PACKAGE / "train.db")
    assert proof["training_metadata"]["sha256"] == sha(PACKAGE / "train_metadata.npz")
    ids, second = (set(r) for r in proof["visits_1based_by_epoch"]["native"])
    assert ids == second and len(ids) == 35
    assert all(sha(PACKAGE / name) == sha(BASELINE / "payload" / name) for name in ("development.db", "development_metadata.npz"))
    config = yaml.safe_load((PACKAGE / "config.yml").read_text(encoding="utf-8"))
    old = yaml.safe_load((BASELINE / "payload/increment545.yml").read_text(encoding="utf-8"))
    only_training_size_diff(old, config)
    for group, name in (("train", NAME), ("val", "development")):
        config["dataset"][group].update(src=f"{REMOTE}/payload/{name}.db", metadata_path=f"{REMOTE}/payload/{name}_metadata.npz")
    check_budget(request, config)
    OUT.mkdir()
    STAGE.mkdir()
    prior.STAGE = STAGE
    for source, target in (
        ("train.db", NAME + ".db"),
        ("train_metadata.npz", NAME + "_metadata.npz"),
        ("development.db", "development.db"),
        ("development_metadata.npz", "development_metadata.npz"),
    ):
        prior.copy_checked(PACKAGE / source, target)
    basis = BASELINE / "payload"
    for entry in (basis / "scripts").rglob("*.py"):
        prior.copy_checked(entry, entry.relative_to(basis).as_posix())
    prior.copy_checked(basis / "allocation_owner.py", "allocation_owner.py")
    for name in ("force_role_data.py", "force_role_runtime.py", "role_force_trainer.py"):
        assert sha(STAGE / "scripts/adsorption" / name) == sha(PACKAGE / "runtime/scripts/adsorption" / name)
    render_native()
    with (STAGE / (NAME + ".yml")).open("x", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    b_cpu = load(BASELINE / "cpu_preflight.json")
    save(
        STAGE / "user_authorization.json",
        {
            "user_authorized": True,
            "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
            "backend": BACKEND,
            "remote_root": CANONICAL,
            "user_request": user_request,
            "arms": {NAME: COUNT},
            "no_new_dft": True,
            "no_requeue_or_retries": True,
        },
    )
    save(
        STAGE / "contract.json",
        {
            "checkpoint_sha256": model["sha256"],
            "runtime_sha256": RUNTIME_SHA,
            "arms": {
                NAME: {
                    "manifest_sha256": sha(PACKAGE / "training_manifest.json"),
                    "limits": request["training_limits"],
                    "new_ids": sorted(ids),
                }
            },
            "expected_development_ids": b_cpu["arms"]["increment545"]["development_ids"],
            "baseline_model_source_sha256": b_cpu["model_source_sha256"],
            "baseline_development_db_sha256": sha(PACKAGE / "development.db"),
            "baseline_comparison_sha256": sha(BASELINE / "comparison_summary.json"),
            "baseline_candidate_sha256": b545["candidate_sha256"],
            "package_inventory_sha256": sha(PACKAGE / "package_inventory.json"),
            "files": {p.relative_to(STAGE).as_posix(): sha(p) for p in sorted(STAGE.rglob("*")) if p.is_file()},
            "frozen_protected_input_hashes": guard,
            "scheduler_seconds": 1740,
            "killwait_seconds": 30,
        },
    )
    assert training_guards() == guard
    print("One 580-frame payload bound. The existing 545 candidate is read only.", flush=True)


def stage():
    expected = sha(STAGE / "contract.json")
    files = {**load(STAGE / "contract.json")["files"], "contract.json": expected}
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w:gz", compresslevel=3) as a:
        for relative in files:
            assert sha(STAGE / relative) == files[relative]
            a.add(STAGE / relative, arcname=relative, recursive=False)
    commands = (
        f'test "$(hostname)" = {NODE} && test "$(realpath -e /home/sbq/sbq)" = /home/ubuntu/hdd/sbq/sbq && '
        f"mkdir {REMOTE} && mkdir {REMOTE}/payload && "
        f"tar -xzf - --keep-old-files -C {REMOTE}/payload && "
        f"cp --reflink=auto {FROZEN_REMOTE_PATH} {REMOTE}/frozen536.pt && "
        f"bash -n {REMOTE}/payload/job.sh && sha256sum {REMOTE}/payload/contract.json {REMOTE}/frozen536.pt {RUNTIME}"
    )
    result = ssh(commands, tar.getvalue(), timeout=85)
    output = record("stage", result).decode()
    assert [line.split()[0] for line in output.splitlines()] == [expected, prior.MODEL_SHA, RUNTIME_SHA]
    print("MZ73 staged contract and frozen checkpoint verified.", flush=True)


def record(name, result):
    prior.OUT = OUT
    return prior.record_run(name, result)


def cpu():
    expected = sha(STAGE / "contract.json")
    root = REMOTE + "/cpucheck"
    cmd = (
        f"mkdir {root} && cd {root} && {ENV} CUDA_VISIBLE_DEVICES=-1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 "
        f"TMPDIR={root} XDG_CACHE_HOME={root}/cache TORCH_HOME={root}/torch HF_HOME={root}/hf "
        f"MPLCONFIGDIR={root}/mpl TORCH_EXTENSIONS_DIR={root}/extensions HF_HUB_OFFLINE=1 WANDB_MODE=disabled "
        f"timeout --kill-after=5s 85s {RUNTIME} -B {REMOTE}/payload/worker.py preflight --contract-sha256 {expected}"
    )
    print(record("cpu", ssh(cmd, timeout=100)).decode(), end="")
    path = OUT / "cpu_preflight.json"
    pull("cpu_preflight.json", path)
    pre = load(path)
    contract = load(STAGE / "contract.json")
    assert pre["contract_sha256"] == expected and pre["cuda_initialized"] is False
    assert pre["model_source_sha256"] == contract["baseline_model_source_sha256"]
    assert pre["arms"][NAME]["development_ids"] == contract["expected_development_ids"]


def submit():
    contract_path = STAGE / "contract.json"
    expected = sha(contract_path)
    contract = load(contract_path)
    pre = OUT / "cpu_preflight.json"
    proof = load(pre)
    assert proof["contract_sha256"] == expected and proof["cuda_initialized"] is False
    assert proof["model_source_sha256"] == contract["baseline_model_source_sha256"]
    assert training_guards() == contract["frozen_protected_input_hashes"]
    save(OUT / f"{NAME}_submission_reservation.json", {"arm": NAME, "contract_sha256": expected, "auto_retry": False})
    script = rf"""
import hashlib, json, re, socket, subprocess
from pathlib import Path
root=Path({REMOTE!r})
arm={NAME!r}
digest={expected!r}
assert socket.gethostname()=={NODE!r} and root.resolve()==Path({CANONICAL!r})
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/"payload/contract.json")==digest and sha(root/"cpu_preflight.json")=={sha(pre)!r}
conf=subprocess.check_output(["scontrol","show","config"],text=True,timeout=8)
wait=re.search(r"(?m)^\s*KillWait\s*=\s*(\d+) sec",conf)
assert wait and int(wait[1])<=30
with (root/(arm+"_submit_attempt.json")).open("x") as f:
    json.dump({{"contract_sha256":digest,"arm":arm}}, f)
logs=str(root/(arm+"-slurm-%j.log"))
args=["sbatch","--parsable","--job-name=force-"+arm,"--chdir="+str(root),
      "--output="+logs,"--error="+logs,str(root/"payload/job.sh"),arm,digest]
p=subprocess.run(args,capture_output=True,text=True,timeout=12)
job=p.stdout.strip().split(";")[0] if p.returncode==0 else None
job=job if job and job.isdecimal() else None
result={{"arm":arm,"job_id":job,"contract_sha256":digest,"sbatch_returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}}
with (root/(arm+"_submission.json")).open("x") as f:
    json.dump(result,f,indent=2)
print(json.dumps(result),flush=True)
if not job: raise SystemExit(1)
"""
    result = ssh(prior.scoped_python(script), timeout=32)
    record(NAME + "_sbatch", result)
    target = OUT / f"{NAME}_submission.json"
    pull(target.name, target)
    receipt = load(target)
    assert receipt["contract_sha256"] == expected and receipt["job_id"].isdecimal()
    print("580 trial accepted as Slurm job", receipt["job_id"], flush=True)


def collect():
    submission = load(OUT / f"{NAME}_submission.json")
    job = submission["job_id"]
    assert job.isdecimal()
    remote = f"{NAME}_{job}"
    out = OUT / NAME
    out.mkdir()
    for name in (
        "job_exit_record.json",
        "allocation_preflight.json",
        "execution_device.json",
        "training_completed.json",
        "training_visits.jsonl",
        "candidate_binding.json",
        "native_two_backward_check.json",
    ):
        pull(f"{remote}/{name}", out / name)
    pull(f"{NAME}-slurm-{job}.log", out / "slurm.log")
    contract_path = STAGE / "contract.json"
    digest = sha(contract_path)
    contract = load(contract_path)
    exit_record, trace, binding = (load(out / f) for f in ("job_exit_record.json", "training_completed.json", "candidate_binding.json"))
    assert exit_record["producer_exit_code"] == 0
    assert all(a["contract_sha256"] == digest for a in (submission, exit_record, trace, binding))
    assert binding["job_id"] == job == exit_record["job_id"]
    visits = [json.loads(line) for line in (out / "training_visits.jsonl").read_text(encoding="utf-8").splitlines()]
    replay = load(OUT / "cpu_preflight.json")["arms"][NAME]["epochs"]
    assert [v["sample_id"] for v in visits] == replay[0] + replay[1]
    assert trace["native_iterations"] == len(visits) == 2 * COUNT and trace["epochs"] == 2
    assert [v["step"] for v in visits] == list(range(1, 2 * COUNT + 1))
    assert trace["optimizer_updates"] == sum(v["optimizer_update"] for v in visits)
    added = set(contract["arms"][NAME]["new_ids"])
    coverage = {
        str(epoch): sorted({v["sample_id"] for v in visits if v["epoch"] == epoch and v["optimizer_update"] and v["sample_id"] in added})
        for epoch in (1, 2)
    }
    selected = binding["path"]
    assert selected.startswith(remote + "/checkpoints/") and selected.endswith("/best_checkpoint.pt")
    pull(selected, out / "candidate.pt")
    assert sha(out / "candidate.pt") == binding["sha256"]
    duration = exit_record["finished_unix"] - exit_record["started_unix"]
    assert 0 < duration <= 1800
    assert training_guards() == contract["frozen_protected_input_hashes"]
    save(
        OUT / f"{NAME}_report.json",
        {
            "job_id": job,
            "producer_exit_code": 0,
            "native_iterations": len(visits),
            "epochs": trace["epochs"],
            "optimizer_updates": trace["optimizer_updates"],
            "new_samples_with_update_by_epoch": coverage,
            "complete_new_sample_update_coverage": all(set(v) == added for v in coverage.values()),
            "producer_wall_seconds": duration,
            "gpu": load(out / "allocation_preflight.json")["gpu"],
            "candidate_sha256": binding["sha256"],
            "development_metrics": binding["metrics"],
            "dev_input_sha256": sha(STAGE / "development.db"),
        },
    )
    print("Completed", len(visits), "native iterations; new-frame updates", {k: len(v) for k, v in coverage.items()})


def compare():
    earlier_path = BASELINE / "comparison_summary.json"
    base = load(earlier_path)
    now = load(OUT / f"{NAME}_report.json")
    contract = load(STAGE / "contract.json")
    assert sha(earlier_path) == contract["baseline_comparison_sha256"]
    old = base["arms"]["increment545"]
    assert sha(BASELINE / "increment545/candidate.pt") == old["candidate_sha256"] == contract["baseline_candidate_sha256"]
    assert now["dev_input_sha256"] == old["dev_input_sha256"] == contract["baseline_development_db_sha256"]
    assert sha(PACKAGE / "package_inventory.json") == contract["package_inventory_sha256"]
    assert training_guards() == contract["frozen_protected_input_hashes"]
    metrics = {}
    for name, first in old["development_metrics"].items():
        second = now["development_metrics"][name]
        assert first["numel"] == second["numel"] and math.isfinite(second["metric"])
        change = second["metric"] - first["metric"]
        metrics[name] = {"545": first["metric"], "580": second["metric"], "delta": change, "percent": 100 * change / first["metric"]}
    assert now["development_metrics"]["forces_role_vector_mae"]["numel"] == 78
    save(
        OUT / "comparison_summary.json",
        {
            "development_frames": 78,
            "same_development_db_sha256": now["dev_input_sha256"],
            "init_checkpoint_sha256": contract["checkpoint_sha256"],
            "arms": {"545": old, "580": now},
            "metrics": metrics,
            "two_epoch_step_difference": 70,
            "heldout_evaluated": False,
            "promoted": False,
            "new_dft": False,
            "training_comparison_scope": "Single-seed two-epoch pilot on checkpoint-selection development set",
        },
    )
    print(metrics["forces_role_vector_mae"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "stage", "cpu", "submit", "collect", "compare"))
    opts = parser.parse_args()
    if opts.phase == "prepare":
        request = sys.stdin.read().strip()
        if not request:
            parser.error("the exact user execution request is required")
        prepare(request)
    else:
        globals()[opts.phase]()
