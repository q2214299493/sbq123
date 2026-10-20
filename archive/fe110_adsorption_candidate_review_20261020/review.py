"""Development-only selection and a non-executable independent-validation proposal."""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.adsorption.force_finetune import load_manifest, validate_label_row

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
TRAINING = BASE / "adsorption_training_direct_20261020_v2"
POOL = BASE / "adsorption_pool_rebuild_20261019_v1/prepared_v2"
DEST = BASE / "adsorption_candidate_review_20261020_v1"


def checkpoint_metadata():
    """Read trusted own checkpoints on CPU only;no inference,training or remote writes."""
    DEST.mkdir(exist_ok=False)
    receipt = load_json_object(TRAINING / "verification_receipt.json")
    request = load_json_object(TRAINING / "package/control/training_request.json")
    backend = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]
    ssh = backend["ssh"]
    program = r'''
import gc,hashlib,json,socket,torch
from pathlib import Path
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
if socket.gethostname()!='MZ73':raise ValueError('unexpected host')
boundary=Path('/home/sbq/sbq').resolve()
if str(boundary)!='/home/ubuntu/hdd/sbq/sbq':raise ValueError('canonical boundary differs')
models={}
base_config=None
for name,item in MODELS.items():
 p=Path(item['path'])
 if not p.resolve().is_relative_to(boundary) or digest(p)!=item['sha256']:raise ValueError('checkpoint path/hash mismatch')
 payload=torch.load(p,map_location='cpu',weights_only=False)
 config=payload['config']
 if name=='baseline':base_config=config['model']
 elif config['model']!=base_config:raise ValueError('model architecture differs')
 models[name]={'path':str(p),'sha256':item['sha256'],'bytes':p.stat().st_size,
  'epoch':payload.get('epoch'),'step':payload.get('step'),'primary_metric':payload.get('primary_metric'),
  'best_val_metric':payload.get('best_val_metric'),'configured_primary_metric':config.get('evaluation_metrics',{}).get('primary_metric'),
  'architecture_matches_baseline':True}
 del payload;gc.collect()
print(json.dumps({'models':models,'CPU_metadata_read_only':True,'CUDA_initialized':torch.cuda.is_initialized(),
 'model_inference_or_training':False,'remote_files_written':False},allow_nan=False))
'''
    models = {"baseline": request["base_checkpoint"], **receipt["candidates"]}
    source = "MODELS=" + repr(models) + "\n" + program
    command = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"],
        "env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 CUDA_VISIBLE_DEVICES='' /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"]
    with (DEST / "checkpoint_metadata.json").open("xb") as output, (DEST / "checkpoint_metadata.stderr").open("xb") as errors:
        result = subprocess.run(command, input=source.encode(), stdout=output, stderr=errors, timeout=90, check=False)
    write_json_exclusive(DEST / "checkpoint_metadata_receipt.json", {"exit_code": result.returncode,
        "output_sha256": sha256_file(DEST / "checkpoint_metadata.json"), "CPU_only": True, "remote_writes": False})
    if result.returncode:
        raise RuntimeError("CPU checkpoint inspection failed;preserve evidence before further action")
    print((DEST / "checkpoint_metadata.json").read_text(encoding="utf-8"))


def grouped_review(arms):
    groups = ("forces_role_vector_mae", "forces_adsorbate_C_vector_mae", "forces_adsorbate_O_vector_mae",
        "forces_adsorbate_H_vector_mae", "forces_near_Fe_vector_mae", "forces_other_Fe_vector_mae", "forces_replay_vector_mae")
    best = {arm: min(info["development_rounded_native_log"], key=lambda r: r["forces_role_vector_mae"]) for arm, info in arms.items()}
    rows = []
    for group in groups:
        first, second = best["control"][group], best["treatment"][group]
        rows.append({"metric": group, "control": first, "treatment": second, "units": "eV/Angstrom",
            "treatment_minus_control": second-first, "relative_change_percent": 100*(second-first)/first if first else None,
            "direction": "treatment_lower" if second < first else "control_lower" if first < second else "rounded_tie"})
    return {"rows": rows, "best_epochs_from_rounded_native_log": {k: v["epoch"] for k, v in best.items()},
        "group_regressions_are_soft_review_warnings_not_zero_tolerance_failures": True,
        "single_seed_two_epochs_not_statistical_significance": True}


def native_metadata():
    """Inference exports omit trainer state;inspect the retained native checkpoint."""
    metadata = load_json_object(DEST / "checkpoint_metadata.json")
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    program = r'''
import gc,hashlib,json,torch
from pathlib import Path
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
result={}
for arm in ('control','treatment'):
 root=Path(MODELS[arm]['path']).parent
 paths=list(root.rglob('checkpoint.pt'))
 best=list(root.rglob('best_checkpoint.pt'))
 if len(paths)!=1 or len(best)!=1 or digest(best[0])!=MODELS[arm]['sha256']:raise ValueError('native/best checkpoint provenance ambiguous')
 payload=torch.load(paths[0],map_location='cpu',weights_only=False)
 result[arm]={'native_checkpoint_path':str(paths[0]),'native_checkpoint_sha256':digest(paths[0]),
  'inference_export_matches_native_best':True,'native_keys':sorted(payload),
  'epoch':payload.get('epoch'),'step':payload.get('step'),'primary_metric':payload.get('primary_metric'),
  'best_val_metric':payload.get('best_val_metric')}
 del payload;gc.collect()
print(json.dumps({'models':result,'CUDA_initialized':torch.cuda.is_initialized(),'model_run':False},allow_nan=False))
'''
    command = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"],
        "env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 CUDA_VISIBLE_DEVICES='' /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"]
    with (DEST / "native_checkpoint_metadata.json").open("xb") as output, (DEST / "native_checkpoint_metadata.stderr").open("xb") as errors:
        result = subprocess.run(command, input=("MODELS=" + repr(metadata["models"]) + "\n" + program).encode(), stdout=output, stderr=errors, timeout=90, check=False)
    write_json_exclusive(DEST / "native_checkpoint_metadata_receipt.json", {"exit_code": result.returncode,
        "output_sha256": sha256_file(DEST / "native_checkpoint_metadata.json"), "CPU_only": True, "remote_writes": False})
    if result.returncode:
        raise RuntimeError("native trainer-state inspection failed;preserve evidence")
    print((DEST / "native_checkpoint_metadata.json").read_text(encoding="utf-8"))


def frozen_validation_rows():
    """Verify labels/split integrity without predictions or test-driven selection."""
    manifest_path = POOL / "training_manifest.json"
    original_request = load_json_object(TRAINING / "package/treatment/training_request.json")
    bound = next(a["sha256"] for a in original_request["artifacts"] if a["path"] == "training_manifest.json")
    if sha256_file(manifest_path) != bound:
        raise ValueError("frozen training split changed")
    manifest = load_manifest(manifest_path)
    test = manifest["splits"]["heldout"]
    train_dev = manifest["splits"]["train"] + manifest["splits"]["development"]
    if len(test) != 46 or Counter(r["source_name"] for r in test) != {"09_C": 23, "10_A": 23}:
        raise ValueError("heldout scope changed")
    if {r["calculation_group"] for r in test} & {r["calculation_group"] for r in train_dev}:
        raise ValueError("whole-job heldout leakage")
    if {r["structure_equivalence_sha256"] for r in test} & {r["structure_equivalence_sha256"] for r in train_dev}:
        raise ValueError("equivalent-geometry heldout leakage")
    if len(manifest["quarantined_observed_heldout"]) != 16:
        raise ValueError("observed heldout quarantine changed")
    for row in test:
        validate_label_row(POOL, row)
    return manifest_path, bound, test, load_json_object(POOL / "verification_receipt.json")


def prepare():
    metadata_receipt = load_json_object(DEST / "checkpoint_metadata_receipt.json")
    if metadata_receipt["exit_code"] or metadata_receipt["output_sha256"] != sha256_file(DEST / "checkpoint_metadata.json"):
        raise ValueError("unverified checkpoint metadata")
    metadata = load_json_object(DEST / "checkpoint_metadata.json")
    native_receipt = load_json_object(DEST / "native_checkpoint_metadata_receipt.json")
    if native_receipt["exit_code"] or native_receipt["output_sha256"] != sha256_file(DEST / "native_checkpoint_metadata.json"):
        raise ValueError("unverified native checkpoint state")
    native = load_json_object(DEST / "native_checkpoint_metadata.json")
    exported_receipt = load_json_object(DEST / "exported_checkpoint_metrics_receipt.json")
    if exported_receipt["exit_code"] or exported_receipt["output_sha256"] != sha256_file(DEST / "exported_checkpoint_metrics.json"):
        raise ValueError("unverified exported checkpoint metrics")
    exported = load_json_object(DEST / "exported_checkpoint_metrics.json")
    if exported["CUDA_initialized"] or exported["model_run"]:
        raise ValueError("checkpoint metrics must be read without model execution")
    if metadata["CUDA_initialized"] or metadata["model_inference_or_training"]:
        raise ValueError("this review must not run a model")
    execution = load_json_object(TRAINING / "verification_receipt.json")
    if execution["status"] != "BOTH_CORRECTED_CUDA_TRAINING_ARMS_COMPLETED":
        raise ValueError("corrected training evidence missing")
    review = grouped_review(execution["arms"])
    exact_metrics = {}
    for name in ("control", "treatment"):
        model = metadata["models"][name]
        if model["sha256"] != execution["candidates"][name]["sha256"] or model["configured_primary_metric"] != "forces_role_vector_mae":
            raise ValueError("checkpoint or development selection metric mismatch")
        trainer_state = native["models"][name]
        if trainer_state["epoch"] != 2 or trainer_state["step"] != 496 or not trainer_state["inference_export_matches_native_best"]:
            raise ValueError("native terminal trainer-state provenance mismatch")
        if exported["models"][name]["sha256"] != model["sha256"]:
            raise ValueError("exported metric/checkpoint binding mismatch")
        exact_metrics[name] = exported["models"][name]["val_metrics"]
        for metric in review["rows"]:
            value = exact_metrics[name][metric["metric"]]["metric"]
            if abs(value-metric[name]) > .000050001:
                raise ValueError("native rounded log does not match exported checkpoint metric")
    for row in review["rows"]:
        first, second = [exact_metrics[name][row["metric"]]["metric"] for name in ("control", "treatment")]
        row.update(control=first, treatment=second, treatment_minus_control=second-first,
                   relative_change_percent=100*(second-first)/first if first else None)
    selected = min(("control", "treatment"), key=lambda k: exact_metrics[k]["forces_role_vector_mae"]["metric"])
    review.update(selected_arm=selected, selection_uses_development_only=True, checkpoint_promoted=False,
        exact_best_development_metric={k: exact_metrics[k]["forces_role_vector_mae"]["metric"] for k in ("control", "treatment")},
        metric_source="inference_export.val_metrics;not the pre-validation resume checkpoint.best_val_metric",
        native_resume_metric_lags_last_validation=True,
        selection_rationale="Common predeclared development metric;C/O versus H/Fe/replay tradeoffs reviewed.No heldout selection.")

    manifest_path, bound, test, isolation = frozen_validation_rows()
    proposal = {"document_kind": "adsorption_independent_validation_proposal", "schema_version": 1,
        "status": "PREPARED_FOR_REVIEW_NOT_EXECUTABLE_NOT_AUTHORIZED", "selected_arm": selected,
        "models": {"baseline": metadata["models"]["baseline"], "candidate": metadata["models"][selected]},
        "selection_frozen_before_heldout_prediction": True, "selection_review_sha256": "",
        "training_manifest": {"path": manifest_path.relative_to(ROOT).as_posix(), "sha256": bound},
        "heldout_count": 46, "whole_job_counts": dict(Counter(r["source_name"] for r in test)),
        "samples": [{**row, "structure_path": (POOL / row["structure_path"]).relative_to(ROOT).as_posix(),
                     "label_source": {**row["label_source"], "path": (POOL / row["label_source"]["path"]).relative_to(ROOT).as_posix()}} for row in test],
        "observed_16_excluded_from_primary_validation": True, "source_test_roles_unchanged": True,
        "known_screening_of_parent_jobs_disclosed": True, "baseline_pretraining_overlap_unknown": True,
        "required_outputs": ["paired per-structure baseline/candidate force errors", "C/O/H/near_Fe/other_Fe and per-job/per-stage summaries",
            "vector MAE,RMSE,max/tail errors and force directions", "near-DFT-minimum residual forces", "worst carbon/changed-connectivity cases"],
        "proposed_prediction_count": 92, "proposed_new_VASP_jobs": 0,
        "scope": "exact fixed structures force inference only;no relaxation,training or energy ranking",
        "review_policy": "Group regressions are warnings with absolute scale and job coverage,not zero-tolerance failure.No test-driven model reselection.",
        "scientific_boundaries": {"GPU_execution_authorized": False, "model_promotion": False,
            "independent_chemical_extrapolation_claim": False, "C2H3_training_coverage": False,
            "TS_domain_claim": False, "measured_VASP_acceleration": False},
        "remaining_before_GPU": ["explicit scope/budget approval", "executable package/runner and backend authorization binding", "live GPU and native inference preflight"],
        "source_pool_integrity_review": isolation}
    write_json_exclusive(DEST / "grouped_development_review.json", review)
    proposal["selection_review_sha256"] = sha256_file(DEST / "grouped_development_review.json")
    write_json_exclusive(DEST / "independent_validation_proposal.json", proposal)
    write_json_exclusive(DEST / "review_receipt.json", {"status": "DEVELOPMENT_SELECTION_FROZEN_VALIDATION_PROPOSED_ONLY",
        "selected_arm": selected, "candidate_sha256": metadata["models"][selected]["sha256"],
        "review_sha256": proposal["selection_review_sha256"], "proposal_sha256": sha256_file(DEST / "independent_validation_proposal.json"),
        "training_manifest_sha256": bound, "new_model_predictions": 0, "new_VASP": 0, "heldout_predictions": 0,
        "source_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in
            [Path(__file__), TRAINING / "verification_receipt.json", DEST / "checkpoint_metadata.json",
             DEST / "native_checkpoint_metadata.json", DEST / "exported_checkpoint_metrics.json", manifest_path]]})
    print(json.dumps({"selected_arm": selected, "checkpoint": metadata["models"][selected], "proposal_sha256": sha256_file(DEST / "independent_validation_proposal.json"),
        "review": review, "new_GPU_or_VASP_calculations": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("checkpoint-metadata", "native-metadata", "prepare"))
    args = parser.parse_args()
    {"checkpoint-metadata": checkpoint_metadata, "native-metadata": native_metadata, "prepare": prepare}[args.action]()
