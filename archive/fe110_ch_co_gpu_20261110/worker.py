"""Execute one reviewed Slurm allocation, with device proof before ML loading."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import os
import signal
import socket

from artifact_io import load_json_object, sha256_file, write_json_exclusive
from device import gpu_admission, model_binding


def run(root, expected):
    request_path = root / "request.json"
    if sha256_file(request_path) != expected:
        raise ValueError("Request changed.")
    request = load_json_object(request_path)
    authorization = load_json_object(root / "authorization.json")
    if authorization["request_sha256"] != expected or not authorization["user_authorized"]:
        raise ValueError("Unbound authorization.")
    bundle = load_json_object(root / "bundle.json")
    for row in bundle["artifacts"]:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != row["sha256"]:
            raise ValueError("Changed/escaped package artifact.")
    output = root / "output"
    admission_dir = root / "admission"
    admission_dir.mkdir(exist_ok=False)
    evidence, devices = [], []
    code, error = 1, None
    try:
        if socket.gethostname() != "MZ73" or not root.resolve().is_relative_to(Path("/home/sbq/sbq").resolve()):
            raise ValueError("Wrong host/write root.")
        admission = gpu_admission(expected, "MZ73", bundle["cudart"], evidence)
        write_json_exclusive(admission_dir / "gpu_admission.json", admission)
        import torch
        torch.cuda.set_per_process_memory_fraction(.80, 0)
        from dual_model_ml_neb import run_dual_model_request, seal_successful_run
        from mlip_same_structure_benchmark import _load_calculator

        def loader(backend, checkpoint, device):
            calculator = _load_calculator(backend, checkpoint, device)
            devices.append({"backend": backend, **model_binding(calculator, admission)})
            write_json_exclusive(admission_dir / (backend + "_model_device.json"), devices[-1])
            return calculator

        def interrupted(signum, _frame):
            raise TimeoutError("Scheduler signal " + str(signum))

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        manifest = run_dual_model_request(request_path, Path(bundle["primary_checkpoint"]),
                   Path(bundle["secondary_checkpoint"]), output, device="cuda", calculator_loader=loader)
        seal_successful_run(output, manifest)
        code = 0
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        write_json_exclusive(admission_dir / "device_commands.json", {"commands": evidence})
        write_json_exclusive(root / "worker_exit.json", {"exit_code": code, "error": error,
            "job_id": os.environ.get("SLURM_JOB_ID"), "request_sha256": expected,
            "finished_at": datetime.now(timezone.utc).isoformat(), "evidence_class": "producer_process_not_scheduler",
            "GPU_models_loaded": [row["backend"] for row in devices]})
    if code:
        raise SystemExit(error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    run(args.root, args.request_sha256)
