"""Review exact static probe labels and forces; no execution or acceptance gate."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_adsorption_validation_20261018.validation_helpers import force_metrics
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.vasp_result_gate import final_scf_status, read_incar_values


def validate_static(directory: Path, expected_symbols: list[str]) -> dict:
    """Cross-check two force parsers and exact coordinates on the frozen branch."""
    atoms = read(directory / "POSCAR", format="vasp")
    values = read_incar_values(directory / "INCAR")
    expected = {"NSW": "0", "IBRION": "-1", "ISPIN": "2", "ISMEAR": "1"}
    if any(values.get(k) != v for k, v in expected.items()) or float(values["SIGMA"]) != .20:
        raise ValueError("not the frozen spin-polarized static branch")
    fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    if atoms.get_chemical_symbols() != expected_symbols or fixed != list(range(18)):
        raise ValueError("input atom order or fixed mask changed")
    text = (directory / "OUTCAR").read_text(encoding="utf-8", errors="strict")
    blocks = list(re.finditer(r"POSITION\s+TOTAL-FORCE \(eV/Angst\)", text))
    if len(blocks) != 1:
        raise ValueError("expected exactly one static force table")
    table = text[blocks[0].end():].splitlines()[2:2 + len(atoms)]
    tokens = [line.split() for line in table]
    if len(tokens) != len(atoms) or any(len(row) != 6 for row in tokens):
        raise ValueError("incomplete raw force table")
    positions = np.asarray([[float(v) for v in row[:3]] for row in tokens])
    forces = np.asarray([[float(v) for v in row[3:]] for row in tokens])
    if not np.isfinite(positions).all() or not np.isfinite(forces).all():
        raise ValueError("nonfinite raw force table")
    precision = np.asarray([[len(v.split(".")[-1]) for v in row[:3]] for row in tokens])
    bound = np.linalg.norm(.5 * 10. ** (-precision), axis=1)
    _, delta = find_mic(positions - atoms.positions, atoms.cell, pbc=[True, True, False])
    if np.any(delta > bound + 1e-8):
        raise ValueError("OUTCAR force coordinates do not match POSCAR")
    parsed = parse_final_outcar(directory / "OUTCAR")
    ase_out = read(directory / "OUTCAR", format="vasp-out")
    if (ase_out.get_chemical_symbols() != expected_symbols
            or not np.array_equal(forces, np.asarray(parsed["forces_eV_per_A"]))
            or not np.array_equal(forces, ase_out.get_forces(apply_constraint=False))):
        raise ValueError("raw/canonical/ASE force parsers disagree")
    final = read(directory / "CONTCAR", format="vasp")
    if (final.get_chemical_symbols() != expected_symbols
            or not np.allclose(final.cell, atoms.cell, atol=1e-10, rtol=0)):
        raise ValueError("final order/cell changed")
    _, movement = find_mic(final.positions - atoms.positions, atoms.cell, pbc=[True, True, False])
    if np.max(movement) > 1e-10:
        raise ValueError("static coordinates moved")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    out = parse_outcar(directory / "OUTCAR")
    if (not parsed["normal_completion"] or not scf["electronically_converged"]
            or scf["last_electronic_iteration"] >= scf["nelm"] or out["fatal_keywords"]):
        raise ValueError("electronic/normal-completion gate failed")
    moments = np.asarray(out["local_magnetization_last_muB"])
    total = out["total_magnetization_history_muB"]
    if (moments.shape != (len(atoms),) or not np.isfinite(moments).all()
            or not total or not np.isfinite(total[-1]) or not np.isfinite(parsed["final_toten_eV"])):
        raise ValueError("incomplete/nonfinite magnetic or energy label")
    return {"symbols": expected_symbols, "fixed_atom_indices_0based": fixed,
            "forces_eV_per_A": forces.tolist(), "SCF": scf,
            "electronic_converged": True, "normal_completion": True,
            "geometry_review_pass": True, "geometry_review_scope": "exact static coordinates only",
            "max_coordinate_difference_A": float(delta.max()),
            "toten_eV_force_label_only": parsed["final_toten_eV"],
            "total_magnetization_muB": total[-1], "local_magnetization_muB": moments.tolist(),
            "Fe_moment_range_muB": [float(moments[:45].min()), float(moments[:45].max())],
            "Fe_positive_moment_count": int((moments[:45] > 0).sum()),
            "magnetic_global_ground_state_verified": False,
            "adsorbate_fmax_eV_A": float(np.linalg.norm(forces[45:], axis=1).max()),
            "source_force_table_sha256": sha256_text("\n".join(" ".join(r) for r in tokens) + "\n")}


def review_labels(batch_root: Path, checkpoint: Path) -> dict:
    """Consume a completed immutable collection without querying remote state."""
    batch = load_json_object(batch_root / "batch_request.json")
    expected = {s["sample_id"]: s for s in batch["samples"]}
    submissions = load_json_object(batch_root / "submission_summary.json")["samples"]
    metadata = {s["sample_id"]: s for s in json.loads((checkpoint / "remote_metadata.stdout.json").read_bytes())}
    potcars = {s["sample_id"]: s["potcar_sha256"] for s in load_json_object(batch_root / "execution_plan.json")["samples"]}
    samples = []
    for job in submissions:
        name = job["sample_id"]
        directory = checkpoint / "vasp" / name
        scheduler = load_json_object(checkpoint / (name + "_scheduler.json"))
        validate_stored_lsf_evidence(scheduler, required_status="DONE")
        if scheduler["job_id"] != job["job_id"] or metadata[name]["POTCAR_sha256"] != potcars[name]:
            raise ValueError("scheduler/job/POTCAR binding changed")
        for filename, info in metadata[name]["files"].items():
            if sha256_file(directory / filename) != info["sha256"]:
                raise ValueError("collected source bytes changed")
        for filename, digest in expected[name]["input_hashes"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("submitted input changed")
        symbols = read(batch_root / name / "POSCAR", format="vasp").get_chemical_symbols()
        row = {"sample_id": name, "source_name": name, "source_job_id": job["job_id"],
               "composition": expected[name]["composition"], "ionic_step": 1,
               "structure_path": "vasp/" + name + "/POSCAR",
               "structure_sha256": sha256_file(directory / "POSCAR"),
               **{"source_" + f + "_sha256": sha256_file(directory / f) for f in ("POSCAR", "INCAR", "OUTCAR")},
               **validate_static(directory, symbols)}
        write_json_exclusive(directory / "label_review.json", row)
        samples.append(row)
    report = {"document_kind": "reviewed_exact_static_force_diagnostics", "samples": samples,
              "batch_sha256": sha256_file(batch_root / "batch_request.json"),
              "sample_role": "screened_untrained_diagnostic_not_independent_heldout",
              "reportable_final_energy": False, "training_authorized": False}
    write_json_exclusive(checkpoint / "dataset_review.json", report)
    return report


def compare_forces(reference, prediction, symbols: list[str], fixed: list[int]) -> dict:
    """Separate adsorbates from Fe, including force-reversal and descent checks."""
    metrics = force_metrics(reference, prediction, symbols, fixed)
    r, p = np.asarray(reference), np.asarray(prediction)
    indices = [i for i, s in enumerate(symbols) if s != "Fe" and i not in fixed]
    r, p = r[indices], p[indices]
    rn, pn = np.linalg.norm(r, axis=1), np.linalg.norm(p, axis=1)
    dot = np.einsum("ij,ij->i", r, p)
    valid = (rn > 1e-8) & (pn > 1e-8)
    atoms = []
    for n, i in enumerate(indices):
        cosine = float(np.clip(dot[n] / (rn[n] * pn[n]), -1, 1)) if valid[n] else None
        atoms.append({"index_0based": i, "symbol": symbols[i],
                      "DFT_norm_eV_A": float(rn[n]), "model_norm_eV_A": float(pn[n]),
                      "vector_error_eV_A": float(np.linalg.norm(p[n] - r[n])),
                      "cosine": cosine,
                      "angle_degrees": float(np.degrees(np.arccos(cosine))) if cosine is not None else None})
    denominator = float(np.sum(r * r))
    metrics["adsorbate"].update(
        relative_vector_L2_error=float(np.linalg.norm(p - r) / np.sqrt(denominator)) if denominator else None,
        opposite_direction_count=int((dot[valid] < 0).sum()),
        defined_direction_count=int(valid.sum()),
        DFT_dot_model_eV2_A2=float(dot.sum()),
        local_descent_first_order=bool(dot.sum() > 0),
        DFT_rms_force_eV_A=float(np.sqrt(denominator / len(indices))) if indices else None)
    return {"groups": metrics, "adsorbate_atoms": atoms}


def projected_contacts(atoms, reference, prediction, guards: dict[str, float]) -> list[dict]:
    """Project relative force along each adsorbate's nearest normalized contact.

    Positive projection separates the pair. For a constrained optimizer this is
    a diagnostic projection, not the actual relative displacement of fixed Fe.
    """
    contacts = set()
    for i in range(45, len(atoms)):
        candidates = []
        for j in range(len(atoms)):
            if i == j:
                continue
            key = "-".join(sorted((atoms[i].symbol, atoms[j].symbol)))
            if key not in guards:
                raise ValueError("missing pair guard: " + key)
            distance = atoms.get_distance(i, j, mic=True)
            candidates.append((distance / guards[key], min(i, j), max(i, j)))
        _, first, second = min(candidates)
        contacts.add((first, second))
    r, p = np.asarray(reference), np.asarray(prediction)
    result = []
    for i, j in sorted(contacts):
        displacement = atoms.get_distance(i, j, mic=True, vector=True)
        distance = float(np.linalg.norm(displacement))
        unit = displacement / distance
        result.append({"indices_0based": [i, j], "elements": [atoms[i].symbol, atoms[j].symbol],
                       "distance_A": distance,
                       "DFT_separating_projection_eV_A": float(np.dot(r[j] - r[i], unit)),
                       "model_separating_projection_eV_A": float(np.dot(p[j] - p[i], unit))})
    return result
