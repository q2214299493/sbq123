"""Energy provenance and permitted-use sidecar. No data admission or computation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import verify_frame
from archive.fe110_grouped_qc_20261026.review import magnetic_status, raw_frames
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.vasp_result_gate import read_incar_values
from .collect import BASE, OUT, PACKAGE, ROOT

CLEAN = ROOT / "calculations/true_fe110_clean_20260629/POSCAR"
CLEAN_CELL = read(CLEAN, format="vasp").cell
RULES = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))["connectivity"]


def source_rows():
    manifest = load_json_object(PACKAGE / "training_manifest.json")
    rows = []
    for split, samples in [*manifest["splits"].items(), ("quarantine", manifest["quarantined_observed_heldout"])]:
        for row in samples:
            rows.append({"pool": "frozen536", "partition": split, "row": row, "root": PACKAGE,
                         "metadata": PACKAGE / "training_manifest.json", "structure": PACKAGE / row["structure_path"]})
    for relative in ("grouped_qc_20261026_v2/candidate_labels.json",
                     "final30_qc_20261025_v1/all_selected_label_qc_local_only.json"):
        path = BASE / relative
        for row in load_json_object(path)["samples"]:
            row = dict(row)  # Schema adapter in this sidecar only; original JSON bytes remain frozen.
            if not row.get("source_OUTCAR_sha256"):
                row["source_OUTCAR_sha256"] = row.get("input_output_hashes", {}).get("OUTCAR")
            structure = Path(row["structure_path"])
            structure = structure if structure.is_absolute() else path.parent / structure
            rows.append({"pool": path.parent.name, "partition": row.get("partition", row.get("split")),
                         "row": row, "root": path.parent, "metadata": path, "structure": structure})
    return rows


class Sources:
    def __init__(self):
        self.index = load_json_object(OUT / "raw_source_index.json")["entries"]
        self.remote = {r["OUTCAR_sha256"]: r for r in load_json_object(OUT / "remote_raw_evidence.json")["results"] if r.get("expected_hash_matches")}
        self.cache = {}
        self.bound = set()

    def get(self, digest, natoms):
        if digest in self.cache:
            return self.cache[digest]
        if digest in self.remote:
            item = self.remote[digest]
            path = OUT / "source_views" / (digest + "_INCAR.decoded.txt")
            path.parent.mkdir(exist_ok=True)
            if not path.exists():
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(item["inputs"].get("INCAR", ""))
            value = {"frames": item["frames"], "parameters": read_incar_values(path),
                     "kpoints": item["inputs"].get("KPOINTS", ""), "potcar_sha256": item.get("POTCAR_sha256"),
                     "potcar_titles": item.get("POTCAR_titles", []), "normal_completion": item["normal_completion"],
                     "source": "remote_exact_hash_read_only", "OUTCAR_path": item["directory"] + "/OUTCAR"}
            self.bound.add(OUT / "remote_raw_evidence.json")
        else:
            candidates = self.index.get(digest, [])
            local = next((x for x in candidates if Path(x["paths"]["OUTCAR"]).is_file()), None)
            if local is None:
                self.cache[digest] = None
                return None
            path = Path(local["paths"]["OUTCAR"])
            if sha256_file(path) != digest:
                self.cache[digest] = {"error": "cached_OUTCAR_hash_changed"}
                return self.cache[digest]
            frames = raw_frames(path, natoms)
            incar = Path(local["paths"].get("INCAR", path.parent / "INCAR"))
            kp = Path(local["paths"].get("KPOINTS", path.parent / "KPOINTS"))
            with path.open("rb") as handle:
                header = handle.read(18000)
                handle.seek(max(0, path.stat().st_size - 12000))
                tail = handle.read()
            value = {"frames": frames, "parameters": read_incar_values(incar) if incar.is_file() else {},
                     "kpoints": kp.read_text(encoding="utf-8") if kp.is_file() else "",
                     "potcar_sha256": local.get("POTCAR_sha256"),
                     "potcar_titles": [s.decode(errors="replace").strip() for s in header.splitlines() if b"TITEL" in s],
                     "normal_completion": b"General timing and accounting" in tail,
                     "source": "local_exact_hash", "OUTCAR_path": str(path)}
            self.bound.update(p for p in (path, incar, kp) if p.is_file())
        self.cache[digest] = value
        return value


def number(parameters, name):
    try:
        return float(parameters[name].split()[0])
    except (KeyError, ValueError):
        return None


def branch(source, atoms):
    parameters = source["parameters"]
    kpoints = source["kpoints"].splitlines()
    mesh = None
    if len(kpoints) >= 4:
        tokens = kpoints[3].split()
        if len(tokens) == 3 and all(v.isdigit() for v in tokens):
            mesh = [int(v) for v in tokens]
    cell_matches = bool(np.allclose(atoms.cell, CLEAN_CELL, atol=1e-9, rtol=0))
    values = {k: number(parameters, k) for k in ("ENCUT", "ISPIN", "ISMEAR", "SIGMA", "EDIFF", "NELM")}
    active = (values["ENCUT"] == 400 and values["ISPIN"] == 2 and values["ISMEAR"] == 1
              and values["SIGMA"] == .2 and str(parameters.get("GGA", "")).strip().upper() == "PE"
              and mesh == [5, 5, 1] and cell_matches
              and bool(source["potcar_titles"]) and all("PAW_PBE" in title for title in source["potcar_titles"]))
    return {"active_PBE_Fe45_sigma0p20_branch_observed": bool(active), "parameters": values,
            "GGA": parameters.get("GGA"), "MAGMOM_seed": parameters.get("MAGMOM"), "kmesh": mesh,
            "same_clean_cell": cell_matches, "POTCAR_sha256": source["potcar_sha256"],
            "POTCAR_titles": source["potcar_titles"], "input_branch_is_not_global_magnetic_ground_state_proof": True}


def frame_for(row, source):
    complete = [x for x in source["frames"] if "forces_eV_per_A" in x and "toten_eV" in x]
    if len(complete) == 1:
        return complete[0]
    return next((x for x in complete if x["ionic_step"] == int(row.get("ionic_step", -1))), None)


def inspect_row(item, sources):
    row = item["row"]
    result = {"sample_id": row["sample_id"], "pool": item["pool"], "partition": item["partition"],
              "source_job_id": row.get("source_job_id"), "family_id": row.get("family_id"),
              "source_collection": row.get("source_collection"), "source_OUTCAR_sha256": row.get("source_OUTCAR_sha256"),
              "source_sample_step": row.get("ionic_step"), "composition": row.get("composition", row.get("formula_without_slab")),
              "E_TOTEN_eV": row.get("toten_eV_force_label_only", row.get("energy_eV_force_label_only")),
              "energy_definition": "VASP_free_energy_TOTEN", "energy_unit": "eV", "force_unit": "eV/Angstrom",
              "original_magnetic_grade_preserved": row.get("magnetic_review_level", "original_QC_fields_only"),
              "metadata_path": str(item["metadata"]), "structure_path": str(item["structure"]),
              "metadata_electronic_converged": row.get("electronic_converged"),
              "metadata_QC_status": row.get("data_qc_status"), "flags": [],
              "absolute_AQ_energy_target_ready": False, "new_energy_training_admission": False,
              "reaction_path_identity": "NOT_ASSIGNED_FROM_FORMULA_OR_FORCE_MAGNITUDE"}
    if not item["structure"].is_file():
        result["flags"].append("SOURCE_STRUCTURE_RECOVERY_REQUIRED")
        return result
    if sha256_file(item["structure"]) != row["structure_sha256"]:
        raise ValueError("source geometry hash changed: " + row["sample_id"])
    atoms = read(item["structure"], format="vasp")
    result["graph"] = chemical_environment(atoms, RULES) if len(atoms) > 45 else {"graph_signature": "CLEAN_SLAB_NO_ADSORBATE"}
    if item["pool"] == "frozen536":
        label = item["root"] / row["label_source"]["path"]
        if sha256_file(label) != row["label_source"]["sha256"]:
            raise ValueError("frozen label source hash changed")
        original = next(r for r in load_json_object(label)["samples"] if r["sample_id"] == row["label_source"]["sample_id"])
        energy = original.get("toten_eV_force_label_only", original.get("energy_eV_force_label_only"))
        if energy != result["E_TOTEN_eV"] or original["forces_eV_per_A"] != row["forces_eV_per_A"]:
            raise ValueError("label energy/forces differ from archived source")
        sources.bound.add(label)
    source = sources.get(row.get("source_OUTCAR_sha256"), len(atoms))
    if source is None or source.get("error"):
        result["flags"].append("EXISTING_RAW_SOURCE_RECOVERY_REQUIRED_NOT_NEW_DFT")
        return result
    result["source_OUTCAR_path"] = source["OUTCAR_path"]
    frame = frame_for(row, source)
    if frame is None:
        result["flags"].append("EXACT_IONIC_FRAME_RECOVERY_REQUIRED")
        return result
    result["DFT_ionic_step"] = frame["ionic_step"]
    result["source_byte_range"] = frame["source_byte_range"]
    result["raw_TOTEN_eV"] = frame["toten_eV"]
    try:
        actual = verify_frame(atoms, frame)
        result["coordinate_force_match"] = bool(np.array_equal(actual, np.asarray(row["forces_eV_per_A"])))
    except (ValueError, KeyError):
        result["coordinate_force_match"] = False
    result["energy_match"] = result["E_TOTEN_eV"] is not None and abs(frame["toten_eV"] - result["E_TOTEN_eV"]) <= 1e-8
    parameters = source["parameters"]
    nelm = number(parameters, "NELM")
    result["electronic_raw_pass"] = bool(frame.get("EDIFF_marker_before_force") and nelm
                                          and frame["electronic_iteration"] < nelm)
    result["normal_completion"] = source["normal_completion"]
    result["compatibility"] = branch(source, atoms)
    moments = magnetic_status(frame["local_moment_tables"], len(atoms)) if frame["local_moment_tables"] else {}
    result["raw_magnetic_grade"] = moments.get("magnetic_review_level", "NO_LOCAL_MOMENT_TABLE")
    result["raw_positive_Fe_local_moments"] = result["raw_magnetic_grade"] == "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"
    for name in ("coordinate_force_match", "energy_match", "electronic_raw_pass", "normal_completion", "raw_positive_Fe_local_moments"):
        if not result[name]:
            result["flags"].append(name.upper() + "_REVIEW_REQUIRED")
    if not result["compatibility"]["active_PBE_Fe45_sigma0p20_branch_observed"]:
        result["flags"].append("COMPATIBILITY_REVIEW_REQUIRED")
    if row.get("electronic_converged") is not True or row.get("geometry_review_pass") is not True:
        result["flags"].append("SOURCE_QC_EXCLUSION_PRESERVED")
    result["energy_force_evidence_ready_for_review"] = not result["flags"]
    result["physical_label_key"] = row["source_OUTCAR_sha256"] + ":" + str(frame["ionic_step"])
    return result


def roles_and_groups(records):
    groups = defaultdict(list)
    for row in records:
        partition = row["partition"]
        if partition == "quarantine":
            row["permitted_use"] = "QUARANTINE_NO_TRAINING"
        elif partition in ("development", "heldout", "final_test"):
            row["permitted_use"] = "RESERVED_PARTITION_ONLY_NO_TRAINING"
        elif row.get("metadata_QC_status") not in (None, "PASS"):
            row["permitted_use"] = "SOURCE_QC_REJECTED_NO_TRAINING"
        elif row.get("energy_force_evidence_ready_for_review"):
            row["permitted_use"] = "RELATIVE_ENERGY_REUSE_CANDIDATE_REQUIRES_NEW_CONTRACT_AND_REVIEW"
        else:
            row["permitted_use"] = "EXISTING_LABEL_NEEDS_EVIDENCE_REVIEW_DO_NOT_RECOMPUTE_YET"
        row["new_DFT_action"] = "NO_DUPLICATE_SINGLE_POINT;resolve_existing_evidence_first"
        if row.get("energy_force_evidence_ready_for_review"):
            # Restrict differences to one output trajectory; no cross-branch or cross-composition mixing.
            group = row["source_OUTCAR_sha256"]
            groups[group].append(row)
    summaries = []
    for group, rows in groups.items():
        unique = {r["physical_label_key"]: r for r in rows}
        summaries.append({"group_id": group, "scope": "same_OUTCAR_only", "unique_frames": len(unique),
                          "sample_ids": sorted({r["sample_id"] for r in rows}),
                          "relative_energy_pairs_available": len(unique) >= 2,
                          "anchor_key_suggested_not_training_label": sorted(unique)[0]})
    return summaries


def run(smoke=False):
    sources = Sources()
    items = source_rows()
    if smoke:
        chosen = []
        for collection in ("reviewed_original_statics119_20261025", "reviewed_reico_statics137",
                           "targeted_trajectory16_20261026", "c3_lowforce24_job9924387_20261109", "legacy_control_20261019"):
            chosen.append(next(x for x in items if x["row"].get("source_collection") == collection))
        records = [inspect_row(x, sources) for x in chosen]
        write_json_exclusive(OUT / "smoke5_v2.json", {"records": records, "source_files": source_file_manifest([Path(__file__)])})
        print([(r["sample_id"], r.get("energy_match"), r.get("coordinate_force_match"), r["flags"]) for r in records])
        return
    records = []
    for index, item in enumerate(items):
        records.append(inspect_row(item, sources))
        if index % 100 == 99:
            print({"rows_read": index + 1}, flush=True)
    groups = roles_and_groups(records)
    sources.bound.update(x["metadata"] for x in items)
    sources.bound.update(x["structure"] for x in items if x["structure"].is_file())
    sources.bound.update([Path(__file__), OUT / "raw_source_index.json", OUT / "checkpoint_energy_metadata.json"])
    write_json_exclusive(OUT / "energy_label_sidecar_v2.json", {
        "document_kind": "READ_ONLY_ENERGY_USE_QUALIFICATION_SIDECAR", "status": "EVIDENCE_ONLY_NOT_ADMISSION",
        "records": records, "relative_energy_groups": groups, "original_data_or_partitions_modified": False,
        "new_training_admission": False, "absolute_AQ_energy_target_mapping": "Needs confirmation;checkpoint targets adsorption_energy,not raw TOTEN",
        "source_files": source_file_manifest(sorted(sources.bound))})
    print({"rows": len(records), "ready_by_pool": dict(Counter(r["pool"] for r in records if r.get("energy_force_evidence_ready_for_review"))),
           "frozen536_status": dict(Counter(r["permitted_use"] for r in records if r["pool"] == "frozen536"))}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    run(parser.parse_args().smoke)
