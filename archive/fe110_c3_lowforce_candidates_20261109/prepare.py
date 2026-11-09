"""Materialize an independent candidate package; never train, submit or register."""
from __future__ import annotations

import argparse
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import zlib

import numpy as np
import yaml
from ase.io import read, write

from scripts.artifact_io import sha256_file, source_file_manifest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
FROZEN = BASE / "combined_force_package_20261027_v3"
OUTPUT = BASE / "c3_lowforce_candidates_20261109_v1"
STEPS = (15, 82, 84, 90, 91, 92, 97, 99, 104, 106, 110, 114,
         115, 116, 118, 119, 121, 123, 124, 125, 126, 128, 131, 133)
BOUNDARIES = {"is_training_package": False, "training_authorized": False,
              "merged_into_existing_manifest": False, "accepted_endpoint": False,
              "reportable_final_energy": False, "model_promoted": False}
REMOTE = r'''
import base64,hashlib,json,subprocess,zlib
from pathlib import Path
root=Path.home()/'sbq/Fe110/reico_c3_continue_20261027_v1/family_0099_step020_from9922624'
files={}
for name,cap in [('OUTCAR',67108864),('XDATCAR',8388608),('OSZICAR',1048576),
                 ('POSCAR',1048576),('CONTCAR',1048576),('INCAR',1048576),
                 ('KPOINTS',1048576),('script.lsf',1048576)]:
 p=root/name;before=p.stat()
 if before.st_size>cap:raise ValueError('bounded source read exceeded: '+name)
 with p.open('rb') as f:data=f.read(cap+1)
 after=p.stat()
 if len(data)!=before.st_size or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
  raise ValueError('source changed during read: '+name)
 files[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
              'payload':base64.b64encode(zlib.compress(data)).decode()}
h=hashlib.sha256()
with (root/'POTCAR').open('rb') as f:
 for block in iter(lambda:f.read(1048576),b''):h.update(block)
argv=['bjobs','-a','-w','9924387'];p=subprocess.run(argv,capture_output=True,timeout=15)
print(json.dumps({'job_id':'9924387','server_alias':'sunboquan-codex','remote_directory':str(root),
 'files':files,'POTCAR_sha256':h.hexdigest(),'scheduler_query':{'argv':argv,'returncode':p.returncode,
 'stdout_base64':base64.b64encode(p.stdout).decode(),'stderr_base64':base64.b64encode(p.stderr).decode()}}))
'''


def save_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("preserve changed existing artifact: " + str(path))
        return
    with path.open("xb") as handle:
        handle.write(data)


def save_json(path, value):
    save_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def frozen_hashes():
    return {name: sha256_file(FROZEN / name) for name in
            ("training_manifest.json", "train.db", "development.db", "train_metadata.npz", "development_metadata.npz")}


def check_boundaries(document):
    if any(document.get(key) is not value for key, value in BOUNDARIES.items()):
        raise ValueError("candidate-only boundary changed")
    if document.get("force_unit") != "eV/Angstrom":
        raise ValueError("unexpected force unit")


def collect(output):
    receipt = output / "source_collection.json"
    if receipt.exists():
        result = load(receipt)
        for name, info in result["files"].items():
            if sha256_file(output / "source" / name) != info["sha256"]:
                raise ValueError("collected source changed: " + name)
        return result
    proc = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
         "sunboquan-codex", "python3 -B -"], input=REMOTE.encode(), capture_output=True, timeout=60)
    if proc.returncode:
        raise RuntimeError("read-only collection failed: " + proc.stderr.decode(errors="replace")[:1000])
    result = json.loads(proc.stdout)
    for name, item in result["files"].items():
        content = zlib.decompress(base64.b64decode(item.pop("payload"), validate=True))
        save_bytes(output / "source" / name, content)
        if len(content) != item["bytes"] or sha256_file(output / "source" / name) != item["sha256"]:
            raise ValueError("remote/local byte binding failed: " + name)
    query = result["scheduler_query"]
    for stream in ("stdout", "stderr"):
        path = output / "source" / ("scheduler." + stream + ".txt")
        save_bytes(path, base64.b64decode(query.pop(stream + "_base64"), validate=True))
        query[stream + "_sha256"] = sha256_file(path)
    # Missing history is recorded truthfully, never manufactured as DONE.
    result["terminal_scheduler_status"] = None
    result["terminal_scheduler_evidence_recovered"] = False
    save_bytes(output / "provenance/collection_program.py", REMOTE.encode())
    save_json(receipt, result)
    return result


def inputs(output, collected):
    from scripts.vasp_result_gate import read_incar_values

    source = output / "source"
    submitted = BASE / "c3_continuation_20261027_v1/inputs"
    for name in ("POSCAR", "INCAR", "KPOINTS"):
        if (source / name).read_bytes() != (submitted / name).read_bytes():
            raise ValueError("submitted input changed: " + name)
    values = read_incar_values(source / "INCAR")
    expected = {"ENCUT": 400, "ISPIN": 2, "ISMEAR": 1, "SIGMA": .2, "EDIFF": 1e-5, "EDIFFG": -.02, "ISIF": 2}
    if any(float(values[k]) != v for k, v in expected.items()) or values["GGA"] != "PE":
        raise ValueError("incompatible physical branch")
    if values["LDIPOL"].strip(".").upper() not in ("F", "FALSE"):
        raise ValueError("dipole policy changed")
    if collected["POTCAR_sha256"] != "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85":
        raise ValueError("POTCAR family/order binding changed")
    return values


def audit_frames(output, collected):
    from archive.fe110_10b_lowforce_20261023.legacy_helpers import restore_input_lattice, verify_frame
    from archive.fe110_10b_lowforce_20261023.review import scf_for_frame
    from archive.fe110_grouped_qc_20261026.review import geometry, magnetic_status, raw_frames
    from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar

    source = output / "source"
    values = inputs(output, collected)
    initial = read(source / "POSCAR", format="vasp")
    out = parse_outcar(source / "OUTCAR")
    if not out["normal_completion"] or not out["reached_required_accuracy"] or out["fatal_keywords"] or out["run_index"] != 1:
        raise ValueError("source is not one normally completed, converged VASP run")
    frames = raw_frames(source / "OUTCAR", 51)
    trajectory = read(source / "XDATCAR", format="vasp-xdatcar", index=":")
    independent = read(source / "OUTCAR", format="vasp-out", index=":")
    osz = parse_oszicar(source / "OSZICAR")
    if not len(frames) == len(trajectory) == len(independent) == osz["ionic_steps"] == 133:
        raise ValueError("source frame identity/count differs")
    cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"]}
    if set(cycles) != set(range(1, 134)) or len(osz["magnetization_history_muB"]) != 133:
        raise ValueError("noncontiguous electronic/magnetic identities")
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    rows, atoms_by_step, tables = [], {}, {}
    for frame, atoms, cross in zip(frames, trajectory, independent, strict=True):
        restore_input_lattice(atoms, initial, source / "XDATCAR")
        atoms.set_constraint(initial.constraints)
        atoms.pbc = [True, True, False]
        forces = verify_frame(atoms, frame)
        if not np.array_equal(forces, cross.get_forces(apply_constraint=False)):
            raise ValueError("ASE independent raw force mismatch")
        if not np.allclose(cross.positions, frame["positions_A"], atol=1e-10, rtol=0):
            raise ValueError("ASE force-coordinate mismatch")
        step = frame["ionic_step"]
        if (abs(frame["toten_eV"] - osz["energies"][step - 1]) > 1e-4
                or abs(frame["toten_eV"] - cross.get_potential_energy(force_consistent=True)) > 1e-8):
            raise ValueError("source energy metadata mismatch")
        mag = magnetic_status(frame["local_moment_tables"], 51)
        geo = geometry(atoms, initial, rules)
        if mag["magnetic_review_flags"] or geo["adsorbate_component_count"] != 1:
            raise ValueError("magnetic/connected-C3 review failed")
        row = {"sample_id": f"family_0099_step020_job9924387_opt{step:03d}", "family_id": "family_0099",
               "source_seed": "family_0099_step020", "source_job_id": "9924387", "parent_job_id": "9922624",
               "calculation_group": "reico_family_0099", "partition": "train", "split": "train",
               "origin": "expanded_closed_trajectory", "ionic_step": step, "source_total_steps": 133,
               "symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18)),
               "forces_eV_per_A": forces.tolist(), "energy_eV_force_label_only": frame["toten_eV"],
               "toten_eV_force_label_only": frame["toten_eV"], "source_OUTCAR_sha256": collected["files"]["OUTCAR"]["sha256"],
               "source_XDATCAR_sha256": collected["files"]["XDATCAR"]["sha256"],
               "source_force_byte_range": frame["source_byte_range"], "electronic_converged": True,
               "geometry_review_pass": True, "data_qc_status": "PASS", "parent_ionic_converged": True,
               "composition": "C3H2O", "force_unit": "eV/Angstrom", "accepted_endpoint": False,
               "training_authorized": False, "reportable_final_energy": False,
               "SCF": scf_for_frame(frame, cycles[step], values),
               "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
               "total_magnetization_muB": osz["magnetization_history_muB"][step - 1], **mag, **geo}
        rows.append(row)
        atoms_by_step[step], tables[step] = atoms, frame["raw_force_table"]
    if len({r["graph_signature"] for r in rows}) != 1:
        raise ValueError("chemical graph changed")
    verify_frame(read(source / "CONTCAR", format="vasp"), frames[-1])
    return rows, atoms_by_step, tables


def isolate_and_select(output, rows, atoms):
    from collections import Counter
    from archive.fe110_10b_lowforce_20261023.legacy_helpers import collapse_redundant, pose_distance, pose_variants
    from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar
    from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
    from scripts.adsorption.reico_dataset_audit import reserved_geometries
    from scripts.adsorption.reico_selection import frame_distance

    cfg = load(ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json")
    prior = ROOT / cfg["prior_manifest"]
    inventory = load(ROOT / cfg["inventory"])
    reserved = reserved_geometries(inventory, load(prior), prior.parent, [ROOT / p for p in cfg["reserved_geometry_catalogs"]])
    manifest = load(FROZEN / "training_manifest.json")
    protected = manifest["splits"]["development"] + manifest["splits"]["heldout"] + manifest["quarantined_observed_heldout"]
    if len(reserved) != 513 or not {r["structure_sha256"] for r in protected} <= {r["structure_sha256"] for r, _ in reserved}:
        raise ValueError("protected geometry scope changed")
    if {r["partition"] for r in inventory["frames"] if r["family_id"] == "family_0099"} != {"train"}:
        raise ValueError("parent family is not training-only")
    operations = surface_pose_symmetries(read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"))
    base = read_poscar(output / "source/POSCAR")
    variants = []
    for ref, other in reserved:
        if sha256_file(Path(ref["structure_path"])) != ref["structure_sha256"]:
            raise ValueError("reserved source changed")
        if Counter(other.get_chemical_symbols()) == Counter(rows[0]["symbols"]):
            variants.append((ref["sample_id"], pose_variants(read_poscar(Path(ref["structure_path"])), operations)))
    for row in rows:
        pose = Poscar("", base.cell, base.symbols, base.counts, atoms[row["ionic_step"]].get_scaled_positions(wrap=False), base.flags)
        distance, name = min((pose_distance(pose, v), name) for name, v in variants)
        row.update(reserved_min_RMSD_A=distance, nearest_reserved_id=name)
        if distance <= .20:
            raise ValueError("reserved geometry isolation conflict")
    kept, redundant = collapse_redundant(sorted(rows, key=lambda r: -r["ionic_step"]),
        lambda a, b: frame_distance(atoms[a["ionic_step"]], atoms[b["ionic_step"]]))
    selected = sorted((r for r in kept if r["movable_fmax_eV_A"] <= .05), key=lambda r: r["ionic_step"])
    if tuple(r["ionic_step"] for r in selected) != STEPS:
        raise ValueError("reviewed24 selection differs; requires fresh review")
    save_json(output / "isolation_review.json", {"reserved_geometries": len(reserved), "same_composition": len(variants),
        "surface_symmetries": len(operations), "comparisons": len(rows) * len(variants), "conflicts": [],
        "threshold_A": .20, "reserved_forces_or_energies_used": False, "current78_53_16_covered": True,
        "minimum_RMSD_A": min(r["reserved_min_RMSD_A"] for r in rows)})
    save_json(output / "deduplication_review.json", {"geometry_threshold_A": .02, "maximum_atom_force_delta_eV_A": .02,
        "all_source_frames": len(rows), "same_job_retained": len(kept), "redundant": redundant,
        "selected_steps": list(STEPS), "selection_is_not_independent_minimum_count": True})
    return selected


def materialize(output, selected, atoms, tables):
    from scripts.adsorption.force_finetune import validate_label_row

    for row in selected:
        step, sid = row["ionic_step"], row["sample_id"]
        buffer = io.StringIO()
        write(buffer, atoms[step], format="vasp", direct=True, vasp5=True)
        row["structure_path"] = f"structures/{sid}.vasp"
        save_bytes(output / row["structure_path"], buffer.getvalue().encode())
        row["structure_sha256"] = sha256_file(output / row["structure_path"])
        row["structure_equivalence_sha256"] = row["structure_sha256"]
        row["raw_force_table_path"] = f"force_tables/{sid}.txt"
        save_bytes(output / row["raw_force_table_path"], tables[step])
        row["source_force_table_sha256"] = sha256_file(output / row["raw_force_table_path"])
    label_path = output / "labels/source_labels.json"
    save_json(label_path, {"samples": selected, **BOUNDARIES})
    linked = copy.deepcopy(selected)
    for row in linked:
        row["label_source"] = {"path": "labels/source_labels.json", "sha256": sha256_file(label_path), "sample_id": row["sample_id"]}
        validate_label_row(output, row)
    manifest = {"document_kind": "reviewed_force_label_candidates", "schema_version": 1,
                "source_job_id": "9924387", "samples": linked, "force_unit": "eV/Angstrom", **BOUNDARIES}
    check_boundaries(manifest)
    save_json(output / "candidate_manifest.json", manifest)


def run(output=OUTPUT):
    output = Path(output).resolve()
    if output == FROZEN.resolve() or output.is_relative_to(FROZEN.resolve()):
        raise ValueError("cannot write inside the frozen512 package")
    if output.exists() and not (output / "request.json").exists():
        raise ValueError("existing output is not this candidate package")
    before = frozen_hashes()
    request = {"source_job_id": "9924387", "selected_steps": list(STEPS), "force_unit": "eV/Angstrom",
               "frozen512_before": before, "purpose": "independent force candidate binding and review", **BOUNDARIES}
    save_json(output / "request.json", request)
    collected = collect(output)
    rows, atoms, tables = audit_frames(output, collected)
    selected = isolate_and_select(output, rows, atoms)
    save_json(output / "all_frame_qc.json", {"frames": [{k: v for k, v in r.items() if k != "forces_eV_per_A"} for r in rows],
        "frame_count": len(rows), "SCF_geometry_magnetic_PASS": len(rows), "is_training_package": False})
    materialize(output, selected, atoms, tables)
    if frozen_hashes() != before:
        raise ValueError("frozen512 files changed during candidate assembly")
    save_json(output / "frozen512_verification.json", {"before": before, "after": frozen_hashes(), "unchanged": True})
    dependencies = [Path(__file__), Path(__file__).with_name("verify.py"),
        ROOT / "archive/fe110_grouped_qc_20261026/review.py", ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
        ROOT / "archive/fe110_10b_lowforce_20261023/review.py", ROOT / "scripts/adsorption/force_finetune.py",
        ROOT / "scripts/adsorption/reico_selection.py", ROOT / "configs/adsmind_lite/analysis_rules.yaml"]
    save_json(output / "implementation_binding.json", {"source_files": source_file_manifest(dependencies)})
    save_json(output / "package_summary.json", {"source_frames": len(rows), "candidate_frames": len(selected),
        "selected_steps": list(STEPS), "manifest_sha256": sha256_file(output / "candidate_manifest.json"),
        "terminal_scheduler_status": None, "separate_candidate_review_required": True,
        "force_unit": "eV/Angstrom", **BOUNDARIES})
    return {"source_frames": len(rows), "candidate_frames": len(selected), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.output)))


if __name__ == "__main__":
    main()
