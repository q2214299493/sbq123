#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from ase.calculators.singlepoint import SinglePointCalculator
from ase.db import connect
from ase.io import read

try:
    from scripts.artifact_io import load_json_object, sha256_file
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from artifact_io import load_json_object, sha256_file


def _manifest(path: Path) -> dict[str, Any]:
    payload = load_json_object(path)
    if payload.get("document_kind") != "aqcat25_ts_force_only_training_manifest":
        raise ValueError("invalid force-only training manifest")
    if payload.get("training_target") != "forces_only" or payload.get("energy_loss_coefficient") != 0.0:
        raise ValueError("TS active learning must use force-only fine-tuning")
    if payload.get("restrictions", {}).get("reportable_final_energy") is not False:
        raise ValueError("fine-tuning output must remain non-reportable")
    return payload


def build_database(manifest_path: Path, output: Path, split: str = "train") -> int:
    payload = _manifest(manifest_path)
    if output.exists():
        raise FileExistsError(f"training database already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    database = connect(output)
    count = 0
    key = "training_samples" if split == "train" else "validation_samples"
    samples = payload.get(key)
    if not isinstance(samples, list):
        raise ValueError(f"training manifest has no {key}")
    for label in samples:
        structure = manifest_path.parent / label["structure_path"]
        if sha256_file(structure) != label["structure_sha256"]:
            raise ValueError(f"training structure hash mismatch: {structure}")
        atoms = read(structure, format="vasp")
        forces = np.asarray(label["forces_eV_per_A"], dtype=float)
        if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
            raise ValueError(f"invalid VASP force-label shape: {forces.shape}")
        energy = float(label["energy_eV_force_label_only"])
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
        database.write(
            atoms,
            data={
                "sid": str(label["sample_id"]),
                "fid": 0,
                "is_spin_off": False,
                "is_low_fi": False,
                "adsorption_energy": energy,
                "source_result_class": label["source_result_class"],
                "source_outcar_sha256": label.get("source_outcar_sha256", label.get("source_labels_sha256")),
                "sample_role": label["sample_role"],
                "reportable_final_energy": False,
            },
        )
        count += 1
    if count == 0:
        raise ValueError("training manifest has no labels")
    return count


def prepare_config(template: Path, dataset: Path, validation_dataset: Path, output: Path, epochs: int) -> None:
    payload = yaml.safe_load(template.read_text(encoding="utf-8"))
    training = payload["dataset"]["train"]
    training["format"] = "ase_db"
    training["src"] = str(dataset.resolve())
    validation = dict(training)
    validation["src"] = str(validation_dataset.resolve())
    payload["dataset"]["val"] = validation
    payload["optim"]["max_epochs"] = int(epochs)
    payload["optim"]["load_best"] = True
    if isinstance(payload["optim"].get("scheduler_params"), dict):
        payload["optim"]["scheduler_params"]["epochs"] = int(epochs)
    output.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AQCat25 TS force-only training data from accepted VASP labels.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-db")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--split", choices=("train", "validation"), default="train")
    config = commands.add_parser("prepare-config")
    config.add_argument("--template", type=Path, required=True)
    config.add_argument("--dataset", type=Path, required=True)
    config.add_argument("--validation-dataset", type=Path, required=True)
    config.add_argument("--output", type=Path, required=True)
    config.add_argument("--epochs", type=int, required=True)
    args = parser.parse_args()
    if args.command == "build-db":
        print(build_database(args.manifest, args.output, args.split))
    else:
        prepare_config(args.template, args.dataset, args.validation_dataset, args.output, args.epochs)


if __name__ == "__main__":
    main()
