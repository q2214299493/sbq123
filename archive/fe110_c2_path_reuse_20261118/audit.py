"""Read existing C2 path labels; write a separate audit, never label admission."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re

import numpy as np
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import verify_frame
from archive.fe110_c2_c4_joint_candidates_20261114.geometry import iron_maps, nearest, packed_pose
from archive.fe110_grouped_qc_20261026.review import magnetic_status, raw_frames
from archive.fe110_joint_priority_20261117.analyze import BASE, ROOT, SLAB, guard_hashes, load, save, sha, table
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.vasp_result_gate import read_incar_values

CHCO = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
SOURCE = BASE / "c2_c4_joint_candidates_20261114_v1/reaction_path_reuse_audit.json"
RUN = BASE / "c2_path_reuse_20261118_v1"
EXPECTED_TITLES = ["PAW_PBE Fe 06Sep2000", "PAW_PBE C 08Apr2002", "PAW_PBE O 08Apr2002", "PAW_PBE H 15Jun2001"]


def magnetic_decision(tables, natoms):
    if not tables:
        return {"magnetic_review_level": "NO_LOCAL_MOMENT_TABLE", "local_moment_table_count": 0,
                "Fe_moment_range_muB": None, "local_magnetization_muB": None,
                "magnetic_global_ground_state_verified": False}
    return magnetic_status(tables, natoms)


def classification(row):
    if not row["coordinate_force_match"] or not row["electronic_pass"] or not row["compatibility_pass"]:
        return "BLOCKED_SOURCE_OR_COMPATIBILITY"
    if row["magnetic"]["magnetic_review_level"] != "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE":
        return "DIAGNOSTIC_REUSE_ONLY_MAGNETIC_BLOCKED"
    if row["protected_overlap"]:
        return "BLOCKED_TRAINING_PROTECTED_SOURCE"
    return "FORCE_REUSE_REVIEW_CANDIDATE_NO_NEW_DFT"


def compatibility(directory, outcar, pot_sha, expected_pot, atoms):
    values = read_incar_values(directory / "INCAR")
    kp = (directory / "KPOINTS").read_text(encoding="utf8").splitlines()
    with outcar.open("rb") as stream:
        header = stream.read(90000).decode("ascii", errors="replace")
    observed = {}
    for key in ("ENCUT", "ISPIN", "ISMEAR", "SIGMA", "EDIFF", "LORBIT", "NUPDOWN", "NELECT", "LDIPOL", "LDAU"):
        match = re.search(r"\b" + key + r"\s*=\s*([^\s;]+)", header)
        observed[key] = match.group(1) if match else None
    titles = re.findall(r"TITEL\s*=\s*([^\r\n]+)", header)
    titles = [title.strip() for title in titles]
    fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
    same_cell = bool(np.allclose(atoms.cell, read_poscar(SLAB).cell, rtol=0, atol=1e-6))
    numeric = {"ENCUT": 400., "ISPIN": 2., "ISMEAR": 1., "SIGMA": .2}
    checks = {key: float(values.get(key, "nan")) == expected and float(observed.get(key) or "nan") == expected
              for key, expected in numeric.items()}
    checks.update(GGA=str(values.get("GGA", "")).upper() == "PE", kmesh=kp[2].lower().startswith("g") and kp[3].split() == ["5", "5", "1"],
                  kshift=len(kp) < 5 or all(float(v) == 0 for v in kp[4].split()),
                  fixed_mask=fixed == list(range(18)), same_cell=same_cell,
                  symbols=atoms.get_chemical_symbols() == ["Fe"] * 45 + ["C", "C", "O", "H"],
                  POTCAR=pot_sha == expected_pot, POTCAR_titles=titles == EXPECTED_TITLES,
                  LDIPOL=str(observed["LDIPOL"]).strip(".").upper() in ("F", "FALSE"), NUPDOWN=float(observed["NUPDOWN"] or "nan") == -1,
                  neutral_electrons=abs(float(observed["NELECT"] or "nan") - 375.) < 1e-6)
    return {"checks": checks, "pass": all(checks.values()), "INCAR": values, "OUTCAR_observed": observed,
            "POTCAR_titles": titles, "POTCAR_sha256": pot_sha, "kpoints": kp,
            "fixed_indices_0based": fixed, "EDIFF_is_stage_specific_not_mixed_energy_acceptance": True}


def collect_specs(source, bound):
    sources = []
    for key in ("newly_bound_existing_first_steps", "existing_last_step_labels"):
        for row in source[key]:
            sources.append({"id": row.get("candidate_id", row.get("sample_id")), "kind": key,
                            "structure": Path(row["structure_path"]), "outcar": Path(row.get("OUTCAR_path", row.get("source_OUTCAR_path"))),
                            "out_sha": row.get("OUTCAR_sha256", row.get("source_OUTCAR_sha256")), "step": row["DFT_ionic_step"],
                            "original": row})
    for row in source["additional_paper_physical_labels"]:
        label_path = Path(row["label_path"])
        if sha(label_path) != row["label_sha256"]:
            raise ValueError("old label review changed")
        label = load(label_path)
        sources.append({"id": f"paper_round{row['round_index']:03d}", "kind": "additional_paper_physical_labels",
                        "structure": Path(row["structure"]["path"]), "outcar": Path(row["outcar"]["path"]),
                        "out_sha": row["outcar"]["sha256"], "step": 1, "original": row, "label": label})
        bound.add(label_path)
    return sources


def read_references(operations, maps):
    """Read frozen isolation sources without invoking older report-writing helpers."""
    config_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    config = load(config_path)
    prior = ROOT / config["prior_manifest"]
    catalogs = [ROOT / p for p in config["reserved_geometry_catalogs"]]
    reserved = reserved_geometries(load(ROOT / config["inventory"]), load(prior), prior.parent, catalogs)
    package = BASE / "combined_force_package_20261113_v1"
    manifest_path = package / "training_manifest.json"
    manifest = load(manifest_path)
    bound = {config_path, prior, manifest_path, ROOT / config["inventory"], *catalogs}
    references = {"train536": [], "protected": []}
    items = [("protected", r["sample_id"], Path(r["structure_path"])) for r, _ in reserved]
    for split, rows in manifest["splits"].items():
        items.extend(("train536" if split == "train" else "protected", row["sample_id"], package / row["structure_path"]) for row in rows)
    items.extend(("protected", row["sample_id"], package / row["structure_path"]) for row in manifest["quarantined_observed_heldout"])
    seen = set()
    for kind, sid, path in items:
        bound.add(path)
        if (kind, path) in seen:
            continue
        seen.add((kind, path))
        pose = read_poscar(path)
        if pose.symbols != ["Fe", "C", "O", "H"] or pose.counts != [45, 2, 1, 1]:
            continue
        references[kind].append({**packed_pose(pose, operations, maps), "id": sid, "source": str(path)})
    return references, bound


def validate_paper_label(spec, forces, frame, bound):
    if "label" not in spec:
        return None
    if not np.array_equal(forces, np.asarray(spec["label"]["forces_eV_per_A"])):
        raise ValueError("reviewed force vectors differ from raw OUTCAR")
    if abs(spec["label"]["dft_toten_eV_force_label_only"] - frame["toten_eV"]) > 1e-8:
        raise ValueError("reviewed energy differs from raw OUTCAR")
    evidence = spec["label"]["scheduler_evidence"]
    path = Path(evidence["path"])
    if sha(path) != evidence["sha256"]:
        raise ValueError("paper process evidence bytes changed")
    bound.add(path)
    return {"scheduler": evidence["scheduler"], "job_id": evidence["job_id"],
            "recorded_state": evidence.get("scheduler_terminal_state"), "source_path": str(path),
            "controller_exit_status": evidence.get("controller_exit_status"),
            "kind": evidence["document_kind"], "backend": evidence["backend_id"]}


def run(destination, smoke=False):
    before = guard_hashes()
    source = load(SOURCE)
    submission_path = CHCO / "vasp_ordinary_neb_20261110_v1/submission_record.json"
    expected_pot = load(submission_path)["potcar_sha256"]
    index_path = BASE / "energy_reaction_sidecar_20261113_v1/raw_source_index.json"
    original_pot = load(index_path)["entries"]["b78aef511cd9afc3b4d9dc1c7d0fe514fa9ad9b63c0c25d58654d3624a8ba2ab"][0]["POTCAR_sha256"]
    if expected_pot != original_pot:
        raise ValueError("POTCAR differs from frozen training reference")
    bound = {SOURCE, submission_path, index_path, Path(__file__), SLAB, ROOT / "configs/true_fe110_production.yaml"}
    sources = collect_specs(source, bound)
    if smoke:
        sources = [sources[0], sources[6], sources[12]]
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    references, ref_bound = read_references(operations, iron_maps(slab, operations))
    bound.update(ref_bound)
    cache, rows = {}, []
    scheduler_path = CHCO / "local_triplet_review_20261112_v1/ordinary_neb_scheduler_evidence.json"
    scheduler = load(scheduler_path)
    validate_stored_lsf_evidence(scheduler, required_status="DONE")
    if scheduler["job_id"] != "9994246":
        raise ValueError("scheduler job mismatch")
    bound.add(scheduler_path)
    for spec in sources:
        outcar, structure = spec["outcar"], spec["structure"]
        bound.update([outcar, structure])
        if outcar not in cache:
            if sha(outcar) != spec["out_sha"]:
                raise ValueError("OUTCAR hash changed")
            frames = raw_frames(outcar, 49)
            directory = outcar.parent if spec["kind"] == "additional_paper_physical_labels" else outcar.parent.parent
            pot = outcar.parent / "POTCAR"
            pot_sha = sha(pot) if pot.is_file() else expected_pot
            # The NEB hash is submission-bound; no fabricated local POTCAR content.
            if pot.is_file():
                bound.add(pot)
            atoms = read(structure, format="vasp")
            comp = compatibility(directory, outcar, pot_sha, expected_pot, atoms)
            oszicar = outcar.parent / "OSZICAR"
            osz = parse_oszicar(oszicar)
            with outcar.open("rb") as stream:
                stream.seek(max(0, outcar.stat().st_size - 12000))
                normal = b"General timing and accounting" in stream.read()
            cache[outcar] = {"frames": frames, "compatibility": comp, "oszicar": osz, "normal": normal}
            bound.update([directory / "INCAR", directory / "KPOINTS", oszicar])
        item = cache[outcar]
        frame = next(f for f in item["frames"] if f["ionic_step"] == spec["step"])
        atoms = read(structure, format="vasp")
        forces = verify_frame(atoms, frame)
        paper_scheduler = validate_paper_label(spec, forces, frame, bound)
        comp = item["compatibility"]
        protected = nearest(read_poscar(structure), references["protected"])
        train = nearest(read_poscar(structure), references["train536"])
        mags = item["oszicar"].get("magnetization_history_muB", [])
        if len(mags) != len(item["frames"]):
            raise ValueError("ionic total magnetization mapping incomplete")
        magnetic = magnetic_decision(frame["local_moment_tables"], len(atoms))
        original = spec["original"]
        if spec["kind"] == "newly_bound_existing_first_steps" and sha(structure) != original["structure_sha256"]:
            raise ValueError("first-step coordinates changed")
        if "structure" in original and sha(structure) != original["structure"]["sha256"]:
            raise ValueError("paper coordinates changed")
        scheduler_info = {"scheduler": "LSF", "job_id": "9994246", "recorded_state": "DONE", "source_path": str(scheduler_path)}
        if paper_scheduler is not None:
            scheduler_info = paper_scheduler
        row = {"id": spec["id"], "kind": spec["kind"], "source_family": "CH_CO_to_CHCO_shared_reaction_not_independent_validation",
               "structure_path": str(structure), "structure_sha256": sha(structure), "OUTCAR_path": str(outcar),
               "OUTCAR_sha256": spec["out_sha"], "ionic_step": spec["step"], "physical_key": spec["out_sha"] + ":" + str(spec["step"]),
               "force_table_byte_range": frame["source_byte_range"], "force_table_sha256": __import__("hashlib").sha256(frame["raw_force_table"]).hexdigest(),
               "coordinate_force_match": True, "force_definition": "raw TOTAL-FORCE, not NEB projected/spring force",
               "electronic_iteration": frame["electronic_iteration"], "EDIFF_marker": frame["EDIFF_marker_before_force"],
               "electronic_pass": bool(frame["EDIFF_marker_before_force"] and frame["electronic_iteration"] < float(comp["INCAR"]["NELM"]) and item["normal"]),
               "normal_completion": item["normal"], "compatibility": comp, "compatibility_pass": comp["pass"],
               "total_magnetization_muB": mags[spec["step"] - 1], "magnetic": magnetic,
               "C_C_distance_A": float(atoms.get_distance(45, 46, mic=True)), "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
               "TOTEN_eV_diagnostic_only": frame["toten_eV"], "nearest_train536": train, "nearest_protected": protected,
               "protected_overlap": protected.get("minimum_ads_pose_RMSD_A_any_reference") is not None and protected["minimum_ads_pose_RMSD_A_any_reference"] <= .20,
               "scheduler_evidence": scheduler_info, "original_force_only_scope_preserved": original.get("original_force_only_eligibility_preserved", False),
               "independent_validation_eligible": False, "new_training_admission": False, "new_DFT_submitted": False}
        row["disposition"] = classification(row)
        row["same_coordinate_force_diagnostic_requires_new_DFT"] = not (row["coordinate_force_match"] and row["electronic_pass"] and row["compatibility_pass"])
        rows.append(row)
        print({"reviewed": len(rows), "id": row["id"], "magnetic": magnetic["magnetic_review_level"], "compatibility": comp["pass"]}, flush=True)
    after = guard_hashes()
    if before != after:
        raise ValueError("frozen input guard changed")
    summary = {"references": len(rows), "unique_physical_keys": len({r["physical_key"] for r in rows}),
               "dispositions": dict(Counter(r["disposition"] for r in rows)), "all_source_compatible": all(r["compatibility_pass"] for r in rows),
               "same_coordinate_diagnostic_DFT_avoided": sum(not r["same_coordinate_force_diagnostic_requires_new_DFT"] for r in rows),
               "automatic_training_admissions": 0, "new_compute": 0}
    destination.mkdir(exist_ok=False, parents=True)
    # Bind original bytes only; no serialization of upstream hash-bound evidence.
    bindings = {str(p): sha(p) for p in sorted(bound)}
    save(destination / "audit.json", {"summary": summary, "records": rows, "source_hashes": bindings,
                                      "frozen_before": before, "frozen_after": after, "smoke": smoke})
    columns = [(k, label) for k, label in [("id", "结构ID"), ("kind", "来源组"), ("structure_path", "坐标来源"),
               ("OUTCAR_path", "原始输出"), ("physical_key", "物理标签键"), ("ionic_step", "离子帧"),
               ("C_C_distance_A", "CC距离_A"), ("movable_fmax_eV_A", "可动原子最大力_eV_A"),
               ("total_magnetization_muB", "总磁矩_muB"), ("magnetic", "局域磁性证据"), ("compatibility_pass", "数值分支兼容"),
               ("disposition", "复用结论"), ("same_coordinate_force_diagnostic_requires_new_DFT", "诊断需新DFT"),
               ("nearest_protected", "保护来源隔离"), ("new_training_admission", "新增训练准入")]]
    table(destination / "C2路径标签磁性兼容性.csv", rows, columns)
    print(summary, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    run(arguments.output, arguments.smoke)
