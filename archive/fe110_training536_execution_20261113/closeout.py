"""Verify the completed trial and frozen inputs; never promote the new model."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .checkpoint import OUT, REMOTE
from .submit import ARM, ROOT

PROGRAM = r'''
import hashlib,json
from pathlib import Path
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as handle:
  for block in iter(lambda:handle.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
root=Path(ROOT);package=Path('/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control')
checks={name:digest(package/name)==sha for name,sha in EXPECTED.items()}
checkpoints=list((root/'checkpoints').rglob('best_checkpoint.pt'))
if len(checkpoints)!=1:raise ValueError('unique native best changed')
recovered=json.loads((root/'recovery_v2/candidate_recovery.json').read_text())
record={'prepared_input_hash_checks':checks,'all_prepared_inputs_unchanged':all(checks.values()),
 'native_best_still_matches':digest(checkpoints[0])==recovered['candidate_sha256'],
 'candidate_still_matches':digest(root/'output/job_14505/candidate.pt')==recovered['candidate_sha256'],
 'producer_pid_still_exists':Path('/proc/1346701').exists(),
 'native_output_directories_within_execution_root':True,'new_training_or_inference':False}
# All recorded native output directories were inspected in checkpoint metadata;
# this step checks their canonical containment without loading a force model.
metadata=json.loads((root/'recovery/checkpoint_metadata_inspection.json').read_text())
for item in metadata['records']:
 for key,value in item.get('config_cmd',{}).items():
  if key.endswith('_dir') and not Path(value).resolve().is_relative_to(root.resolve()):record['native_output_directories_within_execution_root']=False
with (root/'recovery_v2/input_integrity_after.json').open('x') as handle:json.dump(record,handle,indent=2)
print(json.dumps(record))
'''


def checkpoint_directories(out):
    return sorted(path for path in out.glob("checkpoint_*") if path.is_dir())


def run():
    returned = OUT / "returned"
    context = load_json_object(OUT.with_name("training536_execution_20261113_v1") / "request_context.json")
    expected = {name: sha256_file(ARM / name) for name in [
        "training_request.json", "config.yml", "training_manifest.json", "train.db", "development.db",
        "train_metadata.npz", "development_metadata.npz"]}
    program = "ROOT=" + repr(REMOTE) + "\nEXPECTED=" + repr(expected) + "\n" + PROGRAM
    compile(program, "<read-only-post-training-integrity>", "exec")
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    options = ["-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12"]
    destination = ssh["user"] + "@" + ssh["host"]
    receipt_path = OUT / "post_training_integrity_process.json"
    if receipt_path.exists():
        if (load_json_object(receipt_path)["exit_code"] != 0
                or not (returned / "input_integrity_after.json").is_file()
                or not (returned / "checkpoint_metadata_inspection.json").is_file()):
            raise RuntimeError("existing integrity operation needs receipt review; do not repeat writes")
    else:
        with (OUT / "post_training_integrity.stdout").open("xb") as stdout, (OUT / "post_training_integrity.stderr").open("xb") as stderr:
            checked = subprocess.run(["ssh", "-T", *options, "-p", str(ssh["port"]), destination, "python3 -B -"],
                                     input=program.encode(), stdout=stdout, stderr=stderr, timeout=45)
        write_json_exclusive(receipt_path, {"exit_code": checked.returncode})
        if checked.returncode:
            raise RuntimeError("inspect post-training integrity output")
        copied = subprocess.run(["scp", "-q", *options, "-P", str(ssh["port"]),
                                 destination + ":" + REMOTE + "/recovery_v2/input_integrity_after.json",
                                 destination + ":" + REMOTE + "/recovery/checkpoint_metadata_inspection.json",
                                 str(returned)], capture_output=True, timeout=30)
        if copied.returncode:
            raise RuntimeError("post-training evidence return failed; preserve existing files")
    remote = load_json_object(returned / "input_integrity_after.json")
    recovery = load_json_object(returned / "candidate_recovery.json")
    completed = load_json_object(returned / "training_completed.json")
    native_device = load_json_object(returned / "execution_device.json")
    final_checkpoints = checkpoint_directories(OUT)
    terminal = None
    terminal_source = None
    for path in final_checkpoints:
        fields = {token.split("=", 1)[0]: token.split("=", 1)[1] for token in
                  (path / "scheduler.stdout").read_text(encoding="utf-8").split() if "=" in token}
        if fields.get("JobState") == "FAILED" and fields.get("ExitCode") == "1:0":
            terminal, terminal_source = fields, path / "scheduler.stdout"
    if terminal is None or terminal["RunTime"] != "00:02:57":
        raise ValueError("preserved native terminal evidence missing")
    frozen_after = frozen_hashes()
    guards = {
        "frozen_512_536_12_inputs_unchanged": frozen_after == context["frozen_hashes_before"],
        "current_task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == context["current_task_sha256"],
        "backend_policy_unchanged": sha256_file(ROOT / "configs/execution_backends.yaml") == context["backend_policy_sha256_before"],
        "prepared_request_unchanged": expected["training_request.json"] == context["training536_request_sha256"],
        "remote_prepared_inputs_unchanged": remote["all_prepared_inputs_unchanged"],
        "native_best_and_remote_candidate_match": remote["native_best_still_matches"] and remote["candidate_still_matches"],
        "local_candidate_matches": sha256_file(returned / "candidate.pt") == recovery["candidate_sha256"],
        "one_CUDA_model": native_device["all_model_parameters_cuda"] and native_device["model_device"] == "cuda:0",
        "two_epochs_1072_real_updates": completed["epochs"] == 2 and completed["native_iterations"] == 1072 and completed["actual_optimizer_updates"] == 1072,
        "finite_new_weights": recovery["all_state_tensors_finite"],
        "pretrained_checkpoint_unchanged": recovery["pretrained_sha256_unchanged"],
        "producer_terminated": not remote["producer_pid_still_exists"],
        "native_writes_within_separate_execution_root": remote["native_output_directories_within_execution_root"],
    }
    summary = {"status": "TRAINING_COMPLETE_NATIVE_BEST_RECOVERED_WRAPPER_FAILURE_PRESERVED",
               "guards": guards, "all_guards_pass": all(guards.values()), "scheduler_job_id": "14505",
               "native_scheduler_terminal_state": "FAILED", "native_scheduler_exit_code": "1:0",
               "failure_phase": "post_training_best_export_search_scope", "training_retried": False,
               "native_iterations": 1072, "actual_optimizer_updates": 1072, "epochs": 2,
               "development_role_vector_MAE_eV_A": recovery["best_val_metric"],
               "candidate_sha256": recovery["candidate_sha256"], "candidate_path": str(returned / "candidate.pt"),
               "main_allocation_seconds": 177, "prior_preflight_allocation_seconds": [1, 9],
               "total_allocation_seconds": 187, "total_GPU_hours": 187 / 3600,
               "main_native_CLI_seconds": 164.0691432952881,
               "new_DFT": 0, "heldout_inference": False, "scientific_acceptance": False, "model_promoted": False,
               "frozen_hashes_after": frozen_after,
               "source_files": source_file_manifest([Path(__file__), terminal_source,
                   *[returned / n for n in ["candidate_recovery.json", "input_integrity_after.json", "training_completed.json",
                     "execution_device.json", "native_two_backward_check.json", "allocation_preflight.json", "job_exit_record.json"]]])}
    write_json_exclusive(OUT / "final_verification.json", summary)
    print({k: v for k, v in summary.items() if k not in ["source_files", "frozen_hashes_after"]})
    if not summary["all_guards_pass"]:
        raise RuntimeError("final verification failed; do not promote or retrain")


if __name__ == "__main__":
    run()
