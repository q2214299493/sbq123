#!/usr/bin/env python3
"""Build a self-contained, authorized MZ73 MatRIS fine-tuning bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_energy_force_finetune import validate_review_package


def _copy_bound(source: Path, target: Path) -> dict[str, str]:
    source = source.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"path": str(target), "sha256": sha256_file(target)}


def _safe_name(sample_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", sample_id).strip("_")


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    local_review_path = args.review_request.resolve()
    context = validate_review_package(local_review_path)
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"remote bundle output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    remote_root = args.remote_root.rstrip("/")
    if not remote_root.startswith("/home/sbq/sbq/"):
        raise ValueError("remote root is outside /home/sbq/sbq")

    code_sources = [
        Path("scripts/__init__.py"),
        Path("scripts/artifact_io.py"),
        Path("scripts/workflow_geometry.py"),
        Path("scripts/matris_energy_force_finetune.py"),
        Path("scripts/matris_finetune_speed_benchmark.py"),
        Path("scripts/matris_training_exclusions.py"),
        Path("scripts/neb_agent/__init__.py"),
        Path("scripts/neb_agent/utils_structure.py"),
    ]
    copied_code: list[dict[str, str]] = []
    for source in code_sources:
        target = output / "code" / source
        binding = _copy_bound(source, target)
        binding["path"] = f"{remote_root}/code/{source.as_posix()}"
        copied_code.append(binding)

    label_targets: dict[str, dict[str, str]] = {}
    all_samples = (
        context["training_samples"]
        + context["adsorption_validation_samples"]
        + context["heldout_validation_samples"]
    )
    for sample in all_samples:
        label_ref = sample["label_source"]
        digest = str(label_ref["sha256"])
        if digest not in label_targets:
            source = Path(str(label_ref["path"])).resolve()
            target = output / "labels" / f"{digest}.json"
            _copy_bound(source, target)
            label_targets[digest] = {
                "path": f"{remote_root}/labels/{target.name}",
                "sha256": digest,
            }

    manifest = load_json_object(context["manifest_path"])
    sample_groups = (
        "training_samples",
        "validation_only_samples",
        "frozen_ts_heldout_validation_samples",
    )
    seen_names: set[str] = set()
    for group in sample_groups:
        rewritten: list[dict[str, Any]] = []
        for source_sample in manifest.get(group, []):
            sample = dict(source_sample)
            sample_id = str(sample["sample_id"])
            name = _safe_name(sample_id)
            if name in seen_names:
                raise ValueError(f"duplicate remote structure name: {sample_id}")
            seen_names.add(name)
            source_structure = Path(str(sample["structure"]["path"])).resolve()
            target_structure = output / "structures" / f"{name}.vasp"
            _copy_bound(source_structure, target_structure)
            structure = dict(sample["structure"])
            structure["path"] = f"{remote_root}/structures/{target_structure.name}"
            sample["structure"] = structure
            sample["label_source"] = label_targets[
                str(sample["label_source"]["sha256"])
            ]
            rewritten.append(sample)
        manifest[group] = rewritten

    exclusion_source = context["exclusion_path"]
    exclusion_target = output / "heldout_training_exclusions.json"
    _copy_bound(exclusion_source, exclusion_target)
    manifest["sources"]["heldout_exclusion_manifest"] = {
        "path": f"{remote_root}/{exclusion_target.name}",
        "sha256": sha256_file(exclusion_target),
    }
    current_sha = manifest["sources"]["current_ts_labels"]["sha256"]
    manifest["sources"]["current_ts_labels"] = label_targets[current_sha]
    manifest["sources"]["prior_ts_labels"] = [
        label_targets[str(row["sha256"])]
        for row in manifest["sources"]["prior_ts_labels"]
    ]
    adsorption = dict(manifest["sources"]["adsorption_replay"])
    adsorption_sha = str(adsorption["labels"]["sha256"])
    adsorption["labels"] = label_targets[adsorption_sha]
    adsorption["structures_root"] = f"{remote_root}/structures"
    manifest["sources"]["adsorption_replay"] = adsorption
    heldout_sha = manifest["sources"]["frozen_ts_heldout_labels"]["sha256"]
    manifest["sources"]["frozen_ts_heldout_labels"] = label_targets[heldout_sha]

    manifest_target = output / "matris_replay_training_manifest.json"
    write_json_atomic(manifest_target, manifest, ensure_ascii=True)

    local_review = context["review"]
    remote_review = dict(local_review)
    remote_review["source_local_review_request"] = {
        "path": str(local_review_path),
        "sha256": sha256_file(local_review_path),
    }
    remote_review["replay_training_manifest"] = {
        "path": f"{remote_root}/{manifest_target.name}",
        "sha256": sha256_file(manifest_target),
    }
    remote_review["heldout_exclusion_manifest"] = {
        "path": f"{remote_root}/{exclusion_target.name}",
        "sha256": sha256_file(exclusion_target),
    }
    remote_review_target = output / "matris_replay_finetune_review_request.json"
    write_json_atomic(remote_review_target, remote_review, ensure_ascii=True)

    authorization_target = output / "execution_authorization.json"
    authorization = {
        "schema_version": 1,
        "document_kind": "matris_energy_force_finetune_execution_authorization",
        "status": "authorized_for_one_formal_checkpoint_candidate_training",
        "execution_authorized": True,
        "user_authorization": {
            "text": args.user_authorization_text,
            "scope": args.authorization_scope,
        },
        "source_local_review_request": {
            "path": str(local_review_path),
            "sha256": sha256_file(local_review_path),
        },
        "review_request": {
            "path": f"{remote_root}/{remote_review_target.name}",
            "sha256": sha256_file(remote_review_target),
        },
        "base_checkpoint": {
            "path": args.base_checkpoint,
            "sha256": local_review["base_checkpoint_sha256"],
        },
        "base_checkpoint_sha256": local_review["base_checkpoint_sha256"],
        "training_hyperparameters": {
            "epochs": args.epochs,
            "force_weight": args.force_weight,
            "energy_weight": args.energy_weight,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "gradient_clip_norm": args.gradient_clip_norm,
            "trainable_scope": args.trainable_scope,
            "seed": args.seed,
        },
        "allowed_output": "one non-promoted versioned checkpoint candidate and review metrics",
        "checkpoint_promotion_authorized": False,
        "complete_path_rerun_authorized": False,
        "automatic_retry_authorized": False,
    }
    write_json_atomic(authorization_target, authorization, ensure_ascii=True)

    job_target = output / "run_finetune.slurm"
    job = f"""#!/bin/bash
#SBATCH --job-name=matris-ef-ft
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=01:30:00

set -uo pipefail

ROOT={remote_root}
PYTHON_BIN=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python
MATRIS_SOURCE=/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS
CHECKPOINT={args.base_checkpoint}
REVIEW=$ROOT/{remote_review_target.name}
AUTH=$ROOT/{authorization_target.name}
RUNNER=$ROOT/code/scripts/matris_energy_force_finetune.py
OUTPUT=$ROOT/results/job_$SLURM_JOB_ID

for path in "$ROOT" "$OUTPUT" "$PYTHON_BIN" "$MATRIS_SOURCE" "$CHECKPOINT" "$REVIEW" "$AUTH" "$RUNNER"; do
  case "$path" in /home/sbq/sbq/*) ;; *) echo "path outside boundary: $path" >&2; exit 2 ;; esac
done

mkdir -p "$OUTPUT"
export PYTHONPATH="$ROOT/code:$MATRIS_SOURCE:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor${{PYTHONPATH:+:$PYTHONPATH}}"
export XDG_CACHE_HOME=/home/sbq/sbq/aqcat25/cache/xdg
export TORCH_HOME=/home/sbq/sbq/aqcat25/cache/torch
export HF_HOME=/home/sbq/sbq/aqcat25/cache/huggingface
export TMPDIR=/home/sbq/sbq/aqcat25/tmp
export WITH_PYG_LIB=0
export TORCH_SPARSE_USE_PYG_LIB=0
export TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
exit_code=0
echo "{sha256_file(remote_review_target)}  $REVIEW" | sha256sum -c - || exit_code=$?
echo "{sha256_file(authorization_target)}  $AUTH" | sha256sum -c - || exit_code=$?
echo "{local_review['base_checkpoint_sha256']}  $CHECKPOINT" | sha256sum -c - || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  "$PYTHON_BIN" "$RUNNER" train \
    --review-request "$REVIEW" \
    --authorization "$AUTH" \
    --checkpoint "$CHECKPOINT" \
    --output "$OUTPUT" \
    --device cuda \
    --epochs {args.epochs} \
    --force-weight {args.force_weight} \
    --energy-weight {args.energy_weight} \
    --learning-rate {args.learning_rate} \
    --weight-decay {args.weight_decay} \
    --gradient-clip-norm {args.gradient_clip_norm} \
    --trainable-scope {args.trainable_scope} \
    --seed {args.seed} || exit_code=$?
fi

STARTED_UTC="$started_utc" EXIT_CODE="$exit_code" OUTPUT="$OUTPUT" \
AUTH_SHA="{sha256_file(authorization_target)}" "$PYTHON_BIN" - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["OUTPUT"]) / "producer_exit_record.json"
payload = {{
    "gpu_job_id": os.environ.get("SLURM_JOB_ID"),
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": int(os.environ["EXIT_CODE"]),
    "status": "success" if int(os.environ["EXIT_CODE"]) == 0 else "failed",
    "authorization_sha256": os.environ["AUTH_SHA"],
    "checkpoint_promotion": False,
    "complete_path_rerun": False,
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}}
path.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
PY

exit "$exit_code"
"""
    job_target.write_text(job, encoding="utf-8", newline="\n")

    files = [path for path in output.rglob("*") if path.is_file()]
    bundle_manifest = {
        "schema_version": 1,
        "document_kind": "matris_energy_force_remote_execution_bundle",
        "status": "prepared_authorized_not_yet_submitted",
        "remote_root": remote_root,
        "source_local_review_request": {
            "path": str(local_review_path),
            "sha256": sha256_file(local_review_path),
        },
        "remote_review_request_sha256": sha256_file(remote_review_target),
        "authorization_sha256": sha256_file(authorization_target),
        "base_checkpoint": authorization["base_checkpoint"],
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in sorted(files)
        ],
        "code": copied_code,
        "submission_performed": False,
    }
    manifest_output = output / "remote_bundle_manifest.json"
    write_json_atomic(manifest_output, bundle_manifest, ensure_ascii=True)
    return {
        "status": "prepared_authorized_not_yet_submitted",
        "bundle_manifest": {
            "path": str(manifest_output),
            "sha256": sha256_file(manifest_output),
        },
        "remote_root": remote_root,
        "remote_review_request_sha256": sha256_file(remote_review_target),
        "authorization_sha256": sha256_file(authorization_target),
        "file_count": len(files) + 1,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--base-checkpoint", required=True)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--force-weight", type=float, required=True)
    parser.add_argument("--energy-weight", type=float, required=True)
    parser.add_argument("--learning-rate", type=float, required=True)
    parser.add_argument("--weight-decay", type=float, required=True)
    parser.add_argument("--gradient-clip-norm", type=float, required=True)
    parser.add_argument("--trainable-scope", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--user-authorization-text", required=True)
    parser.add_argument(
        "--authorization-scope",
        default="one formal MatRIS energy-force replay fine-tuning run",
    )
    return parser


if __name__ == "__main__":
    print(json.dumps(prepare(build_parser().parse_args()), ensure_ascii=False))
