"""Read documented reaction labels and accepted scalar references; no promotion."""
from __future__ import annotations

import re
from pathlib import Path

from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .audit import Sources, inspect_row
from .collect import OUT, ROOT


def static_labels(sources, snapshot):
    result = []
    for calc in snapshot["calculations"]:
        if "force_label" not in calc["purpose"]:
            continue
        file = next(f for f in snapshot["files"] if f["calculation_id"] == calc["calculation_id"] and f["filename"] == "POSCAR")
        poscar = Path(file["local_path"])
        label_path = poscar.parent / "vasp_force_label.json"
        label = load_json_object(label_path)
        request_path = poscar.parent / "label_request.json"
        request = load_json_object(request_path)
        atoms = read(poscar, format="vasp")
        held = request["document_kind"] == "vasp_ts_heldout_force_label_request"
        row = {"sample_id": calc["calculation_id"], "source_OUTCAR_sha256": label["outcar"]["sha256"],
               "ionic_step": 1, "structure_sha256": label["structure"]["sha256"],
               "forces_eV_per_A": label["forces_eV_per_A"], "toten_eV_force_label_only": label["dft_toten_eV_force_label_only"],
               "electronic_converged": label["electronically_converged"], "geometry_review_pass": True,
               "composition": atoms[45:].get_chemical_formula(), "magnetic_review_level": "ORIGINAL_FORCE_ONLY_LABEL_SCOPE"}
        item = {"row": row, "pool": "documented_C_H_formation_path", "partition": "heldout" if held else "train",
                "root": poscar.parent, "metadata": label_path, "structure": poscar}
        record = inspect_row(item, sources)
        record.update(reaction_id=label["reaction_id"], chemical_event="C-H formation", source_label_path=str(label_path),
                      source_label_sha256=sha256_file(label_path), source_request_path=str(request_path),
                      source_request_sha256=sha256_file(request_path), source_request_kind=request["document_kind"],
                      protected_TS_validation=held, source_original_force_only_eligibility=label["eligible_for_force_only_training"],
                      permitted_use="PROTECTED_TS_VALIDATION_NO_TRAINING" if held else "EXISTING_PATH_FORCE_ENERGY_DIAGNOSTIC_MAGNETIC_REVIEW_REQUIRED")
        result.append(record)
        sources.bound.update([poscar, label_path, request_path])
    return result


def accepted_anchors(snapshot, dependencies, sources):
    files = {f["file_id"]: f for f in dependencies["files"]}
    rows = []
    for reference in dependencies["energy_reference_results"]:
        f = files[reference["source_file_id"]]
        path = Path(f["local_path"]) if f["local_path"] else None
        record = {"result_id": reference["result_id"], "calculation_id": reference["calculation_id"],
                  "E_TOTEN_eV": reference["numeric_value"], "unit": reference["unit"],
                  "energy_convention": reference["reference_convention"], "existing_validation_status": reference["validation_status"],
                  "source_path": str(path) if path else None, "source_sha256": f["sha256"],
                  "permitted_use": "EXISTING_ACCEPTED_ELECTRONIC_ENERGY_REFERENCE_NOT_AUTOMATIC_TRAINING", "new_admission": False,
                  "force_coordinate_label_complete": "Needs confirmation;not inferred from scalar registry energy"}
        if path and path.is_file():
            if sha256_file(path) != f["sha256"]:
                raise ValueError("accepted reference source changed")
            with path.open("rb") as handle:
                handle.seek(max(0, path.stat().st_size - 25000))
                tail = handle.read()
            energies = re.findall(rb"free\s+energy\s+TOTEN\s*=\s*([-+\d.Ee]+)", tail)
            record["raw_final_TOTEN_eV"] = float(energies[-1]) if energies else None
            record["raw_scalar_match"] = bool(energies and abs(float(energies[-1]) - reference["numeric_value"]) <= 1e-8)
            sources.bound.add(path)
        else:
            record["raw_scalar_match"] = None
        rows.append(record)
    return {"existing_barriers": snapshot["ts_barriers"], "anchors": rows,
            "no_new_barrier_or_TS_acceptance": True}


def chco_labels(sources):
    folder = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/local_triplet_review_20261112_v1"
    inventory = load_json_object(folder / "remote_inventory.json")
    energies = load_json_object(folder / "local_energy_force_review.json")
    rows = []
    for image in (f"{i:02d}" for i in range(1, 7)):
        path = folder / "raw" / image / "OUTCAR"
        expected = next(x["sha256"] for x in inventory["files"] if x["relative_path"] == image + "/OUTCAR")
        geometry = folder / "raw" / image / "CONTCAR"
        atoms = read(geometry, format="vasp")
        sources.index[expected] = [{"paths": {"OUTCAR": str(path), "INCAR": str(folder / "raw/INCAR"),
                                               "KPOINTS": str(folder / "raw/KPOINTS")},
                                     "evidence": str(folder / "remote_inventory.json"), "POTCAR_sha256": None}]
        source = sources.get(expected, len(atoms))
        frame = [f for f in source["frames"] if "forces_eV_per_A" in f and "toten_eV" in f][-1]
        energy = next(r["final_OUTCAR_TOTEN_eV"] for r in energies["energy_rows"] if r["image"] == image)
        row = {"sample_id": "job9994246_image" + image + "_opt207", "source_job_id": "9994246",
               "source_OUTCAR_sha256": expected, "ionic_step": frame["ionic_step"],
               "structure_sha256": sha256_file(geometry), "forces_eV_per_A": frame["forces_eV_per_A"],
               "toten_eV_force_label_only": energy, "electronic_converged": True, "geometry_review_pass": True,
               "composition": "C2HO", "magnetic_review_level": "SOURCE_PATH_REVIEW_NOT_LOCAL_MAGNETIC_ADMISSION"}
        record = inspect_row({"row": row, "pool": "documented_CH_CO_C_C_coupling_path", "partition": "unassigned_external",
                              "metadata": folder / "local_energy_force_review.json", "structure": geometry}, sources)
        record.update(chemical_event="C-C formation with CO;not automatically CO insertion",
                      reaction_id="CH_plus_CO_to_CHCO", source_parent_job="9994246",
                      permitted_use="EXISTING_PATH_DIAGNOSTIC_NOT_FORMAL_TS;TRAINING_MAGNETIC_REVIEW_REQUIRED",
                      force_definition="raw TOTAL-FORCE atomic vectors;not NEB projected/spring force",
                      final_barrier_available=False, role_assignment_changed=False)
        rows.append(record)
    sources.bound.update([folder / "remote_inventory.json", folder / "local_energy_force_review.json",
                          folder / "collection_receipt.json", folder / "reaction_contract.reviewed.json"])
    return {"labels": rows, "scalar_energy_profile": energies["energy_rows"],
            "endpoint_scalars_not_force_labels_on_symmetry_mapped_geometry": True,
            "no_new_TS_or_barrier_acceptance": True}


def run():
    sources = Sources()
    snapshot = load_json_object(OUT / "registry_ts_snapshot.json")
    dependencies = load_json_object(OUT / "registry_dependency_snapshot.json")
    statics = static_labels(sources, snapshot)
    print({"C_H_static_labels": len(statics), "protected": sum(r["protected_TS_validation"] for r in statics)}, flush=True)
    anchors = accepted_anchors(snapshot, dependencies, sources)
    chco = chco_labels(sources)
    sources.bound.update([Path(__file__), OUT / "registry_ts_snapshot.json", OUT / "registry_dependency_snapshot.json"])
    write_json_exclusive(OUT / "reaction_source_sidecar.json", {
        "status": "READ_ONLY_DOCUMENTED_REACTION_EVIDENCE_NOT_NEW_ADMISSION",
        "C_H_static_labels": statics, "registered_energy_references": anchors, "CH_CO_path": chco,
        "source_files": source_file_manifest(sorted(sources.bound)), "new_calculations": False})
    print({"registered_barriers": len(anchors["existing_barriers"]), "scalar_anchors": len(anchors["anchors"]),
           "CH_CO_force_frames": len(chco["labels"])}, flush=True)


if __name__ == "__main__":
    run()
