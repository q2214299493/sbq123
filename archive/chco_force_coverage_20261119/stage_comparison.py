"""Prepare or submit the exact authorized two-arm CHCO force comparison."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path

import yaml


NAME = "chco_force_coverage_20261119_lr_matched"
SOURCE = Path(__file__).resolve().parent
PROJECT = SOURCE.parents[1]
BASE = "/home/sbq/sbq/compute_pool_20261117/deployed/models/aqcat25_ft512_development.pt"
BASE_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
USER = ("继续，就按你说的做对照：用第9–12点联合微调，第7、8点留作验证，"
        "势函数、学习率和更新次数保持一致。先看最大力误差有没有明显下降，"
        "再决定要不要提交第14个DFT单点，收敛要求仍是0.03 eV/Å。")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def backend():
    config = PROJECT / "configs/execution_backends.yaml"
    b = yaml.safe_load(config.read_text(encoding="utf-8"))["backends"]["buct3_gpu"]
    limits = b["scoped_force_training"][NAME]
    assert b["role"] == "candidate_acceleration_only" and b["ssh"]["identities_only"] is True
    assert b["remote_write_boundary"] == "/home/sbq/sbq"
    assert limits == {"scope": "one_single_vs_joint_AQCat25_force_fit_comparison", "partition": "compute",
                      "gpus": 1, "cpus_per_task": 4, "memory": "15G", "time_limit": "00:22:00",
                      "updates_per_arm": 100, "automatic_retries": 0}
    return config, b


def prepare(case):
    config, b = backend()
    dest = case / NAME
    state = case / "paper_state.v3.json"
    state_bytes = state.read_bytes()
    data = json.loads(state_bytes)
    failed = case / "chco_force_coverage_20261119/job_566_return"
    terminal = json.loads((failed / "native_and_return_packet.json").read_bytes())
    assert terminal["status"] == "FAILED" and "learning-rate traces differ" in terminal["stderr_tail"]
    assert not terminal["files"]["comparison_result.json"]
    expected_jobs = ["14462", "14473", "14488", "14499", "14518", "15970"]
    assert data["completed_label_count"] == 12 and data["reserved_dft_slots"] == 13
    assert data["protocol"]["movable_atom_indices_zero_based"] == list(range(18, 49))
    assert data["protocol"]["initial_checkpoint"]["sha256"] == BASE_SHA
    sets = {}
    src_positions = {}
    for i, job in enumerate(expected_jobs, 7):
        record = data["evaluations"][i - 1]
        accepted = record["accepted_label"]
        raw = base64.b64decode(accepted["raw_label_base64"], validate=True)
        assert digest(raw) == record["label_sha256"] == accepted["artifact_sha256"]
        label = json.loads(raw)
        assert record["execution"]["job_id"] == job and label == accepted["label"]
        assert label["round_index"] == i - 1 and label["electronically_converged"] is True
        assert label["normal_completion"] and label["eligible_for_force_only_training"]
        assert label["compatibility_sha256"] == data["protocol"]["compatibility_sha256"]
        assert label["fixed_atom_indices_zero_based"] == list(range(18))
        ref = label["structure"]
        raw_pos = Path(ref["path"]).read_bytes()
        assert digest(raw_pos) == ref["sha256"] == record["request"]["candidate_structure_sha256"]
        assert label["forces_eV_per_A"] == accepted["raw_forces_eV_per_A"]
        src_positions[i] = raw_pos
        sets[i] = {"point": i, "job_id": job, "poscar_sha256": ref["sha256"],
                   "geometry_sha256": label["geometry_sha256"], "label_sha256": digest(raw),
                   "forces_eV_per_A": label["forces_eV_per_A"],
                   "energy_eV": label["dft_toten_eV_force_label_only"]}
    assert len({x["geometry_sha256"] for x in sets.values()}) == 6
    remote = f"{b['remote_write_boundary']}/{json.loads((case / 'continuation_r012_submission_record.json').read_bytes())['remote_dir'].split('/')[-2]}/{NAME}"
    # This experiment uses its own directory and never edits the sequential state.
    dest.mkdir(exist_ok=False)
    runtime = b["ba_sella_runtime"]
    vendored = SOURCE.parent / "chco_paper_aqcat25_20261112" / "train_latest_label.py"
    template = case / "training_r011_force003" / "force_only_config.yml"
    old = json.loads((case / "training_r011_force003" / "manifest.json").read_bytes())
    for src in (vendored, template):
        assert sha(src) == old["files"][src.name]
    for src in (vendored, template, SOURCE / "run_comparison.py"):
        shutil.copyfile(src, dest / src.name)
    for i, raw in src_positions.items():
        (dest / f"point_{i:02d}.vasp").write_bytes(raw)
    for split, points in (("train", range(9, 13)), ("validation", range(7, 9))):
        write_json(dest / f"{split}_points.json", [sets[i] for i in points])
    (dest / "user_request.txt").write_bytes((USER + "\n").encode("utf-8"))
    write_json(dest / "request.json", {"kind": "chco_aqcat25_coverage_comparison",
               "training": {"single": [12], "joint": [9, 10, 11, 12]}, "validation": [7, 8],
               "updates": 100, "target": "forces_only", "lr": 1e-4, "batch_size": 1, "seed": 0,
               "force_target_eV_per_A": 0.03, "train_sha256": sha(dest / "train_points.json"),
               "validation_sha256": sha(dest / "validation_points.json"), "template_sha256": sha(template),
               "base_path": BASE, "base_sha256": BASE_SHA, "state_sha256": digest(state_bytes),
               "user_request_sha256": sha(dest / "user_request.txt"), "remote_dir": remote,
               "previous_fit_rejection_sha256": sha(failed / "native_and_return_packet.json"),
               "backend_config_sha256": sha(config), "backend_hostname": runtime["hostname"]})
    job = f'''#!/bin/bash
set -euo pipefail
test "$(hostname -s)" = {runtime["hostname"]}
test "$(pwd -P)" = {remote}
test "${{SLURM_NTASKS:-0}}" = 1
test -n "${{SLURM_JOB_ID:-}}"
case "${{CUDA_VISIBLE_DEVICES:-}}" in ''|*,*) exit 2;; esac
umask 077
trap 'code=$?; (set -C; printf "%s %s\\n" "$SLURM_JOB_ID" "$code" > producer_exit.txt)' EXIT
sha256sum -c SHA256SUMS
printf '%s  %s\\n' {runtime["python_launcher_sha256"]} {runtime["python"]} | sha256sum -c -
mkdir tmp cache
export TMPDIR="$PWD/tmp" XDG_CACHE_HOME="$PWD/cache" TORCH_HOME="$PWD/cache/torch"
export HF_HOME="$PWD/cache/hf" CUDA_CACHE_PATH="$PWD/cache/cuda" MPLCONFIGDIR="$PWD/cache/mpl"
export PYTHONDONTWRITEBYTECODE=1 CUDA_CACHE_DISABLE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_MODE=disabled WITH_PYG_LIB=0
export TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
for arm in single joint evaluate; do
    printf 'STAGE %s\\n' "$arm"
    {runtime["python"]} -B run_comparison.py "$arm" --request-sha256 {sha(dest / "request.json")}
done
'''
    (dest / "job.sh").write_bytes(job.encode("ascii"))
    files = {p.name: sha(p) for p in sorted(dest.iterdir())}
    (dest / "SHA256SUMS").write_bytes("".join(f"{v}  {k}\n" for k, v in files.items()).encode())
    print(json.dumps({"bundle": str(dest), "sha256sums_sha256": sha(dest / "SHA256SUMS")}))


def transport(b):
    s = b["ssh"]
    options = ["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=8", "-i", s["identity_file"]]
    return options, str(s["port"]), f"{s['user']}@{s['host']}"


def submit(dest, expected):
    config, b = backend()
    assert dest.name == NAME and sha(dest / "SHA256SUMS") == expected
    for line in (dest / "SHA256SUMS").read_text().splitlines():
        value, name = line.split("  ", 1)
        assert Path(name).name == name and sha(dest / name) == value
    req = json.loads((dest / "request.json").read_bytes())
    assert req["backend_config_sha256"] == sha(config)
    opts, port, address = transport(b)
    ssh = ["ssh", "-T", *opts, "-p", port, address]
    q = shlex.quote
    remote = req["remote_dir"]
    assert remote == "/home/sbq/sbq/chco_paper_aqcat25_ft512_20261112_v1/" + NAME
    limit = b["scoped_force_training"][NAME]
    runtime = b["ba_sella_runtime"]
    reservation = dest.parent / f"{NAME}_submission_attempt.json"
    write_json(reservation, {"bundle": expected, "intended_remote_dir": remote, "automatic_retries": 0})
    parent = str(Path(remote).as_posix().rsplit("/", 1)[0])
    subprocess.run(ssh + [f'test "$(realpath -e {q(parent)})" = {q(parent)} && (umask 077 && mkdir {q(remote)})'],
                   check=True, capture_output=True, timeout=25)
    send = sorted([p for p in dest.iterdir() if p.is_file()])
    subprocess.run(["scp", "-q", *opts, "-P", port, *map(str, send), f"{address}:{remote}/"],
                   check=True, capture_output=True, timeout=120)
    command = ["sbatch", "--parsable", "--no-requeue", "--partition=compute",
               f"--nodelist={runtime['hostname']}", "--nodes=1", "--ntasks=1",
               f"--cpus-per-task={limit['cpus_per_task']}", "--gres=gpu:1",
               f"--mem={limit['memory']}", f"--time={limit['time_limit']}",
               "--job-name=chco-force-coverage", f"--chdir={remote}",
               f"--output={remote}/slurm-%j.out", f"--error={remote}/slurm-%j.err", "job.sh"]
    checked = f"cd {q(remote)} && printf '%s  SHA256SUMS\\n' {expected} | sha256sum -c - >/dev/null"
    checked += " && sha256sum --status -c SHA256SUMS && bash -n job.sh && " + shlex.join(command)
    result = subprocess.run(ssh + [checked], check=True, capture_output=True, timeout=60)
    job_id = result.stdout.decode().strip().split(";", 1)[0]
    assert job_id.isdecimal()
    receipt = {"status": "SUBMITTED", "host": "BUCT3", "job_id": job_id, "remote_dir": remote,
               "limits": limit, "bundle_sha256": expected, "raw_sbatch_stdout": result.stdout.decode(),
               "new_dft_submitted": False}
    write_json(dest.parent / f"{NAME}_submission_record.json", receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "submit"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.path.resolve(strict=True))
    else:
        submit(args.path.resolve(strict=True), args.sha256)
