"""Recover existing first-step path labels before proposing duplicate statics."""
from __future__ import annotations

from pathlib import Path
import re

from ase.io import read
import yaml

from archive.fe110_10b_lowforce_20261023.legacy_helpers import verify_frame
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.artifact_io import load_json_object, sha256_bytes, sha256_file, source_file_manifest, write_json_exclusive
from .collect_sources import BASE, OUT, ROOT
from .audit import SLAB
from .geometry import geometry_report


def first_frame(path, natoms):
    frame = {"ionic_step": 1, "EDIFF_marker_before_force": False, "local_moment_tables": []}
    with path.open("rb") as handle:
        while handle.tell() < 16 * 1024**2:
            offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            iteration = re.search(rb"Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)", line)
            if iteration:
                if int(iteration[1]) != 1:
                    break
                frame["electronic_iteration"] = int(iteration[2])
            if b"aborting loop because EDIFF is reached" in line:
                frame["EDIFF_marker_before_force"] = True
            if b"TOTAL-FORCE (eV/Angst)" in line:
                raw = line + handle.readline()
                rows, tokens = [], []
                for _ in range(natoms):
                    data = handle.readline()
                    raw += data
                    values = data.split()
                    rows.append([float(v) for v in values[:6]])
                    tokens.append([v.decode() for v in values[:3]])
                frame.update(positions_A=[r[:3] for r in rows], forces_eV_per_A=[r[3:] for r in rows],
                             position_tokens=tokens, source_byte_range=[offset, handle.tell()],
                             raw_force_table_sha256=sha256_bytes(raw))
            if b"free  energy   TOTEN" in line and "forces_eV_per_A" in frame:
                frame["E_TOTEN_eV"] = float(line.split()[4])
                return frame
    raise ValueError("bounded first-frame extraction incomplete;do not infer a missing DFT calculation")


def run():
    side = BASE / "energy_reaction_sidecar_20261113_v1/reaction_source_sidecar.json"
    old = load_json_object(side)
    path_root = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
    slab = read_poscar(SLAB)
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    pairs_path = ROOT / "configs/fe110_reico_pilot/geometry_v1.json"
    pairs = load_json_object(pairs_path)["pair_minimum_A"]
    rows, bound = [], {Path(__file__), side, rules_path, pairs_path, SLAB}
    for original in old["CH_CO_path"]["labels"]:
        image = original["sample_id"].split("_image")[1][:2]
        outcar = Path(original["source_OUTCAR_path"])
        geometry = path_root / "vasp_ordinary_neb_20261110_v1" / image / "POSCAR"
        if sha256_file(outcar) != original["source_OUTCAR_sha256"]:
            raise ValueError("existing NEB output changed")
        atoms = read(geometry, format="vasp")
        frame = first_frame(outcar, len(atoms))
        verify_frame(atoms, frame)  # Owning printed-coordinate-precision and fixed-mask check.
        geo = geometry_report(read_poscar(geometry), slab, rules, pairs)
        rows.append({"candidate_id": "job9994246_image" + image + "_opt001", "source_kind": "EXISTING_DFT_PATH_FIRST_STEP",
                     "structure_path": str(geometry), "structure_sha256": sha256_file(geometry),
                     "OUTCAR_path": str(outcar), "OUTCAR_sha256": original["source_OUTCAR_sha256"],
                     "DFT_ionic_step": 1, "source_byte_range": frame["source_byte_range"],
                     "raw_force_table_sha256": frame["raw_force_table_sha256"],
                     "coordinate_force_precision_check": True, "EDIFF_marker_before_force": frame["EDIFF_marker_before_force"],
                     "raw_atomic_force_definition": "first TOTAL-FORCE atomic table;not NEB spring/projected force",
                     "geometry": geo, "monitored_bond_atoms_1based": [46, 47],
                     "monitored_C_C_distance_A": float(atoms.get_distance(45, 46, mic=True)),
                     "chemical_event": "C46-C47 formation from reviewed parent contract;no formal TS grade inferred",
                     "compatibility_evidence": original["compatibility"],
                     "magnetic_scope": "parent six outputs previously lack atom-resolved moments;no new magnetic admission",
                     "proposed_role": "WHOLE_CHCO_PATH_TRAINING_REVIEW_NOT_INDEPENDENT_VALIDATION",
                     "new_DFT_for_existing_coordinate": 0, "new_training_admission": False})
        bound.update([outcar, geometry])
    paper = load_json_object(OUT / "existing_paper_label_sources_v3.json")
    write_json_exclusive(OUT / "reaction_path_reuse_audit.json", {
        "newly_bound_existing_first_steps": rows, "existing_last_step_labels": old["CH_CO_path"]["labels"],
        "existing_C_H_labels": old["C_H_static_labels"], "additional_paper_physical_labels": paper["records"],
        "total_physical_label_references": len(rows) + len(old["CH_CO_path"]["labels"]) + len(old["C_H_static_labels"]) + len(paper["records"]),
        "protected_C_H_validation_labels": sum(r["protected_TS_validation"] for r in old["C_H_static_labels"]),
        "new_DFT_needed_to_obtain_these_existing_forces": 0,
        "no_new_barrier_TS_training_or_magnetic_admission": True,
        "source_files": source_file_manifest(sorted(bound | {OUT / "existing_paper_label_sources_v3.json"}))})
    print({"new_existing_first_steps_bound": len(rows), "C_C_distances_A": [r["monitored_C_C_distance_A"] for r in rows],
           "EDIFF_markers": sum(r["EDIFF_marker_before_force"] for r in rows), "new_DFT": 0}, flush=True)


if __name__ == "__main__":
    run()
