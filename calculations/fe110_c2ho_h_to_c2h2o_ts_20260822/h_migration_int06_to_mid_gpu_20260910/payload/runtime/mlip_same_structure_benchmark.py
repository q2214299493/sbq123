#!/usr/bin/env python3
"""Prepare, run, and assess a hash-bound same-structure MLIP benchmark."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
try:
    from scripts.artifact_io import sha256_file as sha256_file, load_json_object as load_json
except ModuleNotFoundError:  # Standalone MZ73 bundles include artifact_io.py beside this runner.
    from artifact_io import sha256_file as sha256_file, load_json_object as load_json


TS_SAMPLE_IDS = ("R1", "R2", "S1", "S2", "F1", "F2")
TS_ROLES = {
    "R1": "rising_path",
    "R2": "rising_path",
    "S1": "near_saddle",
    "S2": "near_saddle",
    "F1": "falling_path",
    "F2": "falling_path",
}






def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def composition_key(symbols: Iterable[str]) -> str:
    counts = Counter(symbols)
    return "-".join(f"{symbol}{counts[symbol]}" for symbol in sorted(counts))


def atom_order_sha256(symbols: Iterable[str]) -> str:
    value = "\n".join(symbols) + "\n"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_empty_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"destination is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _force_array(value: Any, atom_count: int, label: str) -> list[list[float]]:
    import numpy as np

    forces = np.asarray(value, dtype=float)
    if forces.shape != (atom_count, 3) or not np.isfinite(forces).all():
        raise ValueError(f"{label} forces must be finite with shape ({atom_count}, 3)")
    return forces.tolist()


def _resolve_source_path(source_root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (source_root / path).resolve()


def _outcar_has_normal_footer(path: Path) -> bool:
    marker = b"General timing and accounting informations for this job:"
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - 1024 * 1024))
        return marker in handle.read()


def extend_benchmark(args: argparse.Namespace) -> None:  # noqa: C901
    """Extend an existing package with reviewed, already-computed VASP labels."""
    import numpy as np
    from ase.constraints import FixAtoms
    from ase.io import read, write

    base_manifest_path = args.base_manifest.resolve()
    base_manifest = load_json(base_manifest_path)
    if base_manifest.get("document_kind") != "mlip_same_structure_benchmark_manifest":
        raise ValueError("invalid base benchmark manifest")
    spec_path = args.spec.resolve()
    spec = load_json(spec_path)
    if spec.get("document_kind") != "mlip_existing_vasp_label_extension_spec":
        raise ValueError("invalid extension specification")
    source_root = args.source_root.resolve()
    destination = args.destination.resolve()
    _require_empty_directory(destination)
    structures_dir = destination / "structures"
    structures_dir.mkdir()

    records = copy.deepcopy(base_manifest["samples"])
    source_files = [base_manifest_path, spec_path]
    sample_ids = {sample["sample_id"] for sample in records}
    for sample in records:
        base_structure = base_manifest_path.parent / sample["structure"]["path"]
        staged_structure = structures_dir / Path(sample["structure"]["path"]).name
        shutil.copy2(base_structure, staged_structure)
        if sha256_file(staged_structure) != sample["structure"]["sha256"]:
            raise ValueError(f"base structure hash mismatch: {sample['sample_id']}")
        sample["structure"]["path"] = staged_structure.relative_to(destination).as_posix()
        if sample["subset"] == "adsorption":
            sample.setdefault("reaction_id", "fe110_adsorption")
            sample.setdefault(
                "energy_group_id", f"fe110_adsorption::{sample['composition_key']}"
            )
            sample.setdefault("label_region", "near_relaxed_adsorption")
        else:
            sample.setdefault("reaction_id", "fe110_c_h_to_ch")
            sample.setdefault("energy_group_id", "fe110_c_h_to_ch::path")
            sample.setdefault("label_region", "path_internal")

    for item in spec["samples"]:
        sample_id = str(item["sample_id"])
        if sample_id in sample_ids:
            raise ValueError(f"duplicate sample id: {sample_id}")
        outcar = _resolve_source_path(source_root, item["outcar"])
        if not outcar.is_file():
            raise FileNotFoundError(outcar)
        expected_outcar_hash = item.get("outcar_sha256")
        actual_outcar_hash = sha256_file(outcar)
        if expected_outcar_hash and actual_outcar_hash != expected_outcar_hash:
            raise ValueError(f"OUTCAR hash mismatch for {sample_id}")
        if bool(item["normal_completion"]) and not _outcar_has_normal_footer(outcar):
            raise ValueError(f"normal VASP footer is missing for {sample_id}")
        if not bool(item["electronically_converged"]):
            raise ValueError(f"electronically unconverged label is ineligible: {sample_id}")

        atoms = read(outcar, index=-1, format="vasp-out")
        atom_count = len(atoms)
        symbols = atoms.get_chemical_symbols()
        fixed = sorted(int(value) for value in item["fixed_atom_indices_zero_based"])
        if not fixed or fixed[0] < 0 or fixed[-1] >= atom_count:
            raise ValueError(f"invalid fixed-atom mask for {sample_id}")
        parsed_fixed = sorted(
            {
                int(index)
                for constraint in atoms.constraints
                if hasattr(constraint, "get_indices")
                for index in constraint.get_indices()
            }
        )
        if parsed_fixed and parsed_fixed != fixed:
            raise ValueError(f"OUTCAR fixed-atom mask mismatch for {sample_id}")
        atoms.set_constraint(FixAtoms(indices=fixed))
        forces = _force_array(atoms.get_forces(), atom_count, f"VASP {sample_id}")
        free_energy = float(atoms.calc.results["free_energy"])
        if not math.isfinite(free_energy):
            raise ValueError(f"non-finite VASP TOTEN for {sample_id}")
        expected_toten = item.get("expected_toten_eV")
        if expected_toten is not None and not math.isclose(
            free_energy, float(expected_toten), abs_tol=1.0e-6, rel_tol=0.0
        ):
            raise ValueError(
                f"VASP TOTEN mismatch for {sample_id}: {free_energy} != {expected_toten}"
            )

        staged_name = f"{sample_id}.vasp"
        staged_structure = structures_dir / staged_name
        write(staged_structure, atoms, format="vasp", direct=True, vasp5=True)
        staged_atoms = read(staged_structure, format="vasp")
        if staged_atoms.get_chemical_symbols() != symbols or not np.allclose(
            staged_atoms.positions, atoms.positions, atol=1.0e-5, rtol=0.0
        ):
            raise RuntimeError(f"staged structure changed for {sample_id}")

        evidence = []
        for value in item.get("validation_evidence", []):
            evidence_path = _resolve_source_path(source_root, value)
            if not evidence_path.is_file():
                raise FileNotFoundError(evidence_path)
            evidence.append(
                {"path": str(evidence_path), "sha256": sha256_file(evidence_path)}
            )
            source_files.append(evidence_path)
        record = {
            "sample_id": sample_id,
            "source_sample_id": str(item.get("source_sample_id", sample_id)),
            "subset": str(item["subset"]),
            "role": str(item["role"]),
            "reaction_id": str(item["reaction_id"]),
            "energy_group_id": str(item["energy_group_id"]),
            "label_region": str(item["label_region"]),
            "composition_key": composition_key(symbols),
            "structure": {
                "path": staged_structure.relative_to(destination).as_posix(),
                "sha256": sha256_file(staged_structure),
                "atom_count": atom_count,
                "atom_order_sha256": atom_order_sha256(symbols),
                "symbols": symbols,
                "source_outcar_sha256": actual_outcar_hash,
                "source_outcar_final_ionic_step": True,
            },
            "fixed_atom_indices_zero_based": fixed,
            "vasp_label": {
                "energy_eV": free_energy,
                "forces_eV_per_A": forces,
                "normal_completion": bool(item["normal_completion"]),
                "electronic_converged": True,
                "ionic_converged": bool(item["ionic_converged"]),
                "energy_class": str(item["energy_class"]),
                "energy_convention": str(item["energy_convention"]),
                "energy_comparison_eligible": bool(
                    item.get("energy_comparison_eligible", True)
                ),
                "validation_evidence": evidence,
            },
        }
        if item.get("aqcat_context"):
            record["aqcat_context"] = item["aqcat_context"]
        records.append(record)
        sample_ids.add(sample_id)
        source_files.append(outcar)

    all_forces = np.asarray(
        [
            value
            for record in records
            for row in record["vasp_label"]["forces_eV_per_A"]
            for value in row
        ],
        dtype=float,
    )
    if not np.isfinite(all_forces).all():
        raise ValueError("extended VASP labels contain non-finite forces")
    subset_counts = dict(Counter(record["subset"] for record in records))
    reaction_counts = dict(Counter(record["reaction_id"] for record in records))
    manifest = copy.deepcopy(base_manifest)
    manifest.update(
        {
            "schema_version": 2,
            "benchmark_id": args.benchmark_id,
            "base_manifest": {
                "path": str(base_manifest_path),
                "sha256": sha256_file(base_manifest_path),
            },
            "sample_count": len(records),
            "subsets": subset_counts,
            "reactions": reaction_counts,
            "relative_energy_scope": (
                "within_energy_group_id_only; identical composition and compatible VASP "
                "branch required; subtract each group minimum"
            ),
            "samples": records,
            "source_files": [
                {"path": str(path.resolve()), "sha256": sha256_file(path)}
                for path in sorted(set(source_files), key=lambda value: str(value.resolve()))
            ],
        }
    )
    manifest["scientific_limits"].update(
        {
            "c2ho_h_internal_path_vasp_labels_available": False,
            "c2ho_h_records_are_converged_reaction_endpoints_only": True,
            "ordinary_neb_and_nsw1_path_energies_are_benchmark_labels_not_final_barriers": True,
        }
    )
    write_json_atomic(destination / "benchmark_manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "extended",
                "destination": str(destination),
                "sample_count": len(records),
                "subsets": subset_counts,
                "reactions": reaction_counts,
                "manifest_sha256": sha256_file(destination / "benchmark_manifest.json"),
            },
            indent=2,
        )
    )


def prepare_benchmark(args: argparse.Namespace) -> None:  # noqa: C901
    import numpy as np
    from ase.io import read

    destination = args.destination.resolve()
    _require_empty_directory(destination)
    structures_dir = destination / "structures"
    structures_dir.mkdir()

    adsorption_root = args.adsorption_root.resolve()
    ts_root = args.ts_root.resolve()
    adsorption_labels_path = adsorption_root / "labels.json"
    adsorption_predictions_path = adsorption_root / "predictions.json"
    adsorption_labels = load_json(adsorption_labels_path)
    adsorption_predictions = load_json(adsorption_predictions_path)
    adsorption_prediction_by_id = {
        row["sample_id"]: row for row in adsorption_predictions["samples"]
    }

    records: list[dict[str, Any]] = []
    source_files: list[Path] = [adsorption_labels_path, adsorption_predictions_path]
    for label in adsorption_labels["samples"]:
        sample_id = str(label["sample_id"])
        source_structure = adsorption_root / "structures" / f"{sample_id}.vasp"
        prediction = adsorption_prediction_by_id.get(sample_id)
        if prediction is None:
            raise ValueError(f"missing AQCat25 adsorption prediction for {sample_id}")
        structure_hash = sha256_file(source_structure)
        if structure_hash != label["structure_sha256"]:
            raise ValueError(f"adsorption structure hash mismatch for {sample_id}")
        if prediction["structure_sha256"] != structure_hash:
            raise ValueError(f"AQCat25 adsorption prediction hash mismatch for {sample_id}")
        atoms = read(source_structure, format="vasp")
        symbols = atoms.get_chemical_symbols()
        if symbols != label["symbols"]:
            raise ValueError(f"adsorption symbol order mismatch for {sample_id}")
        if atom_order_sha256(symbols) != label["atom_order_sha256"]:
            raise ValueError(f"adsorption atom-order hash mismatch for {sample_id}")
        fixed_zero_based = [int(value) - 1 for value in label["fixed_atom_indices_1based"]]
        staged_name = f"adsorption__{sample_id}.vasp"
        staged_structure = structures_dir / staged_name
        shutil.copy2(source_structure, staged_structure)
        if sha256_file(staged_structure) != structure_hash:
            raise RuntimeError(f"staged adsorption structure hash mismatch for {sample_id}")
        atom_count = len(symbols)
        records.append(
            {
                "sample_id": f"adsorption__{sample_id}",
                "source_sample_id": sample_id,
                "subset": "adsorption",
                "role": label["family"],
                "composition_key": composition_key(symbols),
                "structure": {
                    "path": f"structures/{staged_name}",
                    "sha256": structure_hash,
                    "atom_count": atom_count,
                    "atom_order_sha256": label["atom_order_sha256"],
                    "symbols": symbols,
                },
                "fixed_atom_indices_zero_based": fixed_zero_based,
                "vasp_label": {
                    "energy_eV": float(label["final_toten_eV"]),
                    "forces_eV_per_A": _force_array(
                        label["forces_eV_per_A"], atom_count, f"VASP {sample_id}"
                    ),
                    "normal_completion": bool(label["normal_completion"]),
                    "electronic_converged": True,
                    "ionic_converged": bool(label["ionic_converged"]),
                    "energy_class": "compatible_relaxation_toten",
                },
                "existing_aqcat25_prediction": {
                    "checkpoint_sha256": adsorption_predictions["checkpoint_sha256"],
                    "energy_eV": float(prediction["predicted_energy_eV"]),
                    "forces_eV_per_A": _force_array(
                        prediction["forces_eV_per_A"], atom_count, f"AQCat25 {sample_id}"
                    ),
                },
            }
        )
        source_files.append(source_structure)

    ts_label_root = ts_root / "heldout_vasp_force_labels_sigma0p20_20260820"
    ts_prediction_root = (
        ts_root
        / "heldout_aqcat_force_predictions_20260820"
        / "returned_from_mz73_job1278"
    )
    for sample_id in TS_SAMPLE_IDS:
        label_path = ts_label_root / sample_id / "vasp_force_label.json"
        prediction_path = ts_prediction_root / f"image_{sample_id}" / "prediction.json"
        label = load_json(label_path)
        prediction = load_json(prediction_path)
        source_structure = Path(label["structure"]["path"])
        if not source_structure.is_file():
            source_structure = ts_label_root / sample_id / "POSCAR"
        structure_hash = sha256_file(source_structure)
        if structure_hash != label["structure"]["sha256"]:
            raise ValueError(f"TS structure hash mismatch for {sample_id}")
        if prediction["structure_sha256"] != structure_hash:
            raise ValueError(f"AQCat25 TS prediction hash mismatch for {sample_id}")
        atoms = read(source_structure, format="vasp")
        symbols = atoms.get_chemical_symbols()
        if symbols != label["structure"]["symbols"]:
            raise ValueError(f"TS symbol order mismatch for {sample_id}")
        staged_name = f"ts_path__{sample_id}.vasp"
        staged_structure = structures_dir / staged_name
        shutil.copy2(source_structure, staged_structure)
        if sha256_file(staged_structure) != structure_hash:
            raise RuntimeError(f"staged TS structure hash mismatch for {sample_id}")
        atom_count = len(symbols)
        if not label["normal_completion"] or not label["electronically_converged"]:
            raise ValueError(f"TS VASP label is not complete and electronic-converged: {sample_id}")
        records.append(
            {
                "sample_id": f"ts_path__{sample_id}",
                "source_sample_id": sample_id,
                "subset": "ts_path",
                "role": TS_ROLES[sample_id],
                "composition_key": composition_key(symbols),
                "structure": {
                    "path": f"structures/{staged_name}",
                    "sha256": structure_hash,
                    "atom_count": atom_count,
                    "atom_order_sha256": atom_order_sha256(symbols),
                    "symbols": symbols,
                },
                "fixed_atom_indices_zero_based": [
                    int(value) for value in label["fixed_atom_indices_zero_based"]
                ],
                "vasp_label": {
                    "energy_eV": float(label["dft_toten_eV_force_label_only"]),
                    "forces_eV_per_A": _force_array(
                        label["forces_eV_per_A"], atom_count, f"VASP TS {sample_id}"
                    ),
                    "normal_completion": True,
                    "electronic_converged": True,
                    "ionic_converged": False,
                    "energy_class": "force_label_only_not_reportable_final_energy",
                },
                "existing_aqcat25_prediction": {
                    "checkpoint_sha256": prediction["checkpoint_sha256"],
                    "energy_eV": float(prediction["predicted_energy_eV"]),
                    "forces_eV_per_A": _force_array(
                        prediction["forces_eV_per_A"], atom_count, f"AQCat25 TS {sample_id}"
                    ),
                },
            }
        )
        source_files.extend([source_structure, label_path, prediction_path])

    checkpoint_hashes = {
        record["existing_aqcat25_prediction"]["checkpoint_sha256"] for record in records
    }
    if len(checkpoint_hashes) != 1:
        raise ValueError("existing AQCat25 predictions do not use one exact checkpoint")
    all_forces = [
        value
        for record in records
        for row in record["vasp_label"]["forces_eV_per_A"]
        for value in row
    ]
    if not np.isfinite(np.asarray(all_forces)).all():
        raise ValueError("VASP labels contain non-finite forces")
    source_manifest = [
        {"path": str(path.resolve()), "sha256": sha256_file(path)}
        for path in sorted(set(source_files), key=lambda value: str(value.resolve()))
    ]
    manifest = {
        "schema_version": 1,
        "document_kind": "mlip_same_structure_benchmark_manifest",
        "benchmark_id": args.benchmark_id,
        "compatibility_branch": adsorption_labels["compatibility_branch"],
        "sample_count": len(records),
        "subsets": {"adsorption": 13, "ts_path": 6},
        "aqcat25_checkpoint_sha256": next(iter(checkpoint_hashes)),
        "matris_checkpoint_sha256": args.matris_checkpoint_sha256.lower(),
        "force_metric_scope": "movable_atoms_only",
        "relative_energy_scope": (
            "within_subset_and_identical_composition_only; subtract each group minimum"
        ),
        "relaxation_protocol": {
            "eligible_subset": "adsorption",
            "optimizer": "LBFGS",
            "fmax_eV_per_A": 0.05,
            "max_steps": 300,
            "cell_fixed": True,
            "selective_dynamics_preserved": True,
            "technical_success_requires": [
                "optimizer_converged",
                "movable_fmax_at_or_below_target",
                "finite_energy_and_forces",
            ],
            "generic_geometry_sanity_requires": [
                "atom_order_preserved",
                "cell_preserved",
                "fixed_atoms_preserved",
                "minimum_pair_distance_at_least_0.6_A",
                "at_least_one_adsorbate_atom_within_3.0_A_of_Fe",
            ],
        },
        "samples": records,
        "source_files": source_manifest,
        "scientific_limits": {
            "predicted_values_are_not_dft": True,
            "ts_force_label_energies_are_not_reportable_final_energies": True,
            "relaxation_success_is_not_a_global_minimum_claim": True,
        },
    }
    write_json_atomic(destination / "benchmark_manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "prepared",
                "destination": str(destination),
                "sample_count": len(records),
                "manifest_sha256": sha256_file(destination / "benchmark_manifest.json"),
            },
            indent=2,
        )
    )


def _load_calculator(backend: str, checkpoint: Path, device: str):
    if backend == "aqcat25":
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401

        return patched_calc(
            checkpoint_path=str(checkpoint), is_spin_off=False, is_low_fi=False
        )
    if backend == "matris":
        import torch
        from ase import units
        from ase.calculators.calculator import Calculator
        from matris.applications.base import MatRISCalculator
        from matris.model.model import MatRIS

        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        config = dict(state["config"])
        checkpoint_reference_energy = config.get("reference_energy")
        if checkpoint_reference_energy == "fecoh":
            # The public V0.9 loader does not register the provider's FeCOH label.
            # Its initialized AtomRef weight is strictly replaced by the checkpoint
            # state below, so the supported placeholder cannot affect predictions.
            config["reference_energy"] = "demo"
        model = MatRIS(**config)
        model.load_state_dict(state["state_dict"], strict=True)
        model.config["reference_energy"] = checkpoint_reference_energy
        model = model.to(device)
        model.eval()

        class ProvidedCheckpointMatRISCalculator(MatRISCalculator):
            def __init__(self) -> None:
                Calculator.__init__(self)
                self.task = "ef"
                self.device = device
                self.model = model
                self.stress_unit = units.GPa
                self.key = {"atoms_per_graph", "ref_energy", "e", "f"}

        return ProvidedCheckpointMatRISCalculator()
    raise ValueError(f"unsupported backend: {backend}")


def _minimum_pair_distance(atoms) -> float:
    import numpy as np

    distances = np.asarray(atoms.get_all_distances(mic=True), dtype=float)
    distances[np.eye(len(atoms), dtype=bool)] = np.inf
    return float(np.min(distances))


def _nearest_adsorbate_fe_distance(atoms) -> float:
    symbols = atoms.get_chemical_symbols()
    fe_indices = [index for index, symbol in enumerate(symbols) if symbol == "Fe"]
    adsorbate_indices = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    if not fe_indices or not adsorbate_indices:
        return math.inf
    return min(
        float(atoms.get_distance(adsorbate, fe_index, mic=True))
        for adsorbate in adsorbate_indices
        for fe_index in fe_indices
    )


def _finite_prediction(atoms) -> tuple[float, list[list[float]]]:
    import numpy as np

    energy = float(atoms.get_potential_energy())
    forces = np.asarray(atoms.get_forces(), dtype=float)
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all() or not math.isfinite(
        energy
    ):
        raise RuntimeError("calculator returned non-finite energy or forces")
    return energy, forces.tolist()


def run_backend(args: argparse.Namespace) -> None:  # noqa: C901
    import numpy as np
    import torch
    from ase.io import read, write
    from ase.optimize import LBFGS

    manifest_path = args.manifest.resolve()
    manifest = load_json(manifest_path)
    if manifest.get("document_kind") != "mlip_same_structure_benchmark_manifest":
        raise ValueError("invalid benchmark manifest")
    expected_checkpoint_hash = manifest[f"{args.backend}_checkpoint_sha256"]
    checkpoint = args.checkpoint.resolve()
    actual_checkpoint_hash = sha256_file(checkpoint)
    if actual_checkpoint_hash != expected_checkpoint_hash:
        raise ValueError(
            f"{args.backend} checkpoint hash mismatch: {actual_checkpoint_hash} != "
            f"{expected_checkpoint_hash}"
        )
    output = args.output.resolve()
    partial_path = output / "results.partial.json"
    final_path = output / "results.json"
    if output.exists() and any(output.iterdir()) and not args.resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    relaxed_dir = output / "relaxed_structures"
    relaxed_dir.mkdir(exist_ok=True)
    prior: dict[str, Any] | None = load_json(partial_path) if args.resume and partial_path.exists() else None
    completed = {record["sample_id"]: record for record in prior.get("samples", [])} if prior else {}

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    calculator = _load_calculator(args.backend, checkpoint, args.device)
    relaxation_protocol = manifest["relaxation_protocol"]
    started = time.time()
    selected_samples = manifest["samples"]
    if args.sample_id:
        requested = set(args.sample_id)
        selected_samples = [sample for sample in selected_samples if sample["sample_id"] in requested]
        missing = requested - {sample["sample_id"] for sample in selected_samples}
        if missing:
            raise ValueError(f"unknown requested sample ids: {sorted(missing)}")
    elif args.sample_limit:
        selected_samples = selected_samples[: args.sample_limit]
    for sample in selected_samples:
        sample_id = sample["sample_id"]
        if sample_id in completed:
            continue
        structure_path = manifest_path.parent / sample["structure"]["path"]
        record: dict[str, Any] = {
            "sample_id": sample_id,
            "subset": sample["subset"],
            "structure_sha256": sample["structure"]["sha256"],
            "single_point": {"status": "not_run"},
            "relaxation": {"status": "not_applicable"},
        }
        sample_started = time.time()
        try:
            if sha256_file(structure_path) != sample["structure"]["sha256"]:
                raise ValueError("structure hash mismatch")
            atoms = read(structure_path, format="vasp")
            if atom_order_sha256(atoms.get_chemical_symbols()) != sample["structure"][
                "atom_order_sha256"
            ]:
                raise ValueError("atom-order hash mismatch")
            if args.backend == "aqcat25":
                atoms.info["is_spin_off"] = False
                atoms.info["is_low_fi"] = False
                context = sample.get("aqcat_context")
                if context:
                    atoms.info["bonds_TS"] = [
                        [int(left), int(right), str(action)]
                        for left, right, action in context["bonds_TS"]
                    ]
                    atoms.info["indices_ads"] = [
                        int(index) for index in context["indices_ads"]
                    ]
                elif sample["subset"] == "ts_path":
                    non_fe = [
                        index
                        for index, symbol in enumerate(atoms.get_chemical_symbols())
                        if symbol != "Fe"
                    ]
                    if len(non_fe) == 2:
                        atoms.info["bonds_TS"] = [[non_fe[0], non_fe[1], "form"]]
                        atoms.info["indices_ads"] = non_fe
            atoms.calc = calculator
            energy, forces = _finite_prediction(atoms)
            record["single_point"] = {
                "status": "success",
                "energy_eV": energy,
                "forces_eV_per_A": forces,
            }
        except Exception as exc:  # Preserve every failed structure and continue the batch.
            record["single_point"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:2000],
            }

        if (
            not args.skip_relaxation
            and sample["subset"] == relaxation_protocol["eligible_subset"]
        ):
            try:
                atoms = read(structure_path, format="vasp")
                if args.backend == "aqcat25":
                    atoms.info["is_spin_off"] = False
                    atoms.info["is_low_fi"] = False
                atoms.calc = calculator
                symbols_before = atoms.get_chemical_symbols()
                cell_before = np.asarray(atoms.cell.array, dtype=float).copy()
                positions_before = np.asarray(atoms.positions, dtype=float).copy()
                fixed = np.asarray(sample["fixed_atom_indices_zero_based"], dtype=int)
                logfile = output / f"relax_{sample_id}.log"
                optimizer = LBFGS(atoms, logfile=str(logfile))
                converged = bool(
                    optimizer.run(
                        fmax=float(relaxation_protocol["fmax_eV_per_A"]),
                        steps=int(relaxation_protocol["max_steps"]),
                    )
                )
                energy, forces_list = _finite_prediction(atoms)
                forces = np.asarray(forces_list, dtype=float)
                movable = np.ones(len(atoms), dtype=bool)
                movable[fixed] = False
                movable_fmax = (
                    float(np.linalg.norm(forces[movable], axis=1).max())
                    if np.any(movable)
                    else 0.0
                )
                minimum_pair_distance = _minimum_pair_distance(atoms)
                nearest_adsorbate_fe = _nearest_adsorbate_fe_distance(atoms)
                invariants = {
                    "atom_order_preserved": atoms.get_chemical_symbols() == symbols_before,
                    "cell_preserved": bool(
                        np.allclose(atoms.cell.array, cell_before, atol=1e-10, rtol=0.0)
                    ),
                    "fixed_atoms_preserved": bool(
                        np.allclose(
                            atoms.positions[fixed], positions_before[fixed], atol=1e-8, rtol=0.0
                        )
                    ),
                }
                technical_success = bool(
                    converged
                    and movable_fmax <= float(relaxation_protocol["fmax_eV_per_A"]) + 1e-10
                )
                geometry_sanity = bool(
                    all(invariants.values())
                    and minimum_pair_distance >= 0.6
                    and nearest_adsorbate_fe <= 3.0
                )
                relaxed_path = relaxed_dir / f"{sample_id}.vasp"
                write(relaxed_path, atoms, format="vasp", direct=True, vasp5=True)
                record["relaxation"] = {
                    "status": "success" if technical_success else "not_converged",
                    "optimizer": relaxation_protocol["optimizer"],
                    "optimizer_steps": int(optimizer.nsteps),
                    "optimizer_converged": converged,
                    "final_energy_eV": energy,
                    "final_movable_fmax_eV_per_A": movable_fmax,
                    "technical_success": technical_success,
                    "geometry_sanity_pass": geometry_sanity,
                    "usable_success": bool(technical_success and geometry_sanity),
                    "minimum_pair_distance_A": minimum_pair_distance,
                    "nearest_adsorbate_fe_distance_A": nearest_adsorbate_fe,
                    "invariants": invariants,
                    "relaxed_structure": {
                        "path": relaxed_path.relative_to(output).as_posix(),
                        "sha256": sha256_file(relaxed_path),
                    },
                }
            except Exception as exc:  # Preserve every failed relaxation and continue.
                record["relaxation"] = {
                    "status": "failed",
                    "technical_success": False,
                    "geometry_sanity_pass": False,
                    "usable_success": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2000],
                }
        record["elapsed_seconds"] = time.time() - sample_started
        completed[sample_id] = record
        partial = {
            "schema_version": 1,
            "document_kind": "mlip_same_structure_benchmark_result",
            "benchmark_id": manifest["benchmark_id"],
            "backend": args.backend,
            "checkpoint_sha256": actual_checkpoint_hash,
            "device": args.device,
            "backend_version": args.backend_version,
            "manifest_sha256": sha256_file(manifest_path),
            "samples": [completed[key] for key in sorted(completed)],
            "complete": False,
        }
        write_json_atomic(partial_path, partial)
        print(json.dumps({"sample_id": sample_id, "completed": True}), flush=True)

    result = load_json(partial_path)
    result["complete"] = len(result["samples"]) == len(selected_samples)
    result["sample_count"] = len(result["samples"])
    result["elapsed_seconds"] = time.time() - started
    result["gpu_name"] = torch.cuda.get_device_name(0) if args.device == "cuda" else None
    write_json_atomic(final_path, result)
    print(
        json.dumps(
            {
                "status": "complete" if result["complete"] else "partial",
                "backend": args.backend,
                "sample_count": result["sample_count"],
                "result_sha256": sha256_file(final_path),
            },
            indent=2,
        )
    )


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(values):
        end = cursor + 1
        while end < len(values) and values[ordered[end]] == values[ordered[cursor]]:
            end += 1
        average = (cursor + 1 + end) / 2.0
        for position in range(cursor, end):
            ranks[ordered[position]] = average
        cursor = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return math.nan
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else math.nan


def spearman(left: list[float], right: list[float]) -> float:
    return pearson(_rank(left), _rank(right))


def kendall_tau(left: list[float], right: list[float]) -> float:
    concordant = 0
    discordant = 0
    for first in range(len(left)):
        for second in range(first + 1, len(left)):
            product = (left[first] - left[second]) * (right[first] - right[second])
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else math.nan


def force_metrics(
    labels: list[list[list[float]]],
    predictions: list[list[list[float]]],
    movable_indices: list[list[int]],
) -> dict[str, float | int]:
    import numpy as np

    component_errors: list[float] = []
    vector_errors: list[float] = []
    for label, prediction, indices in zip(labels, predictions, movable_indices):
        reference = np.asarray(label, dtype=float)[indices]
        predicted = np.asarray(prediction, dtype=float)[indices]
        if reference.shape != predicted.shape or reference.ndim != 2 or reference.shape[1] != 3:
            raise ValueError("force arrays are incompatible")
        differences = predicted - reference
        component_errors.extend(differences.ravel().tolist())
        vector_errors.extend(np.linalg.norm(differences, axis=1).tolist())
    return {
        "sample_count": len(labels),
        "movable_atom_count": len(vector_errors),
        "force_component_count": len(component_errors),
        "component_mae_eV_per_A": sum(abs(value) for value in component_errors)
        / len(component_errors),
        "component_rmse_eV_per_A": math.sqrt(
            sum(value * value for value in component_errors) / len(component_errors)
        ),
        "vector_rmse_eV_per_A": math.sqrt(
            sum(value * value for value in vector_errors) / len(vector_errors)
        ),
        "vector_p95_eV_per_A": percentile(vector_errors, 0.95),
        "vector_max_eV_per_A": max(vector_errors),
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def assess_benchmark(args: argparse.Namespace) -> None:  # noqa: C901
    import numpy as np

    manifest = load_json(args.manifest)
    results = [load_json(path) for path in args.result]
    backend_results: dict[str, dict[str, Any]] = {}
    for result in results:
        backend = result["backend"]
        if backend in backend_results:
            raise ValueError(f"duplicate backend result: {backend}")
        if result["manifest_sha256"] != sha256_file(args.manifest):
            raise ValueError(f"result manifest hash mismatch for {backend}")
        if not result.get("complete"):
            raise ValueError(f"benchmark result is incomplete for {backend}")
        backend_results[backend] = result
    if set(backend_results) != {"aqcat25", "matris"}:
        raise ValueError("assessment requires exactly AQCat25 and MatRIS results")

    result_by_backend = {
        backend: {row["sample_id"]: row for row in result["samples"]}
        for backend, result in backend_results.items()
    }
    per_sample_rows: list[dict[str, Any]] = []
    force_summary_rows: list[dict[str, Any]] = []
    relaxation_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "schema_version": 1,
        "document_kind": "mlip_same_structure_benchmark_assessment",
        "benchmark_id": manifest["benchmark_id"],
        "manifest_sha256": sha256_file(args.manifest),
        "backends": {},
        "relative_energy_groups": [],
        "scientific_limits": manifest["scientific_limits"],
    }
    scopes: list[tuple[str, str]] = [("all", "all")]
    scopes.extend(("subset", value) for value in sorted({s["subset"] for s in manifest["samples"]}))
    scopes.extend(
        ("reaction", value)
        for value in sorted({s.get("reaction_id", "unassigned") for s in manifest["samples"]})
    )
    for backend in ("aqcat25", "matris"):
        backend_summary: dict[str, Any] = {"force_metrics": {}, "relaxation": {}}
        for scope_type, scope_id in scopes:
            selected = [
                sample
                for sample in manifest["samples"]
                if scope_type == "all"
                or (scope_type == "subset" and sample["subset"] == scope_id)
                or (
                    scope_type == "reaction"
                    and sample.get("reaction_id", "unassigned") == scope_id
                )
            ]
            labels = []
            predictions = []
            movable_indices = []
            failed = []
            for sample in selected:
                result = result_by_backend[backend].get(sample["sample_id"])
                if result is None or result["single_point"]["status"] != "success":
                    failed.append(sample["sample_id"])
                    continue
                fixed = set(sample["fixed_atom_indices_zero_based"])
                movable = [
                    index for index in range(sample["structure"]["atom_count"]) if index not in fixed
                ]
                labels.append(sample["vasp_label"]["forces_eV_per_A"])
                predictions.append(result["single_point"]["forces_eV_per_A"])
                movable_indices.append(movable)
                one = force_metrics([labels[-1]], [predictions[-1]], [movable])
                if scope_type == "all":
                    per_sample_rows.append(
                        {
                            "backend": backend,
                            "sample_id": sample["sample_id"],
                            "subset": sample["subset"],
                            "role": sample["role"],
                            "reaction_id": sample.get("reaction_id", "unassigned"),
                            "energy_group_id": sample.get("energy_group_id"),
                            "label_region": sample.get("label_region"),
                            "composition_key": sample["composition_key"],
                            "component_mae_eV_per_A": one["component_mae_eV_per_A"],
                            "component_rmse_eV_per_A": one["component_rmse_eV_per_A"],
                            "vector_rmse_eV_per_A": one["vector_rmse_eV_per_A"],
                            "vector_p95_eV_per_A": one["vector_p95_eV_per_A"],
                            "vector_max_eV_per_A": one["vector_max_eV_per_A"],
                            "vasp_energy_eV": sample["vasp_label"]["energy_eV"],
                            "predicted_energy_eV": result["single_point"]["energy_eV"],
                            "single_point_status": "success",
                        }
                    )
            metrics = force_metrics(labels, predictions, movable_indices) if labels else {}
            metrics["failed_samples"] = failed
            scope_key = scope_id if scope_type != "reaction" else f"reaction::{scope_id}"
            backend_summary["force_metrics"][scope_key] = metrics
            force_summary_rows.append(
                {
                    "backend": backend,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    **{key: value for key, value in metrics.items() if key != "failed_samples"},
                    "failed_sample_count": len(failed),
                }
            )

        adsorption_pairs = [
            (sample, result_by_backend[backend][sample["sample_id"]]["relaxation"])
            for sample in manifest["samples"]
            if sample["subset"] == "adsorption"
        ]
        evaluated_pairs = [
            pair for pair in adsorption_pairs if pair[1].get("status") != "not_applicable"
        ]
        adsorption_results = [row for _, row in evaluated_pairs]
        technical = sum(bool(row.get("technical_success")) for row in adsorption_results)
        usable = sum(bool(row.get("usable_success")) for row in adsorption_results)
        backend_summary["relaxation"] = {
            "eligible_sample_count": len(adsorption_pairs),
            "evaluated_sample_count": len(adsorption_results),
            "technical_success_count": technical,
            "technical_success_rate": (
                technical / len(adsorption_results) if adsorption_results else None
            ),
            "usable_success_count": usable,
            "usable_success_rate": usable / len(adsorption_results) if adsorption_results else None,
            "failures": [
                {
                    "sample_id": sample["sample_id"],
                    "status": relaxation.get("status"),
                    "error": relaxation.get("error"),
                }
                for sample, relaxation in evaluated_pairs
                if not relaxation.get("usable_success")
            ],
        }
        for sample, relaxation in evaluated_pairs:
            relaxation_rows.append(
                {
                    "backend": backend,
                    "sample_id": sample["sample_id"],
                    "status": relaxation.get("status"),
                    "optimizer_steps": relaxation.get("optimizer_steps"),
                    "optimizer_converged": relaxation.get("optimizer_converged"),
                    "final_movable_fmax_eV_per_A": relaxation.get(
                        "final_movable_fmax_eV_per_A"
                    ),
                    "technical_success": relaxation.get("technical_success"),
                    "geometry_sanity_pass": relaxation.get("geometry_sanity_pass"),
                    "usable_success": relaxation.get("usable_success"),
                    "minimum_pair_distance_A": relaxation.get("minimum_pair_distance_A"),
                    "nearest_adsorbate_fe_distance_A": relaxation.get(
                        "nearest_adsorbate_fe_distance_A"
                    ),
                    "error_type": relaxation.get("error_type"),
                    "error": relaxation.get("error"),
                }
            )
        if backend == "aqcat25":
            deltas = []
            for sample in manifest["samples"]:
                result = result_by_backend[backend][sample["sample_id"]]
                if result["single_point"]["status"] != "success":
                    continue
                existing_prediction = sample.get("existing_aqcat25_prediction")
                if existing_prediction is None:
                    continue
                current = np.asarray(result["single_point"]["forces_eV_per_A"])
                existing = np.asarray(existing_prediction["forces_eV_per_A"])
                deltas.extend(np.abs(current - existing).ravel().tolist())
            backend_summary["existing_prediction_reproducibility"] = {
                "compared_sample_count": sum(
                    "existing_aqcat25_prediction" in sample for sample in manifest["samples"]
                ),
                "max_force_component_delta_eV_per_A": max(deltas) if deltas else math.nan
            }
        summary["backends"][backend] = backend_summary

    energy_rows: list[dict[str, Any]] = []
    group_keys = sorted(
        {
            sample.get(
                "energy_group_id", f"{sample['subset']}::{sample['composition_key']}"
            )
            for sample in manifest["samples"]
            if sample["vasp_label"].get("energy_comparison_eligible", True)
        }
    )
    for energy_group_id in group_keys:
        samples = [
            sample
            for sample in manifest["samples"]
            if sample.get(
                "energy_group_id", f"{sample['subset']}::{sample['composition_key']}"
            )
            == energy_group_id
            and sample["vasp_label"].get("energy_comparison_eligible", True)
        ]
        if len(samples) < 2:
            continue
        compositions = {sample["composition_key"] for sample in samples}
        if len(compositions) != 1:
            raise ValueError(f"mixed compositions in energy group: {energy_group_id}")
        composition = next(iter(compositions))
        reaction_id = samples[0].get("reaction_id", "unassigned")
        subset = samples[0]["subset"]
        vasp = [float(sample["vasp_label"]["energy_eV"]) for sample in samples]
        vasp_relative = [value - min(vasp) for value in vasp]
        for backend in ("aqcat25", "matris"):
            if any(
                result_by_backend[backend][sample["sample_id"]]["single_point"]["status"]
                != "success"
                for sample in samples
            ):
                continue
            prediction = [
                float(result_by_backend[backend][sample["sample_id"]]["single_point"]["energy_eV"])
                for sample in samples
            ]
            predicted_relative = [value - min(prediction) for value in prediction]
            errors = [pred - ref for pred, ref in zip(predicted_relative, vasp_relative)]
            group = {
                "backend": backend,
                "subset": subset,
                "reaction_id": reaction_id,
                "energy_group_id": energy_group_id,
                "composition_key": composition,
                "sample_count": len(samples),
                "relative_energy_mae_eV": sum(abs(value) for value in errors) / len(errors),
                "relative_energy_rmse_eV": math.sqrt(
                    sum(value * value for value in errors) / len(errors)
                ),
                "spearman_rho": spearman(vasp_relative, predicted_relative),
                "kendall_tau": kendall_tau(vasp_relative, predicted_relative),
                "lowest_energy_match": int(vasp.index(min(vasp)) == prediction.index(min(prediction))),
            }
            summary["relative_energy_groups"].append(group)
            for sample, reference, predicted, error in zip(
                samples, vasp_relative, predicted_relative, errors
            ):
                energy_rows.append(
                    group
                    | {
                        "sample_id": sample["sample_id"],
                        "vasp_relative_energy_eV": reference,
                        "predicted_relative_energy_eV": predicted,
                        "relative_energy_error_eV": error,
                    }
                )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output / "per_sample_force_metrics.csv",
        [
            "backend",
            "sample_id",
            "subset",
            "role",
            "reaction_id",
            "energy_group_id",
            "label_region",
            "composition_key",
            "component_mae_eV_per_A",
            "component_rmse_eV_per_A",
            "vector_rmse_eV_per_A",
            "vector_p95_eV_per_A",
            "vector_max_eV_per_A",
            "vasp_energy_eV",
            "predicted_energy_eV",
            "single_point_status",
        ],
        per_sample_rows,
    )
    _write_csv(
        output / "relative_energy_metrics.csv",
        [
            "backend",
            "subset",
            "reaction_id",
            "energy_group_id",
            "composition_key",
            "sample_count",
            "sample_id",
            "vasp_relative_energy_eV",
            "predicted_relative_energy_eV",
            "relative_energy_error_eV",
            "relative_energy_mae_eV",
            "relative_energy_rmse_eV",
            "spearman_rho",
            "kendall_tau",
            "lowest_energy_match",
        ],
        energy_rows,
    )
    _write_csv(
        output / "force_summary.csv",
        [
            "backend",
            "scope_type",
            "scope_id",
            "sample_count",
            "movable_atom_count",
            "force_component_count",
            "component_mae_eV_per_A",
            "component_rmse_eV_per_A",
            "vector_rmse_eV_per_A",
            "vector_p95_eV_per_A",
            "vector_max_eV_per_A",
            "failed_sample_count",
        ],
        force_summary_rows,
    )
    _write_csv(
        output / "relaxation_metrics.csv",
        [
            "backend",
            "sample_id",
            "status",
            "optimizer_steps",
            "optimizer_converged",
            "final_movable_fmax_eV_per_A",
            "technical_success",
            "geometry_sanity_pass",
            "usable_success",
            "minimum_pair_distance_A",
            "nearest_adsorbate_fe_distance_A",
            "error_type",
            "error",
        ],
        relaxation_rows,
    )
    write_json_atomic(output / "assessment_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build a hash-bound benchmark package")
    prepare.add_argument("--adsorption-root", type=Path, required=True)
    prepare.add_argument("--ts-root", type=Path, required=True)
    prepare.add_argument("--destination", type=Path, required=True)
    prepare.add_argument("--benchmark-id", required=True)
    prepare.add_argument("--matris-checkpoint-sha256", required=True)
    prepare.set_defaults(func=prepare_benchmark)

    extend = subparsers.add_parser(
        "extend", help="Add reviewed existing VASP labels to a prepared package"
    )
    extend.add_argument("--base-manifest", type=Path, required=True)
    extend.add_argument("--spec", type=Path, required=True)
    extend.add_argument("--source-root", type=Path, required=True)
    extend.add_argument("--destination", type=Path, required=True)
    extend.add_argument("--benchmark-id", required=True)
    extend.set_defaults(func=extend_benchmark)

    run = subparsers.add_parser("run", help="Run one MLIP backend on the prepared package")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--backend", choices=("aqcat25", "matris"), required=True)
    run.add_argument("--checkpoint", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    run.add_argument("--backend-version", required=True)
    run.add_argument("--sample-limit", type=int)
    run.add_argument("--sample-id", action="append")
    run.add_argument("--skip-relaxation", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.set_defaults(func=run_backend)

    assess = subparsers.add_parser("assess", help="Calculate unified force/energy/relax metrics")
    assess.add_argument("--manifest", type=Path, required=True)
    assess.add_argument("--result", action="append", type=Path, required=True)
    assess.add_argument("--output", type=Path, required=True)
    assess.set_defaults(func=assess_benchmark)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
