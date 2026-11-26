"""Fe(110) MACE CPU trial: pre-relaxation, ordinary path and label-selection review."""
from __future__ import annotations

import argparse
import math
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import numpy as np
import yaml
from ase.geometry import find_mic
from ase.io import read
from ase.optimize import FIRE

from scripts.aqcat25_ml_neb import (RunSettings, _adjacent_rmsd, _evaluate_path, _fixed_indices,
    _key_bond_distances, _label_candidates, _minimum_pair_distance, _optimizer_stage,
    _periodic_branch_continuous, _unwrap_path, _write_vasp_atomic)
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.fe110_mlip_selection import select_model
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/mace_fe110_pilot.yaml"


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def checked_file(record):
    path = Path(record["path"]).resolve(strict=True)
    if sha256_file(path) != record["sha256"]:
        raise ValueError(f"Bound source changed: {path}")
    return path


def validate_config(config):
    if config.get("version") != 1 or config.get("status") != "validation_only":
        raise ValueError("Expected a versioned validation-only configuration")
    if set(config["steps"]) != {"adsorption", "ordinary_neb"} or any(
        type(n) is not int or not 0 <= n <= 2 for n in config["steps"].values()
    ):
        raise ValueError("Pilot permits at most two steps per stage")
    policy = config["active_learning"]
    if policy["mode"] != "single_model_coverage_and_exact_vasp_error" or policy["calibration_status"] != "uncalibrated":
        raise ValueError("No inherited model calibration or committee evidence")
    if any(policy[k] is not False for k in
           ("new_vasp_labels_authorized", "training_authorized", "production_promotion_authorized")):
        raise ValueError("Pilot cannot authorize labeling, training or production")


def load_calculator(model):
    checkpoint = checked_file(model)
    import torch
    from mace.calculators import MACECalculator

    # Load only the hash-pinned local artifact in the dedicated pilot process.
    # The MACE runtime handles its own checkpoint format.
    torch.set_num_threads(2)
    # e3nn restores nested TorchScript with no map_location, independently of
    # torch.load. Map that load to CPU only during this isolated pilot's setup.
    jit_load = torch.jit.load

    def load_jit_on_cpu(file, map_location=None, **kwargs):
        return jit_load(file, map_location=map_location or "cpu", **kwargs)

    with patch.object(torch.jit, "load", load_jit_on_cpu):
        calc = MACECalculator(model_paths=str(checkpoint), device="cpu", head=model["head"],
                              default_dtype=model["dtype"])
    supported = {int(z) for z in calc.models[0].atomic_numbers}
    if calc.head != model["head"] or not set(model["required_atomic_numbers"]) <= supported:
        raise ValueError("Requested head or Fe–C–O–H element coverage absent")
    if sha256_file(checkpoint) != model["sha256"]:
        raise ValueError("Checkpoint changed during loading")
    return calc, sorted(supported)


def check_geometry(images, reference, settings):
    fixed = _fixed_indices(reference)
    if fixed != list(range(18)):
        raise ValueError("Not the reviewed bottom-18 Fe(110) mask")
    for image in images:
        if (not np.array_equal(image.numbers, reference.numbers)
                or not np.array_equal(image.pbc, reference.pbc)
                or not np.allclose(image.cell, reference.cell, atol=1e-9, rtol=0)
                or _fixed_indices(image) != fixed or not np.isfinite(image.positions).all()):
            raise ValueError("Order, PBC, cell, finite geometry or fixed mask changed")
        _, drift = find_mic(image.positions[fixed] - reference.positions[fixed], reference.cell, reference.pbc)
        if drift.max() > 1e-8 or _minimum_pair_distance(image) < settings.minimum_pair_distance_A:
            raise ValueError("Fixed-layer drift or collision")
    if len(images) > 1 and (not _periodic_branch_continuous(images)
            or max(_adjacent_rmsd(images)) > settings.max_adjacent_rmsd_A):
        raise ValueError("Path adjacency / PBC guard failed")


def seed_path(config):
    base = ROOT / config["path_review_root"]
    root = base / "path"
    review = root / "path_review.json"
    report = root / "path_generation_report.json"
    contract_path = base / "reaction_contract.reviewed.json"
    contract = load_json_object(contract_path)
    if not validate_path_review(review, report)[0] or not validate_path_binding(root, contract)["valid"]:
        raise ValueError("Reviewed path or contract unavailable")
    normalized = base / "periodic_normalization.json"
    rows = load_json_object(normalized)["images"]
    if [r["image"] for r in rows] != [f"{i:02d}" for i in range(8)]:
        raise ValueError("Expected the exact eight-image reviewed seed")
    refs = []
    for row in rows:
        path = Path(row["review_path"]).resolve(strict=True)
        if path.parent != (root / row["image"]).resolve() or sha256_file(path) != row["review_sha256"]:
            raise ValueError("Normalized seed identity changed")
        refs.append(ref(path))
    changes = [{"atoms_1based": [int(i) + 1 for i in pair], "change": change}
        for key, change in (("formed_bonds", "formed"), ("broken_bonds", "broken")) for pair in contract[key]]
    return refs, changes, {"path_review": ref(review), "periodic_normalization": ref(normalized),
                           "contract": ref(contract_path)}


def evaluate(atoms, calculator):
    atoms.calc = calculator
    energy, forces = float(atoms.get_potential_energy()), np.asarray(atoms.get_forces(apply_constraint=False))
    if not math.isfinite(energy) or forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
        raise ValueError("Nonfinite or incomplete MACE prediction")
    return energy, forces


def path_trial(config, calculator, output, settings):
    refs, changes, origin = seed_path(config)
    images = [read(checked_file(r), format="vasp") for r in refs]
    reference = images[0].copy()
    _unwrap_path(images)
    check_geometry(images, reference, settings)
    initial = [_key_bond_distances(a, changes) for a in images]
    state = {"classification": "MACE_CPU_PILOT_NOT_HANDOFF", "model": config["model"], "input_images": refs}
    neb, converged, steps = _optimizer_stage(images, calculator, output, state, stage="mace_ordinary_neb",
        climb=False, spring_constant=settings.spring_constant_eV_per_A2, fmax=settings.ordinary_fmax_eV_per_A,
        max_steps=config["steps"]["ordinary_neb"], completed_steps=0, checkpoint_interval=1,
        step_guard=lambda: check_geometry(images, reference, settings))
    rows, metrics = _evaluate_path(images, neb, changes, output, settings)
    energies = metrics.pop("energies_eV")
    metrics["relative_energies_to_is_eV"] = [v - energies[0] for v in energies]
    if not np.isfinite(metrics["relative_energies_to_is_eV"]).all():
        raise ValueError("Invalid path energy")
    return {"steps": steps, "converged_at_ml_target": converged, "ci_started": False,
            "origin": origin, "input_images": refs, "input_bond_distances_A": initial,
            "images": rows, **metrics}


def prerelax_trial(config, calculator, reference, source, output, settings):
    atoms = reference.copy()
    before, force_before = evaluate(atoms, calculator)
    opt = FIRE(atoms, logfile=str(output / "mace_adsorption.log"), maxstep=.05)
    opt.attach(lambda: check_geometry([atoms], reference, settings), interval=1)
    converged = bool(opt.run(fmax=.10, steps=config["steps"]["adsorption"]))
    after, force_after = evaluate(atoms, calculator)
    _, movement = find_mic(atoms.positions - reference.positions, atoms.cell, atoms.pbc)
    mobile = np.delete(np.arange(len(atoms)), _fixed_indices(atoms))
    target = output / "adsorption_prerelax.vasp"
    _write_vasp_atomic(target, atoms)
    return {"input_structure": source, "output_structure": ref(target),
        "input_role": "existing_converged_coadsorption_endpoint_not_speed_benchmark",
        "steps": opt.nsteps, "converged_at_ml_target": converged,
        "delta_ml_energy_eV": after - before,
        "movable_ml_fmax_eV_per_A": [float(np.linalg.norm(f[mobile], axis=1).max()) for f in (force_before, force_after)],
        "maximum_displacement_A": float(movement.max()), "fixed_mask_preserved": True}


def compare_label(member, calculator):
    """Compare on the OUTCAR's final evaluated coordinates, not a relaxed ML image."""
    structure, outcar, incar = (checked_file(member[k]) for k in ("structure", "outcar", "incar"))
    stamp = member["scf"]
    if (not member["normal_completion"] or not stamp["electronically_converged"]
            or not member["final_output_hash_matches"]):
        raise ValueError("Reference is not a reviewed normally/electronically completed label")
    atoms = read(outcar, format="vasp-out", index=-1)
    saved = read(structure, format="vasp")
    if not np.array_equal(atoms.numbers, saved.numbers) or not np.allclose(atoms.cell, saved.cell, atol=1e-6, rtol=0):
        raise ValueError("OUTCAR ordinal species or cell differs")
    displacement, mismatch = find_mic(atoms.positions - saved.positions, saved.cell, saved.pbc)
    # The reviewed VASP force tables print Cartesian coordinates to 5 decimals.
    # Allow half a printed unit per component, plus cell-printing roundoff.
    component_error = float(np.abs(displacement).max())
    if not math.isfinite(component_error) or component_error > 5.1e-6:
        raise ValueError(f"OUTCAR terminal geometry not aligned to reviewed structure: {component_error:.7g} A per component")
    vasp_energy = float(atoms.calc.results["free_energy"])
    if abs(vasp_energy - member["final_toten_eV"]) > 1e-8:
        raise ValueError("VASP reference energy changed")
    vasp_forces = np.asarray(atoms.get_forces(apply_constraint=False))
    if not np.isfinite(vasp_forces).all() or vasp_forces.shape != (len(atoms), 3):
        raise ValueError("Missing raw VASP force vectors")
    energy, prediction = evaluate(atoms, calculator)
    mobile = np.delete(np.arange(len(atoms)), _fixed_indices(saved))
    vectors = prediction - vasp_forces
    is_fe = atoms.numbers == 26
    groups = {"movable": mobile, "movable_Fe": mobile[is_fe[mobile]], "adsorbate": mobile[~is_fe[mobile]]}
    metrics = {}
    for key, indices in groups.items():
        norms = np.linalg.norm(vectors[indices], axis=1)
        metrics[key] = {"n_atoms": len(norms), "vector_mae_eV_per_A": float(norms.mean()),
                        "vector_max_eV_per_A": float(norms.max())}
    return {"structure": ref(structure), "outcar": ref(outcar), "incar": ref(incar),
        "max_alignment_error_A": float(mismatch.max()), "max_component_alignment_error_A": component_error,
        "mace_energy_eV": energy, "vasp_toten_eV": vasp_energy,
        "mace_forces_eV_per_A": prediction.tolist(), "vasp_forces_eV_per_A": vasp_forces.tolist(),
        "force_error": metrics, "not_training_or_independent_holdout": True}


def active_learning_review(config, path, calculator, output):
    groups = {}
    for key in ("ch_co", "int06_mid"):
        packet = ROOT / config["reference_review_root"] / key / "review_packet.json"
        members = load_json_object(packet)["source_members"]
        rows, rejected = {}, {}
        for name in ("initial", "ts", "final"):
            try:
                rows[name] = compare_label(members[name], calculator)
            except (OSError, ValueError, KeyError) as exc:
                rejected[name] = {"reason": str(exc), "outcar": members[name]["outcar"]}
        for name in rows:
            if "initial" in rows:
                for model, field in (("mace", "mace_energy_eV"), ("vasp", "vasp_toten_eV")):
                    rows[name][f"{model}_relative_to_is_eV"] = rows[name][field] - rows["initial"][field]
        groups[key] = {"source_review": ref(packet), "same_geometry_comparisons": rows, "rejected_labels": rejected}
    selected = _label_candidates(path["images"], path["adjacent_rmsd_A"])
    by_image = {r["image"]: r for r in path["images"]}
    for item in selected:
        row = by_image[item["image"]]
        item["candidate_structure"] = ref(output / row["structure_path"])
        item["review_state"] = "not_labeled_or_approved"
    return {"policy": config["active_learning"], "reference_comparisons": groups,
            "existing_vasp_labels_compared": sum(len(g["same_geometry_comparisons"]) for g in groups.values()),
            "selection_basis": "predicted peak/neighbors, path coverage and adjacent RMSD; not uncertainty",
            "candidate_labels": selected, "training_state": "blocked_no_reviewed_mace_calibration_or_split",
            "new_vasp_jobs": False, "updated_weights": False}


def run(output, config_path):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    validate_config(config)
    if config_path == CONFIG.resolve() and select_model("ts_path_search")["model"] != config["model"]:
        raise ValueError("Default pilot must match the selected Fe(110) model")
    output.mkdir(parents=True, exist_ok=False)
    calculator, elements = load_calculator(config["model"])
    settings = RunSettings(ordinary_max_steps=config["steps"]["ordinary_neb"], ml_ci="off",
                           minimum_pair_distance_A=1.0, max_adjacent_rmsd_A=.75)
    packet = ROOT / config["reference_review_root"] / "ch_co/review_packet.json"
    initial = load_json_object(packet)["source_members"]["initial"]["structure"]
    ads = prerelax_trial(config, calculator, read(checked_file(initial), format="vasp"), initial, output, settings)
    write_json_exclusive(output / "adsorption_review.json", ads)
    path = path_trial(config, calculator, output, settings)
    write_json_exclusive(output / "path_review.json", path)
    learning = active_learning_review(config, path, calculator, output)
    write_json_exclusive(output / "active_learning_review.json", learning)
    count = learning["existing_vasp_labels_compared"]
    write_json_exclusive(output / "receipt.json", {"status": "PILOT_COMPLETED_NOT_PRODUCTION_VALIDATED" if count == 6
        else "PILOT_PARTIAL_LABEL_COMPARISON_NOT_PRODUCTION_VALIDATED",
        "runtime": {n: version(n) for n in ("mace-torch", "torch", "ase")},
        "device": "cpu", "config": ref(config_path), "model": config["model"], "elements": elements,
        "adsorption_steps": ads["steps"], "ordinary_neb_steps": path["steps"],
        "path_images": len(path["images"]), "existing_vasp_labels_compared": count,
        "formal_execution_authorized": False, "weights_changed": False, "production_configuration_changed": False})


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--config", type=Path, default=CONFIG)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    run(args.output.resolve(), args.config.resolve())


if __name__ == "__main__":
    main()
