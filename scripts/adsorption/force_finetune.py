"""Bounded adsorption force-label adapter; no TS acceptance or submission authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml
from ase.calculators.singlepoint import SinglePointCalculator
from ase.db import connect
from ase.io import read


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def local_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact path escapes package")
    return path


def validate_label_row(root: Path, row: dict) -> None:
    structure = local_path(root, row["structure_path"])
    if digest(structure) != row["structure_sha256"]:
        raise ValueError("structure hash mismatch")
    atoms = read(structure, format="vasp")
    if atoms.get_chemical_symbols() != row["symbols"]:
        raise ValueError("atom order mismatch")
    fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    if fixed != row["fixed_atom_indices_0based"] or fixed != list(range(18)):
        raise ValueError("fixed mask mismatch")
    forces = np.asarray(row["forces_eV_per_A"], dtype=float)
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
        raise ValueError("invalid force labels")
    if not np.isfinite(row["energy_eV_force_label_only"]):
        raise ValueError("nonfinite label metadata energy")
    if not row["electronic_converged"] or not row["geometry_review_pass"]:
        raise ValueError("unreviewed force label")
    source = row["label_source"]
    source_path = local_path(root, source["path"])
    if digest(source_path) != source["sha256"]:
        raise ValueError("label source hash mismatch")
    labels = json.loads(source_path.read_text(encoding="utf-8"))
    original = next((s for s in labels["samples"] if s["sample_id"] == source["sample_id"]), None)
    if original is None or original["forces_eV_per_A"] != row["forces_eV_per_A"]:
        raise ValueError("force labels differ from source")
    if (original["structure_sha256"] != row["structure_sha256"]
            or original["symbols"] != row["symbols"]
            or original["source_OUTCAR_sha256"] != row["source_OUTCAR_sha256"]):
        raise ValueError("label geometry/order/OUTCAR differs from source")
    energy = original.get("toten_eV_force_label_only", original.get("final_toten_eV"))
    if energy != row["energy_eV_force_label_only"]:
        raise ValueError("energy metadata differs from source")


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("document_kind") != "aqcat25_adsorption_force_training_manifest":
        raise ValueError("not an adsorption-specific force manifest")
    if payload.get("training_target") != "forces_only" or payload.get("energy_loss_coefficient") != 0:
        raise ValueError("this candidate package supports force-only adaptation")
    if payload.get("reportable_final_energy") is not False:
        raise ValueError("trajectory energies must remain non-reportable")
    seen_ids, jobs, structures = set(), {}, {}
    for split in ("train", "development", "heldout"):
        rows = payload["splits"][split]
        if not rows:
            raise ValueError("empty split: " + split)
        for row in rows:
            sid = row["sample_id"]
            if sid in seen_ids:
                raise ValueError("duplicate sample id")
            seen_ids.add(sid)
            old = jobs.setdefault(row["calculation_group"], split)
            if old != split:
                raise ValueError("whole-job split leakage")
            old = structures.setdefault(row["structure_equivalence_sha256"], split)
            if old != split:
                raise ValueError("strict equivalent geometry split leakage")
            validate_label_row(path.parent, row)
    return payload


def verify_request(path: Path) -> dict:
    request = json.loads(path.read_text(encoding="utf-8"))
    if request.get("document_kind") != "aqcat25_adsorption_small_finetune_request":
        raise ValueError("wrong request kind")
    for item in request["artifacts"]:
        artifact = local_path(path.parent, item["path"])
        if digest(artifact) != item["sha256"]:
            raise ValueError("request artifact binding failed: " + item["path"])
    manifest = load_manifest(local_path(path.parent, request["manifest_path"]))
    counts = {key: len(rows) for key, rows in manifest["splits"].items()}
    if request["split_counts"] != counts:
        raise ValueError("request count mismatch")
    config = yaml.safe_load(local_path(path.parent, request["config_path"]).read_text())
    if config["optim"]["max_epochs"] != request["training_limits"]["epochs"]:
        raise ValueError("epoch limit mismatch")
    if config["optim"]["lr_initial"] != request["training_limits"]["learning_rate"]:
        raise ValueError("learning rate mismatch")
    loss = {name: values for entry in config["loss_functions"] for name, values in entry.items()}
    if loss["energy"]["coefficient"] != 0 or loss["forces"]["coefficient"] != 1:
        raise ValueError("force-only loss changed")
    # Only development data may choose epochs. Heldout has a separate database.
    remote = request["remote_package_root"]
    if config["dataset"]["train"]["src"] != remote + "/train.db" or config["dataset"]["val"]["src"] != remote + "/development.db":
        raise ValueError("training config split mismatch")
    for split in ("train", "val"):
        dataset = config["dataset"][split]
        if dataset.get("atoms_transform_args", {}).get("skip_always") is not True:
            raise ValueError("training must retain inference-equivalent zero tags")
    for option in ("train_on_free_atoms", "eval_on_free_atoms"):
        if config["outputs"]["forces"][option] is not True:
            raise ValueError("fixed atoms must be excluded from force objective")
    return {"status": "LOCAL_PACKAGE_VALID", "counts": counts,
            "training_authorized": request["training_authorized"], "model_run": False}


def build_database(manifest: Path, output: Path, split: str) -> int:
    payload = load_manifest(manifest)
    if split not in payload["splits"]:
        raise ValueError("unknown split")
    if output.exists():
        raise FileExistsError(output)
    database = connect(output)
    with database:
        for row in payload["splits"][split]:
            atoms = read(local_path(manifest.parent, row["structure_path"]), format="vasp")
            # POSCAR inference uses zero tags. Do not silently switch the domain
            # bit by the ASE-dataset default apply_one_tags transformation.
            atoms.set_tags(np.zeros(len(atoms), dtype=int))
            energy = row["energy_eV_force_label_only"]
            atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=row["forces_eV_per_A"])
            database.write(atoms, data={"sid": row["sample_id"], "fid": row["ionic_step"],
                "is_spin_off": False, "is_low_fi": False, "adsorption_energy": energy,
                "sample_role": row["sample_role"], "calculation_group": row["calculation_group"],
                "reportable_final_energy": False, "source_outcar_sha256": row["source_OUTCAR_sha256"]})
    return len(payload["splits"][split])


def force_metrics(reference: np.ndarray, predicted: np.ndarray, symbols: list[str], fixed: list[int]) -> dict:
    reference, predicted = np.asarray(reference), np.asarray(predicted)
    if reference.shape != predicted.shape or reference.shape != (len(symbols), 3):
        raise ValueError("prediction shape mismatch")
    if not np.isfinite(reference).all() or not np.isfinite(predicted).all():
        raise ValueError("nonfinite force prediction")
    free = [i for i in range(len(symbols)) if i not in fixed]
    groups = {"movable": free, "adsorbate": [i for i in free if symbols[i] != "Fe"]}
    groups.update({s: [i for i in free if symbols[i] == s] for s in ("Fe", "C", "O", "H")})
    result = {}
    for name, indices in groups.items():
        if not indices:
            result[name] = {"atom_count": 0, "vector_rmse_eV_A": None}
            continue
        delta = predicted[indices] - reference[indices]
        norm = np.linalg.norm(delta, axis=1)
        rnorm, pnorm = np.linalg.norm(reference[indices], axis=1), np.linalg.norm(predicted[indices], axis=1)
        directional = (rnorm > 1e-8) & (pnorm > 1e-8)
        cos = np.sum(reference[indices] * predicted[indices], axis=1)[directional] / (rnorm*pnorm)[directional]
        result[name] = {"atom_count": len(indices), "component_mae_eV_A": float(np.abs(delta).mean()),
                        "vector_rmse_eV_A": float(np.sqrt(np.mean(norm**2))),
                        "vector_max_eV_A": float(norm.max()),
                        "mean_cosine_nonzero_forces": float(cos.mean()) if len(cos) else None}
    return result


def warm_start(request_path: Path, authorization: Path, output: Path) -> None:
    """Authorized runtime only: reset trainer state, never the baseline weights."""
    verify_request(request_path)
    request = json.loads(request_path.read_text())
    approval = json.loads(authorization.read_text())
    if (approval.get("request_sha256") != digest(request_path) or approval.get("user_authorized") is not True
            or approval.get("action") != "RUN_GPU_ADSORPTION_SMALL_FINETUNE"):
        raise ValueError("missing or stale explicit training authorization")
    checkpoint = Path(request["base_checkpoint"]["path"])
    if digest(checkpoint) != request["base_checkpoint"]["sha256"]:
        raise ValueError("baseline checkpoint changed")
    if output.exists():
        raise FileExistsError(output)
    import torch

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    config = yaml.safe_load(local_path(request_path.parent, request["config_path"]).read_text())
    if payload["config"]["model"] != config["model"]:
        raise ValueError("training architecture differs from baseline checkpoint")
    # --checkpoint otherwise resumes pretraining epoch/optimizer/scheduler,
    # defeating the requested four fresh epochs and low learning rate.
    for key in ("optimizer", "scheduler", "scaler", "best_val_metric", "primary_metric"):
        payload.pop(key, None)
    payload.update(epoch=0, step=0, amp=False)
    torch.save(payload, output)


def evaluate_pair(request_path: Path, candidate: Path, output: Path) -> None:
    """Exact fixed-structure diagnostics; no relaxation/promotion/energy claim."""
    verify_request(request_path)
    request = json.loads(request_path.read_text())
    if output.exists():
        raise FileExistsError(output)
    from fairchem.core.common.relaxation.ase_utils import patched_calc
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401

    manifest = load_manifest(local_path(request_path.parent, request["manifest_path"]))
    baseline = Path(request["base_checkpoint"]["path"])
    if digest(baseline) != request["base_checkpoint"]["sha256"]:
        raise ValueError("baseline changed")
    # Deliberately excludes heldout. Freeze/review candidate before a separate
    # independent evaluation request; no post-hoc epoch selection on heldout.
    rows = manifest["splits"]["development"]
    models = {}
    for name, checkpoint in (("baseline", baseline), ("candidate", candidate)):
        calc = patched_calc(checkpoint_path=str(checkpoint), is_spin_off=False, is_low_fi=False)
        predictions, groups = [], {}
        for row in rows:
            atoms = read(local_path(request_path.parent, row["structure_path"]), format="vasp")
            atoms.calc = calc
            # Compare the raw forces. ASE otherwise zeroes the fixed-atom
            # reference and prediction, which can hide labeling mistakes.
            predicted = atoms.get_forces(apply_constraint=False)
            metrics = force_metrics(row["forces_eV_per_A"], predicted, row["symbols"], row["fixed_atom_indices_0based"])
            predictions.append({"sample_id": row["sample_id"], "structure_sha256": row["structure_sha256"],
                                "role": row["sample_role"], "groups": metrics})
            category = "retention" if "retention" in row["sample_role"] else "C2"
            for group, values in metrics.items():
                if values["atom_count"]:
                    key = category + "/" + group
                    count, sum_sq = groups.setdefault(key, (0, 0.0))
                    groups[key] = (count + values["atom_count"], sum_sq + values["atom_count"] * values["vector_rmse_eV_A"]**2)
        models[name] = {"checkpoint_sha256": digest(checkpoint), "samples": predictions,
                        "groups": {key: {"atom_count": count, "vector_rmse_eV_A": float(np.sqrt(total/count))}
                                   for key, (count, total) in groups.items()}}
        del calc
        import gc
        import torch
        gc.collect()
        torch.cuda.empty_cache()
    result = {"document_kind": "adsorption_candidate_development_comparison", "models": models,
              "request_sha256": digest(request_path), "heldout_consumed": False,
              "scientific_acceptance": False, "acceleration_proved": False,
              "status": "CANDIDATE_ONLY_REQUIRES_GROUPED_REVIEW"}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--request", type=Path, required=True)
    build = commands.add_parser("build-db")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--split", choices=("train", "development", "heldout"), required=True)
    warm = commands.add_parser("warm-start")
    warm.add_argument("--request", type=Path, required=True)
    warm.add_argument("--authorization", type=Path, required=True)
    warm.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate-development")
    evaluate.add_argument("--request", type=Path, required=True)
    evaluate.add_argument("--candidate", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        print(json.dumps(verify_request(args.request)))
    elif args.command == "build-db":
        print(json.dumps({"split": args.split, "written": build_database(args.manifest, args.output, args.split)}))
    elif args.command == "warm-start":
        warm_start(args.request, args.authorization, args.output)
    else:
        evaluate_pair(args.request, args.candidate, args.output)


if __name__ == "__main__":
    main()
