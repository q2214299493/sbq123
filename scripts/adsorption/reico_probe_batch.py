"""Select six training-family geometry probes and reuse canonical static inputs.

Preparation only: this module never uploads files, submits VASP, or runs a model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.adsorption.reico_random_geometry import audit_geometry, immutable_json, load_slab
from scripts.artifact_io import load_json_object, sha256_file
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import DEFAULT_PROFILE, build_fe110_active_learning_force_label

QUANTILES = {"C2HO": (0.5,), "C2H2O": (0.5,), "C2H3": (0.5,), "C3H2O": (0.1, 0.5, 0.9)}


def select_probes(records: list[dict], pair_minimum_A: dict) -> list[dict]:
    """Stratify only on geometry, with three C2 and three C3 training families."""
    selected = []
    for composition, quantiles in QUANTILES.items():
        candidates = []
        for row in records:
            if (row["composition"] != composition or row["partition"] != "train"
                    or row["status"] != "CPU_GEOMETRY_CANDIDATE"):
                continue
            minima = row["geometry_audit"]["pair_minima_A"]
            if not minima or any(not np.isfinite(v) or v <= 0 for v in minima.values()):
                raise ValueError("invalid pair-distance descriptor")
            score = min(distance / pair_minimum_A[key] for key, distance in minima.items())
            if score < 1 - 1e-12:
                raise ValueError("a source candidate violates its collision guards")
            candidates.append({**row, "contact_margin_score": score})
        candidates.sort(key=lambda r: (r["contact_margin_score"], r["family_id"]))
        if len(candidates) < len(quantiles):
            raise ValueError(f"insufficient training families for {composition}; no padding")
        indices = [round(q * (len(candidates) - 1)) for q in quantiles]
        if len(set(indices)) != len(indices):
            raise ValueError(f"quantile selection repeats a family for {composition}")
        selected.extend({**candidates[i], "selection_quantile": q} for q, i in zip(quantiles, indices, strict=True))
    if len({r["family_id"] for r in selected}) != 6:
        raise ValueError("six unique families required")
    return selected


def source_records(source: Path) -> tuple[dict, dict, list[dict]]:
    config_path = source / "inputs/config.json"
    config = load_json_object(config_path)
    summary = load_json_object(source / "summary_0100.json")
    if sha256_file(config_path) != summary["binding"]["config_sha256"]:
        raise ValueError("source generation config changed")
    if summary["generated"] != 99 or summary["failed"] != 1:
        raise ValueError("not the frozen first-step 99-candidate pool")
    rows = []
    for family in summary["families"]:
        if family["status"] != "CPU_GEOMETRY_CANDIDATE":
            continue
        path = source / "families" / family["family_id"] / "family.json"
        row = load_json_object(path)
        if any(row[key] != family[key] for key in ("family_id", "composition", "partition", "status", "geometry_key")):
            raise ValueError(f"family binding changed: {path}")
        poscar = path.parent / "POSCAR"
        if sha256_file(poscar) != row["poscar_sha256"]:
            raise ValueError(f"source POSCAR changed: {poscar}")
        rows.append(row)
    return config, summary, rows


def prepare(source: Path, destination: Path, *, profile_path: Path = DEFAULT_PROFILE) -> dict:
    config, summary, records = source_records(source)
    slab = load_slab(source / "inputs/slab.POSCAR", config["source_slab_sha256"])
    selected = select_probes(records, config["pair_minimum_A"])
    if destination.exists():
        raise FileExistsError(f"refusing an existing preparation destination: {destination}")
    # Recheck all six before any input directory is created.
    for row in selected:
        poscar = source / "families" / row["family_id"] / "POSCAR"
        atoms = read(poscar, format="vasp")
        if audit_geometry(atoms, slab, config)["reasons"]:
            raise ValueError(f"probe geometry failed fresh guards: {row['family_id']}")
        if atoms.get_chemical_symbols()[45:] != [s for s in config["element_order"] for _ in range(row["counts"][s])]:
            raise ValueError("source composition/order mismatch")
    destination.mkdir(parents=True, exist_ok=False)
    frozen = {"document_kind": "fe110_reico_six_probe_selection", "selection_before_DFT_or_model_prediction": True,
              "source_summary_sha256": sha256_file(source / "summary_0100.json"),
              "source_generation_binding": summary["binding"], "selection_scope": "training_split_only_not_independent_validation",
              "selector_sha256": sha256_file(Path(__file__)), "rows": selected,
              "full_99_domain_validity_from_six_probes": False}
    immutable_json(destination / "selection.json", frozen)
    samples = []
    for row in selected:
        folder = destination / row["family_id"]
        folder.mkdir(exist_ok=False)
        source_poscar = source / "families" / row["family_id"] / "POSCAR"
        with (folder / "POSCAR").open("xb") as handle:
            handle.write(source_poscar.read_bytes())
        profile = build_fe110_active_learning_force_label(folder, profile_path=profile_path)
        immutable_json(folder / "input_profile.json", profile)
        request = {"document_kind": "fe110_reico_fixed_geometry_probe", "family_id": row["family_id"],
                   "composition": row["composition"], "partition": row["partition"],
                   "selection_sha256": sha256_file(destination / "selection.json"),
                   "structure_sha256": sha256_file(folder / "POSCAR"),
                   "source_POSCAR": str(source_poscar.resolve()), "source_family_sha256": sha256_file(source_poscar.parent / "family.json"),
                   "geometry_audit": audit_geometry(read(folder / "POSCAR", format="vasp"), slab, config),
                   "requested_labels": ["compatible_TOTEN", "all_atom_forces", "total_and_local_magnetic_moments"],
                   "electronic_convergence_required": True, "ionic_convergence_required_for_label": False,
                   "training_eligibility": "pending_label_energy_force_and_magnetic_review", "reportable_adsorption_energy": False,
                   "scientific_acceptance": False, "geometry_optimization": False}
        immutable_json(folder / "label_request.json", request)
        check = preflight(folder, "diagnostic_static")
        if not check["passed"]:
            raise ValueError(f"canonical preflight failed: {row['family_id']}: {check['errors']}")
        samples.append({"sample_id": row["family_id"], "composition": row["composition"], "directory": row["family_id"],
                        "structure_sha256": sha256_file(folder / "POSCAR"), "bundle_sha256": check["bundle_sha256"],
                        "input_hashes": check["files"], "cores": profile["cores"], "status": "PREPARED_NOT_SUBMITTED"})
    batch = {"document_kind": "fe110_reico_six_probe_batch", "status": "PREPARED_PENDING_EXECUTION_GATE_AND_REMOTE_RECHECK",
             "samples": samples, "profile_sha256": sha256_file(profile_path), "remote_backend": "sunboquan-codex",
             "automatic_retry": False, "optimization_or_training_authorized_by_this_file": False,
             "selection_sha256": sha256_file(destination / "selection.json"), "new_DFT_probes": 6,
             "included_in_original_300_label_cap": True, "is_independent_final_test": False}
    immutable_json(destination / "batch_request.json", batch)
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination)
    print(json.dumps({"status": result["status"], "samples": [r["sample_id"] for r in result["samples"]], "submitted": 0}))


if __name__ == "__main__":
    main()
