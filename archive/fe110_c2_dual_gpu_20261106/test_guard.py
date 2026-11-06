"""Non-compute tests of exact-input retention and two-job fail-closed arbitration."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import aqcat25_handoff, artifact_io
from . import arbitrate
from .prepare import PACKAGE, PARENT, PARENT_SHA

with patch.dict(sys.modules, {"artifact_io": artifact_io, "aqcat25_handoff": aqcat25_handoff}):
    spec = importlib.util.spec_from_file_location("buct2_worker", Path(__file__).with_name("worker.py"))
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)


def snapshot(backend, state="RUNNING", start="2026-11-07T01:00:00"):
    base = {"state": state, "start_time": start, "tz_offset_seconds": 28800, "job_id": "2",
            "request_sha256": "a" * 64, "model_device": None, "ready": None,
            "checked_at": "2026-11-06T17:00:01+00:00"}
    if backend == "aqcat_gpu":
        base["model_device"] = {"device": "cuda:0"}
    else:
        base["ready"] = {"request_sha256": "a" * 64, "scheduler_job_id": "2", "model_loaded": False,
                         "checked_at": "2026-11-06T17:00:00+00:00"}
    return base


class GuardTests(unittest.TestCase):
    def test_both_pending_no_selection(self):
        self.assertIsNone(arbitrate.choose({n: snapshot(n, "PENDING") for n in ("aqcat_gpu", "buct2_gpu")}))

    def test_only_admitted_replica_selected(self):
        a = snapshot("aqcat_gpu", "PENDING")
        b = snapshot("buct2_gpu")
        self.assertEqual(arbitrate.choose({"aqcat_gpu": a, "buct2_gpu": b}), "buct2_gpu")
        b["ready"]["request_sha256"] = "wrong"
        self.assertIsNone(arbitrate.choose({"aqcat_gpu": a, "buct2_gpu": b}))

    def test_earlier_native_start_and_tie(self):
        for child_start, expected in [("2026-11-07T00:59:59", "buct2_gpu"),
                                      ("2026-11-07T01:00:01", "aqcat_gpu"),
                                      ("2026-11-07T01:00:00", "aqcat_gpu")]:
            with self.subTest(start=child_start):
                s = {"aqcat_gpu": snapshot("aqcat_gpu"), "buct2_gpu": snapshot("buct2_gpu", start=child_start)}
                self.assertEqual(arbitrate.choose(s), expected)

    def test_completed_primary_is_not_discarded(self):
        a = snapshot("aqcat_gpu", "COMPLETED")
        a["producer_exit"] = {"exit_code": 0}
        self.assertEqual(arbitrate.choose({"aqcat_gpu": a, "buct2_gpu": snapshot("buct2_gpu")}), "aqcat_gpu")

    def test_unknown_clock_fails_closed(self):
        s = {"aqcat_gpu": snapshot("aqcat_gpu"), "buct2_gpu": snapshot("buct2_gpu")}
        s["buct2_gpu"]["tz_offset_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "timezone"):
            arbitrate.choose(s)

    def test_late_replica_keeps_original_queue_slot(self):
        a = snapshot("aqcat_gpu", "PENDING")
        b = snapshot("buct2_gpu")
        b["checked_at"] = "2026-11-06T17:01:01+00:00"
        self.assertIsNone(arbitrate.choose({"aqcat_gpu": a, "buct2_gpu": b}))

    def test_failed_producer_not_selected_during_scheduler_lag(self):
        a = snapshot("aqcat_gpu")
        a["producer_exit"] = {"exit_code": 1}
        self.assertEqual(arbitrate.choose({"aqcat_gpu": a, "buct2_gpu": snapshot("buct2_gpu")}), "buct2_gpu")

    def test_no_permit_while_peer_active(self):
        with patch.object(arbitrate, "remote") as remote:
            with self.assertRaisesRegex(ValueError, "peer still active"):
                arbitrate.grant({}, {"state": "RUNNING"})
            remote.assert_not_called()

    def test_mismatched_or_nonterminal_permit_rejected(self):
        peer = {"peer_job_id": "11396", "peer_request_sha256": PARENT_SHA}
        valid = {"action": "RUN_EXACT_GPU_BATCH", "winner_job_id": "2", "request_sha256": "a" * 64,
                 "peer_job_id": "11396", "peer_request_sha256": PARENT_SHA, "peer_terminal_state": "CANCELLED"}
        worker.validate_permit(valid, "a" * 64, "2", peer)
        for key, value in [("peer_terminal_state", "RUNNING"), ("request_sha256", "wrong"), ("winner_job_id", "3")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                worker.validate_permit(dict(valid, **{key: value}), "a" * 64, "2", peer)

    def test_no_permit_times_out_without_model(self):
        with self.assertRaisesRegex(TimeoutError, "model was not loaded"):
            worker.await_permit(Path("nonexistent_local_test_root"), "a" * 64, "2", {}, seconds=0)

    def test_slurm_numeric_visible_device_keeps_native_provenance(self):
        model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=SimpleNamespace(type="cuda"))]))
        calc = SimpleNamespace(model=model)
        admission = {"scheduler_job_id": "2", "nvidia_smi": "GPU-test, NVIDIA A800, 80000, 70000"}
        with patch.dict("os.environ", {"SLURM_JOB_ID": "2", "CUDA_VISIBLE_DEVICES": "0"}, clear=True):
            result = worker.native_cuda_binding(calc, admission)
        self.assertEqual(result["scheduler_job_id"], "2")
        self.assertEqual(result["execution_mode"], "slurm")
        self.assertEqual(result["physical_gpu_uuid"], "GPU-test")

    def test_cpu_model_is_rejected_despite_gpu_allocation(self):
        model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=SimpleNamespace(type="cpu"))]))
        with self.assertRaisesRegex(RuntimeError, "not actually onCUDA"):
            worker.native_cuda_binding(SimpleNamespace(model=model), {})

    def test_model_constructor_is_after_guard(self):
        tree = ast.parse(Path(__file__).with_name("worker.py").read_text())
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
        calls = {n.func.id: n.lineno for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertLess(calls["await_permit"], calls["patched_calc"])

    def test_new_package_preserves_twelve_original_seeds(self):
        if not (PACKAGE / "request.json").exists():
            self.skipTest("package not built yet")
        child = artifact_io.load_json_object(PACKAGE / "request.json")
        parent = artifact_io.load_json_object(PARENT / "request.json")
        worker.verify_scope(child)
        self.assertEqual(child["cases"], parent["cases"])
        self.assertEqual(child["model"]["sha256"], parent["model"]["sha256"])
        for case in child["cases"]:
            self.assertEqual(artifact_io.sha256_file(PACKAGE / case["seed_path"]), case["seed_sha256"])
            aqcat25_handoff.validate_handoff(PACKAGE / case["handoff_path"], root=PACKAGE,
                                            schema_path=PACKAGE / "handoff.schema.json")


if __name__ == "__main__":
    unittest.main()
