"""Prepare new immutable packages; retain the source seeds, checkpoint and budgets."""
from pathlib import Path
import shlex

from archive.fe110_c2_supplement_gpu_20261106.prepare import PACKAGE as PARENT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.aqcat25_handoff import validate_handoff

OUT = Path("calculations/fe110_c2_site_supplement_20261106/gpu_independent_repair_20261107_v1")
REMOTE = "/home/sbq/sbq/fe110_c2_supplement_independent_20261107_v1"
BOLD = "/home/sbq/sbq/fe110_c2_supplement_buct2_20261106_v1"
PARENT_SHA = "b95896f6da62f52d504c97663b4a30e0b3121872463a73f95ea277f6edaf553d"
SITE = "/home/sbq/sbq/ml_ts_acceleration/venv/lib/python3.10/site-packages"


def environment(backend):
    prefix = "" if backend == "aqcat_gpu" else BOLD + "/deps"
    python = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python" if not prefix else prefix + "/usr/bin/python3.10"
    paths = [REMOTE, REMOTE + "/runtime", prefix + "/home/sbq/sbq/aqcat25/python_pkgs",
             prefix + "/home/sbq/sbq/aqcat25/vendor"]
    if prefix:
        paths.append(prefix + SITE)
    env = {"PYTHONPATH": ":".join(paths), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "WANDB_MODE": "disabled", "OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}
    for key, suffix in {"MPLCONFIGDIR": "matplotlib", "XDG_CACHE_HOME": "xdg", "TORCH_HOME": "torch",
            "HF_HOME": "huggingface", "TRITON_CACHE_DIR": "triton", "TORCH_EXTENSIONS_DIR": "extensions",
            "TORCHINDUCTOR_CACHE_DIR": "inductor", "NUMBA_CACHE_DIR": "numba"}.items():
        env[key] = REMOTE + "/cache/" + suffix
    env["TMPDIR"] = REMOTE + "/tmp"
    if prefix:
        env.update(PYTHONHOME=prefix + "/usr", LD_LIBRARY_PATH=BOLD + "/native_libs")
    return python, env, prefix + SITE + "/nvidia/cuda_runtime/lib/libcudart.so.12"


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(source.read_bytes())


def main():
    if sha256_file(PARENT / "request.json") != PARENT_SHA:
        raise ValueError("source request changed")
    parent = load_json_object(PARENT / "request.json")
    for backend in ("aqcat_gpu", "buct2_gpu"):
        base = OUT / backend
        package = base / "package"
        package.mkdir(parents=True, exist_ok=False)
        for item in parent["artifacts"]:
            source = PARENT / item["path"]
            if sha256_file(source) != item["sha256"]:
                raise ValueError("source bytes changed")
            if item["path"] not in {"worker.py", "run.sbatch", "execution_backends.yaml"}:
                copy(source, package / item["path"])
        copy(Path("configs/execution_backends.yaml"), package / "execution_backends.yaml")
        for name in ("device.py", "worker.py"):
            copy(Path(__file__).with_name(name), package / name)
        python, env, cudart = environment(backend)
        runtime = load_json_object(OUT / "runtime_identity.json")[backend]
        if runtime["cudart_path"] != cudart:
            raise ValueError("unexpected native CUDA runtime")
        exports = "\n".join("export " + key + "=" + shlex.quote(value) for key, value in env.items())
        directories = " ".join(shlex.quote(value) for key, value in env.items()
                               if key.endswith("_DIR") or key in {"TMPDIR", "MPLCONFIGDIR", "XDG_CACHE_HOME", "TORCH_HOME", "HF_HOME"})
        script = f'''#!/bin/bash
#SBATCH --job-name=fe110-c2-independent
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:10:00
#SBATCH --signal=B:TERM@15
#SBATCH --chdir={REMOTE}
#SBATCH --output={REMOTE}/slurm-%j.out
#SBATCH --error={REMOTE}/slurm-%j.err
set -euo pipefail
: "${{SLURM_JOB_ID:?real Slurm job required}}"
: "${{REQUEST_SHA256:?request binding required}}"
{exports}
mkdir -p {directories}
exec {python} {REMOTE}/worker.py run --request {REMOTE}/request.json --sha256 "$REQUEST_SHA256"
'''
        with (package / "run.sbatch").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(script)
        for case in parent["cases"]:
            validate_handoff(package / case["handoff_path"], root=package, schema_path=package / "handoff.schema.json")
        request = {**parent, "document_kind": "fe110_c2_independent_gpu_repair", "backend": backend,
                   "remote_root": REMOTE, "parent_request_sha256": PARENT_SHA,
                   "replica_policy": "independent_first_completed_eligible_review",
                   "cudart": {"path": cudart, "sha256": runtime["cudart_sha256"]},
                   "model": {**parent["model"], "path": parent["model"]["path"] if backend == "aqcat_gpu"
                             else BOLD + "/deps" + parent["model"]["path"]},
                   "artifacts": [{"path": path.relative_to(package).as_posix(), "sha256": sha256_file(path)}
                                 for path in sorted(package.rglob("*")) if path.is_file()]}
        write_json_exclusive(package / "request.json", request)
        write_json_exclusive(package / "authorization.json", {"action": "REPAIR_AND_RUN_INDEPENDENT_GPU_REPLICAS",
            "user_authorized": True, "request_sha256": sha256_file(package / "request.json"),
            "parent_request_sha256": PARENT_SHA, "user_request": "修复啊 跟我说干嘛",
            "prior_replica_request": "不能两个任务在两个服务器一起提交吗 哪个算完用哪个啊",
            "VASP_authorized": False, "training_authorized": False})
        print(backend, "PREPARED12", sha256_file(package / "request.json"), flush=True)


if __name__ == "__main__":
    main()
