"""Non-GPU regression checks for the exact startup failure and execution scope."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import device
from .prepare import OUT, PARENT, environment
from scripts.artifact_io import load_json_object, sha256_file
from scripts.aqcat25_handoff import validate_handoff


class DeviceTests(unittest.TestCase):
    def test_index_namespaces_do_not_select_gpu(self):
        evidence = []
        reply = SimpleNamespace(returncode=0, stdout="GPU-physical, 00000000:41:00.0, RTX4090, 24564, 24000\n", stderr="")
        with patch.dict(os.environ, {"SLURM_JOB_GPUS": "1", "CUDA_VISIBLE_DEVICES": "0"}), \
                patch.object(device.subprocess, "run", return_value=reply) as execute:
            result = device.query_identity("0000:41:00.0", evidence)
        self.assertEqual(result["physical_gpu_uuid"], "GPU-physical")
        self.assertEqual(execute.call_args.args[0][2], "0000:41:00.0")
        self.assertEqual(len(evidence), 1)

    def test_physical_mismatch_rejected(self):
        reply = SimpleNamespace(returncode=0, stdout="GPU-wrong,00000000:81:00.0,A800,80000,79000", stderr="")
        with patch.object(device.subprocess, "run", return_value=reply), self.assertRaises(ValueError):
            device.query_identity("0000:41:00.0", [])

    def test_failed_query_preserves_output(self):
        evidence = []
        reply = SimpleNamespace(returncode=6, stdout="object not found", stderr="native failure")
        with patch.object(device.subprocess, "run", return_value=reply), self.assertRaises(RuntimeError):
            device.command(["nvidia-smi"], evidence)
        self.assertEqual(evidence[0]["exit_code"], 6)
        self.assertEqual(evidence[0]["stderr"], "native failure")

    def test_cpu_model_rejected(self):
        calc = SimpleNamespace(model=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device="cpu")])))
        with self.assertRaises(RuntimeError):
            device.model_binding(calc, {"scheduler_job_id": "8"})

    def test_cuda_model_with_numeric_visible_device_accepted(self):
        calc = SimpleNamespace(model=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device="cuda:0")])))
        with patch.dict(os.environ, {"SLURM_JOB_ID": "8", "CUDA_VISIBLE_DEVICES": "0"}):
            result = device.model_binding(calc, {"scheduler_job_id": "8", "physical_gpu_uuid": "GPU-real"})
        self.assertEqual(result["model_devices"], ["cuda:0"])

    def test_other_process_rejected(self):
        allocation = "JobState=RUNNING Comment=hash NodeList=MZ73"
        with patch.dict(os.environ, {"SLURM_JOB_ID": "8"}), \
                patch.object(device.socket, "gethostname", return_value="MZ73"), \
                patch.object(device, "command", side_effect=[allocation, "999999\n"]), \
                patch.object(device, "allocated_identity", return_value={"free_MiB": 24000, "physical_gpu_uuid": "GPU-real"}), \
                self.assertRaises(ValueError):
            device.gpu_admission("hash", "MZ73", "unused", [])

    def test_runtime_paths_and_custom_import_order(self):
        for backend in ("aqcat_gpu", "buct2_gpu"):
            _, env, _ = environment(backend)
            paths = env["PYTHONPATH"].split(":")
            self.assertLess(next(i for i, path in enumerate(paths) if path.endswith("python_pkgs")),
                            next((i for i, path in enumerate(paths) if path.endswith("site-packages")), 999))
            self.assertNotIn("HOME", env)

    def test_packages_same12_and_no_permit(self):
        parent = load_json_object(PARENT / "request.json")
        for backend in ("aqcat_gpu", "buct2_gpu"):
            root = OUT / backend / "package"
            request = load_json_object(root / "request.json")
            self.assertEqual(parent["cases"], request["cases"])
            self.assertEqual(parent["limits"], request["limits"])
            self.assertEqual(parent["resources"], request["resources"])
            self.assertNotIn("arbitration", request)
            self.assertEqual(request["replica_policy"], "independent_first_completed_eligible_review")
            for item in request["artifacts"]:
                self.assertEqual(sha256_file(root / item["path"]), item["sha256"])
            for case in request["cases"]:
                validate_handoff(root / case["handoff_path"], root=root, schema_path=root / "handoff.schema.json")
            sys.path.insert(0, str(Path(__file__).parent.resolve()))
            try:
                source = (root / "worker.py").read_text(encoding="utf-8")
                self.assertNotIn("await_permit", source)
                self.assertNotIn("winner_permit", source)
            finally:
                sys.path.pop(0)
            self.assertTrue(json.loads((root / "authorization.json").read_text())["user_authorized"])


if __name__ == "__main__":
    unittest.main()
