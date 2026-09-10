from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import sha256_file
from scripts.prepare_matris_remote_finetune_bundle import _job_script, _remote_path

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "/home/sbq/sbq"
WRAPPERS = [
    "aqcat25_gpu_job.sh", "aqcat25_ml_neb_job.sh", "aqcat25_ts_finetune_job.sh",
    "aqcat25_ts_force_prediction_batch_job.sh", "dual_model_ml_neb_job.sh",
    "dual_model_ts_force_prediction_batch_job.sh", "dual_model_ts_force_prediction_batch_job_v2.sh",
    "matris_finetune_speed_benchmark_job.sh", "mlip_same_structure_benchmark_job.sh", "generated_matris",
]
VENDOR_WRAPPERS = [name for name in WRAPPERS if name.startswith(("dual_", "matris_", "mlip_", "generated_"))]


def posix(path: Path) -> str:
    value = path.resolve().as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


def bootstrap(text: str) -> str:
    return text[text.index("# BEGIN GPU BOOTSTRAP"):text.index("# END GPU BOOTSTRAP GUARD")]


class Sandbox:
    def __init__(self, path: Path, name: str):
        self.bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
        assert Path(self.bash).is_file(), "Bash is required for the execution lifecycle tests"
        self.root = path / "allowed"
        self.cwd = self.root / "work"
        self.cwd.mkdir(parents=True)
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        self.pilot = self.root / "aqcat25_ts_pilot"
        self.pilot.mkdir()
        self.vendor = self.root / "mlip_same_structure_benchmark_20260825/vendor/MatRIS"
        (self.vendor / "matris").mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.command("hostname", 'printf "%s\\n" "${FAKE_HOST:-MZ73}"\n')
        self.command("nvidia-smi", 'echo "must not query GPUs in tests" >&2; exit 99\n')
        self.python = self.root / "ml_ts_acceleration/venv/bin/python"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(r"""#!/bin/bash
if [ "$1" = "-" ]; then
  [ "${RECORD_EXIT:-0}" = 0 ] || exit "$RECORD_EXIT"
  if [ -n "${EXIT_RECORD:-}" ]; then
    printf '{"status":"%s","exit_code":%d}\n' "$(if [ "${EXIT_CODE:-0}" = 0 ]; then echo success; else echo failed; fi)" "${EXIT_CODE:-0}" > "$EXIT_RECORD"
  fi
  exit 0
fi
printf '%s\n' "$*" >> "$CALL_LOG"
if [ "${INTERRUPT_PAYLOAD:-0}" = 1 ]; then
  kill -TERM "$PPID"
  exit 143
fi
if [ "$1" = "-c" ]; then
  case "$2" in
    *epochs*) echo 1 ;;
    *sha256*) sha256sum "$CHECKPOINT" | cut -d' ' -f1 ;;
    *) printf '%s\n' "$CHECKPOINT" ;;
  esac
elif [ "$1" = "-m" ]; then
  printf 'synthetic trained fixture' > "$PWD/best_checkpoint.pt"
fi
exit "${PAYLOAD_EXIT:-0}"
""", encoding="utf-8", newline="\n")
        self.python.chmod(0o700)
        self.checkpoint = self.root / "checkpoint"
        self.checkpoint.write_text("synthetic checkpoint fixture", encoding="ascii")
        names = ["handoff.json", "request.json", "path_prediction_batch_request.json",
                 "dual_model_prediction_batch_request.json", "experiment_manifest.json",
                 "benchmark_manifest.json", "training.json", "review.json", "authorization.json"]
        for filename in names:
            (self.inputs / filename).write_text("{}", encoding="ascii")
        (self.inputs / "runtime").mkdir()
        (self.inputs / "runtime/artifact_io.py").write_text("# fake vendor support", encoding="ascii")
        digest = sha256_file(self.inputs / "handoff.json")
        helper = (ROOT / "scripts/aqcat25_mz73_env.sh").read_text(encoding="utf-8")
        self.helper = self.pilot / "aqcat25_mz73_env.sh"
        if name == "generated_matris":
            self.helper = self.inputs / "code/scripts/aqcat25_mz73_env.sh"
            self.helper.parent.mkdir(parents=True)
            args = SimpleNamespace(base_checkpoint=BOUNDARY + "/checkpoint", epochs=1,
                                   force_weight=1.0, energy_weight=1.0, learning_rate=0.001,
                                   weight_decay=0.0, gradient_clip_norm=1.0, trainable_scope="all", seed=1)
            text = _job_script(args, BOUNDARY + "/input", self.inputs / "review.json",
                               self.inputs / "authorization.json", sha256_file(self.checkpoint))
        else:
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        # Only disposable test copies replace the hard-coded boundary. Production
        # wrappers have no environment switch that disables containment or MZ73.
        self.helper.write_text(helper.replace(BOUNDARY, posix(self.root)), encoding="utf-8", newline="\n")
        self.script = self.root / name
        self.script.write_text(text.replace(BOUNDARY, posix(self.root)), encoding="utf-8", newline="\n")
        self.output = self.root / "output"
        if name == "aqcat25_gpu_job.sh":
            self.output = self.inputs / "output/job_123"
        elif name == "aqcat25_ts_finetune_job.sh":
            self.output = self.pilot / "active_learning/job_123/output"
        elif name == "generated_matris":
            self.output = self.inputs / "results/job_123"
        self.env = {**os.environ}
        for key in ("XDG_CACHE_HOME", "TORCH_HOME", "HF_HOME", "TMPDIR", "AQCAT_MZ73_HOST"):
            self.env.pop(key, None)
        self.env.update({
            "SLURM_JOB_ID": "123", "AQCAT_PILOT_ROOT": posix(self.pilot),
            "AQCAT_ENV": posix(self.helper), "AQCAT_ROOT": posix(self.root / "aqcat25"),
            "AQCAT_PYTHON": posix(self.python), "PYTHON_BIN": posix(self.python),
            "HANDOFF_ROOT": posix(self.inputs), "BATCH_ROOT": posix(self.inputs),
            "REQUEST_ROOT": posix(self.inputs), "EXPERIMENT_ROOT": posix(self.inputs),
            "BENCHMARK_ROOT": posix(self.inputs), "BACKEND": "matris", "BACKEND_VERSION": "test",
            "TRAINING_MANIFEST": posix(self.inputs / "training.json"),
            "SOURCE_HANDOFF_SHA256": digest, "SOURCE_REQUEST_SHA256": digest,
            "SOURCE_BATCH_SHA256": digest, "SOURCE_MANIFEST_SHA256": digest, "EXPERIMENT_SHA256": digest,
            "PRIMARY_CHECKPOINT": posix(self.checkpoint), "SECONDARY_CHECKPOINT": posix(self.checkpoint),
            "CHECKPOINT": posix(self.checkpoint), "MATRIS_SOURCE": posix(self.vendor),
            "OUTPUT_ROOT": posix(self.output), "OUTPUT": posix(self.output / "prediction.json"),
            "CALL_LOG": posix(self.root / "payload_calls"),
        })

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o700)

    def run(self):
        command = ('export PATH="' + posix(self.bin) + ':$PATH"; cd -P "' + posix(self.cwd)
                   + '"; exec bash "' + posix(self.script) + '"')
        return subprocess.run([self.bash, "-c", command], cwd=self.cwd, env=self.env,
                              text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=25)

    def assert_failed(self, result, *, payload=False):
        assert result.returncode != 0, result.stdout + result.stderr
        records = [json.loads(line) for line in result.stderr.splitlines() if line.startswith('{"document_kind"')]
        assert records, result.stderr
        assert all(record["status"] == "failed" and record["exit_code"] != 0 for record in records)
        assert all(record["evidence_class"] == "producer_process_only_not_scheduler_accounting" for record in records)
        files = list(self.root.rglob("*producer_exit_record*.json"))
        assert files, result.stderr
        assert any(json.loads(path.read_text())["status"] == "failed" for path in files)
        assert (self.root / "payload_calls").exists() is payload


@pytest.mark.parametrize("name", WRAPPERS)
@pytest.mark.parametrize("failure", ["missing_job", "missing_helper", "missing_python", "output_setup", "wrong_host"])
def test_early_failures_leave_records(tmp_path, name, failure):
    sandbox = Sandbox(tmp_path, name)
    if failure == "missing_job":
        sandbox.env.pop("SLURM_JOB_ID")
    elif failure == "missing_helper":
        sandbox.helper.unlink()
    elif failure == "missing_python":
        sandbox.python.unlink()
    elif failure == "output_setup":
        sandbox.output.parent.mkdir(parents=True, exist_ok=True)
        sandbox.output.write_text("not a directory", encoding="ascii")
    else:
        sandbox.env["FAKE_HOST"] = "wrong-host"
    sandbox.assert_failed(sandbox.run())


@pytest.mark.parametrize("name", VENDOR_WRAPPERS)
def test_missing_vendor_leaves_record_without_payload(tmp_path, name):
    sandbox = Sandbox(tmp_path, name)
    (sandbox.vendor / "matris").rmdir()
    sandbox.assert_failed(sandbox.run())


@pytest.mark.parametrize("name", WRAPPERS)
@pytest.mark.parametrize("failure", ["payload", "signal", "receipt"])
def test_execution_and_record_failures_remain_failed(tmp_path, name, failure):
    sandbox = Sandbox(tmp_path, name)
    if failure == "payload":
        sandbox.env["PAYLOAD_EXIT"] = "17"
    elif failure == "signal":
        sandbox.env["INTERRUPT_PAYLOAD"] = "1"
    else:
        sandbox.env["RECORD_EXIT"] = "18"
        # NEB drivers own success records; request the wrapper's failure writer.
        if name in {"aqcat25_ml_neb_job.sh", "dual_model_ml_neb_job.sh"}:
            sandbox.env["PAYLOAD_EXIT"] = "17"
    sandbox.assert_failed(sandbox.run(), payload=True)


@pytest.mark.parametrize("name", WRAPPERS)
def test_canonical_symlink_escape_cannot_write_output(tmp_path, name):
    sandbox = Sandbox(tmp_path, name)
    outside = tmp_path / "outside"
    outside.mkdir()
    sandbox.output.parent.mkdir(parents=True, exist_ok=True)
    sandbox.output.symlink_to(outside, target_is_directory=True)
    sandbox.assert_failed(sandbox.run())
    assert list(outside.iterdir()) == []


def test_venv_interpreter_can_link_to_system_executable(tmp_path):
    sandbox = Sandbox(tmp_path, "dual_model_ml_neb_job.sh")
    system_python = tmp_path / "system-python"
    sandbox.python.rename(system_python)
    sandbox.python.symlink_to(system_python)
    result = sandbox.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox.root / "payload_calls").exists()


def test_interpreter_parent_cannot_escape_boundary(tmp_path):
    sandbox = Sandbox(tmp_path, "dual_model_ml_neb_job.sh")
    parent = sandbox.python.parent
    outside = tmp_path / "outside-bin"
    parent.rename(outside)
    parent.symlink_to(outside, target_is_directory=True)
    sandbox.assert_failed(sandbox.run())


@pytest.mark.parametrize("path", ["/tmp/x", "/home/sbq/sbq/../escape", "/home/sbq/sbq/x/../../escape"])
def test_generated_bundle_rejects_remote_traversal(path):
    with pytest.raises(ValueError):
        _remote_path(path)


def test_bootstrap_guard_has_one_source_and_all_shells_parse(tmp_path):
    common = (ROOT / "scripts/aqcat25_mz73_env.sh").read_text(encoding="utf-8")
    for name in WRAPPERS:
        sandbox = Sandbox(tmp_path / name, name)
        text = sandbox.script.read_text(encoding="utf-8").replace(posix(sandbox.root), BOUNDARY)
        assert bootstrap(text) == bootstrap(common), name
        result = subprocess.run([sandbox.bash, "-n", str(sandbox.script)], capture_output=True)
        assert result.returncode == 0, (name, result.stderr)


@pytest.mark.parametrize("name", WRAPPERS)
def test_success_path_preserves_payload_and_has_no_failure_record(tmp_path, name):
    sandbox = Sandbox(tmp_path, name)
    result = sandbox.run()
    assert result.returncode == 0, result.stderr
    assert (sandbox.root / "payload_calls").is_file()
    assert "gpu_wrapper_execution_failure" not in result.stderr


REQUIRED_INPUTS = {
    "aqcat25_gpu_job.sh": "HANDOFF_ROOT", "aqcat25_ml_neb_job.sh": "HANDOFF_ROOT",
    "aqcat25_ts_finetune_job.sh": "TRAINING_MANIFEST",
    "aqcat25_ts_force_prediction_batch_job.sh": "BATCH_ROOT",
    "dual_model_ml_neb_job.sh": "REQUEST_ROOT",
    "dual_model_ts_force_prediction_batch_job.sh": "BATCH_ROOT",
    "dual_model_ts_force_prediction_batch_job_v2.sh": "BATCH_ROOT",
    "matris_finetune_speed_benchmark_job.sh": "EXPERIMENT_ROOT",
    "mlip_same_structure_benchmark_job.sh": "BENCHMARK_ROOT",
}


@pytest.mark.parametrize("name", REQUIRED_INPUTS)
@pytest.mark.parametrize("failure", ["missing_input", "traversal"])
def test_required_input_and_canonical_parent_escape_fail_closed(tmp_path, name, failure):
    sandbox = Sandbox(tmp_path, name)
    key = REQUIRED_INPUTS[name]
    if failure == "missing_input":
        sandbox.env.pop(key)
    else:
        sandbox.env[key] = posix(sandbox.root) + "/../escape"
    sandbox.assert_failed(sandbox.run())
    assert not (tmp_path / "escape").exists()


def test_environment_cache_escape_is_rejected_before_setup(tmp_path):
    sandbox = Sandbox(tmp_path, "aqcat25_ml_neb_job.sh")
    sandbox.env["XDG_CACHE_HOME"] = posix(sandbox.root) + "/../external-cache"
    sandbox.assert_failed(sandbox.run())
    assert not (tmp_path / "external-cache").exists()


def test_missing_canonicalizer_still_emits_bootstrap_record(tmp_path):
    sandbox = Sandbox(tmp_path, "generated_matris")
    sandbox.command("realpath", "exit 44\n")
    sandbox.assert_failed(sandbox.run())


def test_invalid_digest_is_rejected_before_payload(tmp_path):
    sandbox = Sandbox(tmp_path, "dual_model_ml_neb_job.sh")
    sandbox.env["SOURCE_REQUEST_SHA256"] = "a" * 64 + "; unexpected command"
    sandbox.assert_failed(sandbox.run())


def test_existing_receipt_is_not_overwritten_by_emergency_record(tmp_path):
    sandbox = Sandbox(tmp_path, "aqcat25_gpu_job.sh")
    sandbox.output.mkdir(parents=True)
    receipt = sandbox.output / "producer_exit_record.json"
    original = '{"status":"success","prior_job":"different"}'
    receipt.write_text(original, encoding="ascii")
    sandbox.python.unlink()
    sandbox.assert_failed(sandbox.run())
    assert receipt.read_text() == original
    assert list(sandbox.output.glob("producer_exit_record.failure.*.json"))



def test_sourcing_environment_alone_does_not_install_job_traps(tmp_path):
    sandbox = Sandbox(tmp_path, "aqcat25_ml_neb_job.sh")
    command = '. "' + posix(sandbox.helper) + '"; exit 7'
    result = subprocess.run([sandbox.bash, "-c", command], cwd=sandbox.cwd,
                            text=True, capture_output=True, encoding="utf-8")
    assert result.returncode == 7
    assert not list(sandbox.root.rglob("*producer_exit_record*.json"))
    assert "gpu_wrapper_execution_failure" not in result.stderr


@pytest.mark.parametrize("cache", ["cache/xdg", "cache/torch", "cache/huggingface", "tmp"])
def test_generated_matris_cache_symlink_escape_is_rejected(tmp_path, cache):
    sandbox = Sandbox(tmp_path, "generated_matris")
    outside = tmp_path / "external-cache"
    outside.mkdir()
    cache_path = sandbox.root / "aqcat25" / cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.symlink_to(outside, target_is_directory=True)
    sandbox.assert_failed(sandbox.run())
    assert list(outside.iterdir()) == []
