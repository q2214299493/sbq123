"""Extract existing scalar energies for the previously reviewed near-force pool."""
from __future__ import annotations

import numpy as np
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import restore_input_lattice, verify_frame
from archive.fe110_grouped_qc_20261026.review import magnetic_status
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .audit import Sources, branch
from .collect import BASE, OUT


def run():
    physical_path = BASE / "independent_nearstable_inventory_20261113_v1/physical_inventory.json"
    physical = load_json_object(physical_path)
    sources = Sources()
    trajectories = {}
    result = []
    for row in physical["near_force_candidates"]:
        digest = row["source_OUTCAR_sha256"]
        indexed = sources.index[digest][0]["paths"]
        if digest not in trajectories:
            initial = read(indexed["POSCAR"], format="vasp")
            xdatcar = row["source_XDATCAR"]
            if sha256_file(__import__("pathlib").Path(xdatcar)) != row["source_XDATCAR_sha256"]:
                raise ValueError("near-force coordinate source changed")
            trajectories[digest] = (initial, read(xdatcar, format="vasp-xdatcar", index=":"))
            sources.bound.update([__import__("pathlib").Path(xdatcar), __import__("pathlib").Path(indexed["POSCAR"])])
        initial, trajectory = trajectories[digest]
        atoms = trajectory[row["ionic_step"] - 1]
        restore_input_lattice(atoms, initial, __import__("pathlib").Path(row["source_XDATCAR"]))
        atoms.set_constraint(initial.constraints)
        source = sources.get(digest, len(atoms))
        frame = next(f for f in source["frames"] if f["ionic_step"] == row["ionic_step"])
        forces = verify_frame(atoms, frame)
        moments = magnetic_status(frame["local_moment_tables"], len(atoms)) if frame["local_moment_tables"] else {}
        compatibility = branch(source, atoms)
        record = {"sample_id": row["candidate_id"], "source_job_id": row["source_job_id"],
                  "pool": "prior_independent_near_force_source_inventory", "partition": "unassigned_external_diagnostic",
                  "source_OUTCAR_sha256": digest, "physical_label_key": digest + ":" + str(row["ionic_step"]),
                  "DFT_ionic_step": row["ionic_step"], "source_byte_range": frame["source_byte_range"],
                  "source_XDATCAR": row["source_XDATCAR"], "source_XDATCAR_sha256": row["source_XDATCAR_sha256"],
                  "composition": row["composition"], "graph_signature": row["graph_signature"],
                  "adsorbate_component_count": row["adsorbate_component_count"], "E_TOTEN_eV": frame["toten_eV"],
                  "energy_definition": "raw_same_ionic_step_free_energy_TOTEN", "energy_unit": "eV",
                  "coordinate_force_precision_pass": True,
                  "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
                  "normal_completion": source["normal_completion"],
                  "raw_EDIFF_marker_before_force": frame.get("EDIFF_marker_before_force", False),
                  "raw_magnetic_grade": moments.get("magnetic_review_level", "NO_LOCAL_MOMENT_TABLE"),
                  "original_magnetic_grade_preserved": row["magnetic_review_level"], "compatibility": compatibility,
                  "permitted_use": "EXISTING_EXTERNAL_SOURCE_DIAGNOSTIC_OR_LATER_SEPARATE_VALIDATION_REVIEW",
                  "reaction_path_identity": "OPTIMIZATION_TRAJECTORY_NOT_CERTIFIED_REACTION_PATH",
                  "absolute_AQ_energy_target_ready": False, "new_training_admission": False,
                  "new_DFT_action": "NO_DUPLICATE_DFT;existing_scalar_and_force_source_recovered"}
        result.append(record)
    sources.bound.add(physical_path)
    write_json_exclusive(OUT / "near_energy_source_sidecar.json", {
        "status": "READ_ONLY_EXISTING_ENERGY_EXTRACTION_NO_PARTITION_ASSIGNMENT", "records": result,
        "training_or_reference_energy_promotion": False, "new_calculations": False,
        "source_files": source_file_manifest(sorted(sources.bound))})
    print({"near_force_source_rows": len(result), "new_DFT": False}, flush=True)


if __name__ == "__main__":
    run()
