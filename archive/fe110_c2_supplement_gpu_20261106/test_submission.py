"""Local exact-input and admission guards; no GPU, model or scheduler writes."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts import aqcat25_handoff, artifact_io
from .prepare import PACKAGE, REVIEW_SHA, MODEL_SHA


with patch.dict(sys.modules, {"artifact_io": artifact_io, "aqcat25_handoff": aqcat25_handoff}):
    spec = importlib.util.spec_from_file_location("supplement_worker", Path(__file__).with_name("worker.py"))
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.request = artifact_io.load_json_object(PACKAGE / "request.json")
        self.digest = artifact_io.sha256_file(PACKAGE / "request.json")

    def test_exact_twelve_and_all_artifacts(self):
        self.assertEqual([r["name"] for r in self.request["cases"]], worker.NAMES)
        self.assertEqual(self.request["model"]["sha256"], MODEL_SHA)
        self.assertEqual(self.request["source_review_sha256"], REVIEW_SHA)
        for row in self.request["artifacts"]:
            self.assertEqual(artifact_io.sha256_file(PACKAGE / row["path"]), row["sha256"])

    def test_original_seed_hashes_and_handoffs(self):
        source = artifact_io.load_json_object(PACKAGE / "evidence/source_review.json")
        accepted = {r["name"]: r["structure_sha256"] for r in source["candidates"]}
        for case in self.request["cases"]:
            self.assertEqual(artifact_io.sha256_file(PACKAGE / case["seed_path"]), accepted[case["name"]])
            aqcat25_handoff.validate_handoff(PACKAGE / case["handoff_path"], root=PACKAGE,
                                           schema_path=PACKAGE / "handoff.schema.json")

    def test_authorization_and_no_scope_expansion(self):
        auth = artifact_io.load_json_object(PACKAGE / "authorization.json")
        self.assertEqual(auth["request_sha256"], self.digest)
        self.assertFalse(auth["VASP_authorized"])
        worker.verify_budget(self.request)
        for field in self.request["boundaries"]:
            with self.subTest(field=field):
                altered = dict(self.request, boundaries=dict(self.request["boundaries"], **{field: True}))
                with self.assertRaisesRegex(ValueError, "expansion"):
                    worker.verify_budget(altered)

    def test_hash_mutation_rejected_before_host_or_model(self):
        with self.assertRaisesRegex(ValueError, "request hash changed"):
            worker.verify(PACKAGE / "request.json", "0" * 64)

    def test_no_slurm_allocation_rejected_without_model(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(worker.subprocess, "check_output") as run:
            with self.assertRaisesRegex(ValueError, "scheduler-allocated"):
                worker.gpu_admission(self.digest)
            run.assert_not_called()

    def test_allocated_gpu_binding_and_existing_process_rejection(self):
        env = {"SLURM_JOB_ID": "123", "CUDA_VISIBLE_DEVICES": "0", "SLURM_JOB_GPUS": "2"}
        record = f"JobState=RUNNING Comment={self.digest} NodeList=MZ73".encode()
        info = b"GPU-test, NVIDIA RTX 4090, 24564, 24000\n"
        with patch.dict("os.environ", env, clear=True), patch.object(worker.subprocess, "check_output",
                side_effect=[record, info, b""]):
            self.assertEqual(worker.gpu_admission(self.digest)["SLURM_JOB_GPUS"], "2")
        with patch.dict("os.environ", env, clear=True), patch.object(worker.subprocess, "check_output",
                side_effect=[record, info, b"5678\n"]):
            with self.assertRaisesRegex(ValueError, "already has a compute process"):
                worker.gpu_admission(self.digest)


if __name__ == "__main__":
    unittest.main()
