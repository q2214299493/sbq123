#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
    from scripts.aqcat25_ts_schema import load_document
except ModuleNotFoundError:  # MZ73 deploys these files in one directory.
    from artifact_io import load_json_object, sha256_file, write_json_atomic
    from aqcat25_ts_schema import load_document


def _relative_file(root: Path, value: str, *, label: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe POSIX relative path")
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*relative.parts).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"{label} escapes its root")
    if not candidate.is_file():
        raise FileNotFoundError(f"{label} does not exist: {candidate}")
    return candidate


def validate_batch(batch_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    batch = load_json_object(batch_path)
    if batch.get("schema_version") != 1 or batch.get("document_kind") != (
        "aqcat25_ts_path_force_prediction_batch_request"
    ):
        raise ValueError("invalid AQCat25 path force-prediction batch request")
    if batch.get("automatic_submission") is not False:
        raise ValueError("batch must preserve automatic_submission=false")
    checkpoint = batch.get("checkpoint")
    if not isinstance(checkpoint, dict) or not checkpoint.get("sha256"):
        raise ValueError("batch checkpoint binding is missing")
    rows = batch.get("predictions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("batch has no prediction requests")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("batch prediction row must be an object")
        image = str(row.get("image", ""))
        if not image or image in seen:
            raise ValueError("batch image IDs must be non-empty and unique")
        seen.add(image)
        request_path = _relative_file(
            batch_path.parent,
            str(row.get("request", "")),
            label=f"image {image} request",
        )
        if sha256_file(request_path) != row.get("request_sha256"):
            raise ValueError(f"image {image} request hash mismatch")
        request = load_document(
            request_path, expected_kind="aqcat25_ts_force_prediction_request"
        )
        if request["checkpoint"]["sha256"] != checkpoint["sha256"]:
            raise ValueError(f"image {image} checkpoint hash mismatch")
        structure_path = _relative_file(
            request_path.parent,
            str(request["structure"]["path"]),
            label=f"image {image} structure",
        )
        structure_sha = sha256_file(structure_path)
        if structure_sha != request["structure"]["sha256"] or structure_sha != row.get(
            "structure_sha256"
        ):
            raise ValueError(f"image {image} structure hash mismatch")
        validated.append(
            {
                "image": image,
                "request_path": request_path,
                "request_sha256": row["request_sha256"],
                "structure_sha256": structure_sha,
                "checkpoint_sha256": checkpoint["sha256"],
            }
        )
    return batch, validated


def run_batch(batch_path: Path, runner: Path, output: Path) -> dict[str, Any]:
    batch, rows = validate_batch(batch_path)
    if not runner.is_file():
        raise FileNotFoundError(f"single-structure prediction runner is missing: {runner}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    predictions = []
    for row in rows:
        image_dir = output / f"image_{row['image']}"
        image_dir.mkdir()
        prediction_path = image_dir / "prediction.json"
        subprocess.run(
            [
                sys.executable,
                str(runner),
                "--request",
                str(row["request_path"]),
                "--output",
                str(prediction_path),
            ],
            check=True,
        )
        prediction = load_document(
            prediction_path, expected_kind="aqcat25_ts_force_prediction"
        )
        if prediction["request_sha256"] != row["request_sha256"]:
            raise ValueError(f"image {row['image']} result request hash mismatch")
        if prediction["structure_sha256"] != row["structure_sha256"]:
            raise ValueError(f"image {row['image']} result structure hash mismatch")
        if prediction["checkpoint_sha256"] != row["checkpoint_sha256"]:
            raise ValueError(f"image {row['image']} result checkpoint hash mismatch")
        predictions.append(
            {
                "image": row["image"],
                "prediction": prediction_path.relative_to(output).as_posix(),
                "prediction_sha256": sha256_file(prediction_path),
            }
        )
    result = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_path_force_prediction_set",
        "source_request_sha256": sha256_file(batch_path),
        "checkpoint_sha256": batch["checkpoint"]["sha256"],
        "predictions": predictions,
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    write_json_atomic(output / "path_force_prediction_set.json", result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate or sequentially run one hash-bound AQCat25 TS force-prediction batch."
    )
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    batch, rows = validate_batch(args.batch)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "batch_sha256": sha256_file(args.batch),
                    "checkpoint_sha256": batch["checkpoint"]["sha256"],
                    "images": [row["image"] for row in rows],
                },
                indent=2,
            )
        )
        return
    if args.runner is None or args.output is None:
        parser.error("--runner and --output are required unless --validate-only is used")
    print(json.dumps(run_batch(args.batch, args.runner, args.output), indent=2))


if __name__ == "__main__":
    main()
