"""Reuse the reviewed trajectory reader for four closed current adsorption jobs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import inspect
import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
import yaml
from ase.io import read, write

from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import (
    REMOTE_READER, selected_steps, verify_frame,
)
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, equivalent_pose_rmsd, surface_pose_symmetries
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
DEST = BASE / "adsorption_calibration_20261018_v1/current_trajectories"
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6"
SPLITS = {"06_C": "train", "07_B": "train", "08_A": "train", "08_B": "development"}


def reader_source(records: list[dict]) -> str:
    # The historical campaign contained48/49 atoms; this campaign has49/50.
    # Keep the proven electronic-cycle/force/energy streaming association;
    # validate the exact submitted count instead of inheriting the old count.
    old = "len(rows) not in (48,49)"
    if REMOTE_READER.count(old) != 1:
        raise ValueError("reviewed reader version changed")
    reader = REMOTE_READER.replace(old, "len(rows)!=record['atom_count']")
    old_output = "'normal_completion':True,'files':files"
    if reader.count(old_output) != 1:
        raise ValueError("reviewed reader output changed")
    reader = reader.replace(old_output, "'normal_completion':True,'files':files,'POTCAR_sha256':hashlib.sha256((root/'POTCAR').read_bytes()).hexdigest()")
    selection = inspect.getsource(selected_steps)
    return "RECORDS=" + repr(records) + "\n" + selection + reader


def collect() -> None:
    DEST.mkdir(parents=True, exist_ok=False)
    original = json.loads((BASE / "vasp_batch_v1/submission_summary.json").read_text(encoding="utf-8"))["records"]
    records = [{**r, "split": SPLITS[r["name"]],
                "atom_count": len(expanded_symbols(read_poscar(Path(r["workdir"]) / "POSCAR")))}
               for r in original if r["name"] in SPLITS]
    if {r["name"] for r in records} != set(SPLITS):
        raise ValueError("missing source job")
    code = reader_source(records)
    write_json_exclusive(DEST / "collection_request.json", {"records": records,
        "source_reader_sha256": hashlib.sha256(REMOTE_READER.encode()).hexdigest(),
        "executed_reader_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "split_unit": "whole_VASP_job", "training_authorized": False, "new_calculation": False})
    with (DEST / "remote_extraction.jsonl").open("xb") as output, (DEST / "collection_stderr.txt").open("xb") as errors:
        process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                                    "sunboquan-codex", "python3 -"], stdin=subprocess.PIPE, stdout=output, stderr=errors)
        process.stdin.write(code.encode())
        process.stdin.close()
        timed_out = False
        try:
            exit_code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait()
    write_json_exclusive(DEST / "collection_receipt.json", {"exit_code": exit_code,
        "output_sha256": sha256_file(DEST / "remote_extraction.jsonl"),
        "status": "COLLECTED" if not exit_code else "FAILED_READ_ONLY_COLLECTION",
        "timed_out": timed_out, "new_calculation": False})
    if exit_code:
        raise RuntimeError("read-only collection failed; preserve sources and receipt")


def check_inputs(folder: Path, record: dict) -> None:
    for name in ("POSCAR", "INCAR", "KPOINTS"):
        if sha256_file(folder / name) != sha256_file(Path(record["workdir"]) / name):
            raise ValueError("submitted input changed: " + name)
    values = read_incar_values(folder / "INCAR")
    expected = {"ENCUT": 400, "ISPIN": 2, "ISMEAR": 1, "SIGMA": .2,
                "EDIFF": 1e-5, "EDIFFG": -.02, "ISIF": 2}
    if any(float(values[key]) != target for key, target in expected.items()) or values["GGA"] != "PE":
        raise ValueError("incompatible production branch")
    if values["LDIPOL"].strip(".").upper() not in ("FALSE", "F"):
        raise ValueError("dipole convention changed")
    moments = [float(value) for term in values["MAGMOM"].split()
               for value in ([term.split("*")[1]] * int(term.split("*")[0]) if "*" in term else [term])]
    if moments != [2.2] * 45 + [0.] * (record["atom_count"] - 45):
        raise ValueError("magnetic initialization changed")
    k = (folder / "KPOINTS").read_text().splitlines()
    if k[1].strip() != "0" or not k[2].lower().startswith("g") or k[3].split() != ["5", "5", "1"]:
        raise ValueError("kmesh changed")
    if any(float(value) for value in k[4].split()):
        raise ValueError("kmesh offset changed")


def restore_input_lattice(atoms, initial, xdatcar: Path) -> None:
    """ISIF2 keeps the input cell; XDATCAR prints only six lattice decimals."""
    with xdatcar.open(encoding="utf-8") as handle:
        header = [handle.readline() for _ in range(5)]
    scale = float(header[1])
    if scale <= 0:
        raise ValueError("unsupported XDATCAR lattice scale")
    bounds = np.asarray([[.5 * 10.0 ** Decimal(token).as_tuple().exponent
                          for token in line.split()] for line in header[2:5]]) * scale
    if bounds.shape != (3, 3) or np.any(np.abs(np.asarray(atoms.cell) - np.asarray(initial.cell)) > bounds + 1e-12):
        raise ValueError("XDATCAR cell differs beyond its printed precision")
    atoms.set_cell(initial.cell, scale_atoms=True)


def read_collection(allow_partial: bool = False) -> tuple[list, list]:
    receipt = json.loads((DEST / "collection_receipt.json").read_bytes())
    if (receipt["exit_code"] and not allow_partial) or receipt["output_sha256"] != sha256_file(DEST / "remote_extraction.jsonl"):
        raise ValueError("unverified collection")
    source = DEST / "remote_extraction.jsonl"
    if source.stat().st_size > 15000000:
        raise ValueError("collection payload size cap")
    docs = [json.loads(line) for line in source.read_bytes().splitlines()]
    names = [doc["record"]["name"] for doc in docs]
    if len(names) != len(set(names)) or not set(names).issubset(SPLITS) or not names:
        raise ValueError("unexpected or duplicate source job")
    if set(names) != set(SPLITS) and not allow_partial:
        raise ValueError("source jobs incomplete")
    for doc in docs:
        if (doc["normal_completion"] is not True
                or [frame["ionic_step"] for frame in doc["frames"]] != selected_steps(doc["total_steps"])):
            raise ValueError("incomplete per-job output")
    return docs, sorted(set(SPLITS) - set(names))


def prepare(allow_partial: bool = False) -> None:
    docs, missing = read_collection(allow_partial)
    if allow_partial:
        write_json_exclusive(DEST / "partial_recovery_review.json", {
            "source_receipt_sha256": sha256_file(DEST / "collection_receipt.json"),
            "source_payload_sha256": sha256_file(DEST / "remote_extraction.jsonl"),
            "policy": "reuse only complete per-job outputs with closed-source hashes; not batch success or execution authority",
            "available_jobs": [doc["record"]["name"] for doc in docs], "missing_jobs": missing,
            "remote_retry": False, "new_calculation": False})
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    clean = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    samples = []
    for doc in docs:
        record = doc["record"]
        if doc["POTCAR_sha256"] != record["potcar_sha256"]:
            raise ValueError("POTCAR source changed")
        folder = DEST / "sources" / record["name"]
        folder.mkdir(parents=True, exist_ok=False)
        for name, encoded in doc["files"].items():
            if name not in {"POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR"}:
                raise ValueError("unexpected source filename")
            (folder / name).write_bytes(base64.b64decode(encoded, validate=True))
        check_inputs(folder, record)
        initial = read(folder / "POSCAR", format="vasp")
        trajectory = read(folder / "XDATCAR", index=":", format="vasp-xdatcar")
        osz = parse_oszicar(folder / "OSZICAR")
        cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"] if c["complete"]}
        if len(trajectory) != doc["total_steps"]:
            raise ValueError("trajectory indexing mismatch")
        intended = sorted(connectivity(read_poscar(folder / "POSCAR"), list(range(45, len(initial)))))
        for frame in doc["frames"]:
            step = frame["ionic_step"]
            if not frame["EDIFF_marker_before_force"] or cycles[step]["iteration"] != frame["electronic_iteration"]:
                raise ValueError("SCF/force association failed")
            if frame["electronic_iteration"] >= int(read_incar_values(folder / "INCAR")["NELM"]):
                raise ValueError("SCF limit exhausted")
            atoms = trajectory[step - 1]
            restore_input_lattice(atoms, initial, folder / "XDATCAR")
            atoms.set_constraint(initial.constraints)
            atoms.pbc = [True, True, False]
            if atoms.get_chemical_symbols() != initial.get_chemical_symbols() or not np.allclose(atoms.cell, initial.cell):
                raise ValueError("trajectory order/cell changed")
            forces = verify_frame(atoms, frame)
            if abs(frame["toten_eV"] - osz["energies"][step - 1]) > 1e-4:
                raise ValueError("ionic-frame energy association failed")
            sid = record["name"] + "_step" + str(step).zfill(3)
            path = DEST / "structures" / (sid + ".vasp")
            path.parent.mkdir(exist_ok=True)
            write(path, atoms, format="vasp", direct=True, vasp5=True)
            pose = read_poscar(path)
            distances = atoms.get_all_distances(mic=True)
            np.fill_diagonal(distances, np.inf)
            minimum = float(distances.min())
            same_graph = sorted(connectivity(pose, list(range(45, len(atoms))))) == intended
            # Fixed layers anchor the physical frame; no COM/height fitting.
            fixed_delta = pose.frac[:18] - clean.frac[:18]
            fixed_delta[:, :2] -= np.round(fixed_delta[:, :2])
            fixed_ok = float(np.abs(fixed_delta @ clean.cell).max()) < 1e-7
            if not np.allclose(pose.cell, clean.cell, atol=1e-8, rtol=0):
                raise ValueError("clean-slab branch changed")
            table = folder / (sid + "_force_table.txt")
            table.write_bytes(base64.b64decode(frame["force_table_base64"], validate=True))
            samples.append({"sample_id": sid, "source_job_id": record["job_id"], "source_name": record["name"],
                "split": record["split"], "ionic_step": step, "source_total_steps": doc["total_steps"],
                "structure_path": path.relative_to(DEST).as_posix(), "structure_sha256": sha256_file(path),
                "symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18)),
                "forces_eV_per_A": forces.tolist(), "toten_eV_force_label_only": frame["toten_eV"],
                "source_OUTCAR_sha256": doc["OUTCAR_sha256"], "source_force_table_sha256": sha256_file(table),
                "source_XDATCAR_sha256": sha256_file(folder / "XDATCAR"), "electronic_converged": True,
                "cell_precision_handling": "ISIF2 input lattice restored after checking XDATCAR printing bounds",
                "total_magnetization_muB": osz["magnetization_history_muB"][step - 1]
                    if len(osz["magnetization_history_muB"]) == doc["total_steps"] else None,
                "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
                "minimum_pair_distance_A": minimum, "original_graph_preserved": same_graph,
                "adsorbate_nearest_Fe": [{"atom_index_0based": i, "symbol": atoms[i].symbol,
                    "Fe_index_0based": int(np.argmin(distances[i, :45])),
                    "distance_A": float(distances[i, :45].min())} for i in range(45, len(atoms))],
                "C_O_distances_A": [{"C_index_0based": i, "O_index_0based": j, "distance_A": float(distances[i, j])}
                    for i in range(45, len(atoms)) for j in range(45, len(atoms))
                    if atoms[i].symbol == "C" and atoms[j].symbol == "O"],
                "fixed_coordinates_preserved": fixed_ok,
                "geometry_review_pass": same_graph and fixed_ok and minimum >= rules["contact_validation"]["hard_contact_distance_angstrom"],
                "accepted_endpoint": False, "reportable_energy": False, "training_authorized": False})
    write_json_exclusive(DEST / "dataset_review.json", {"samples": samples,
        "counts": dict(Counter(s["split"] for s in samples)), "whole_job_splits": SPLITS,
        "source_collection_sha256": sha256_file(DEST / "remote_extraction.jsonl"),
        "status": "PARTIAL_LABEL_POOL_NOT_TRAINING_PACKAGE" if missing else "LABEL_POOL_PENDING_SPLIT_REVIEW_NOT_TRAINING",
        "missing_requested_jobs": missing, "collection_completed": not missing,
        "heldout_count": 0, "prior_16_heldout_unchanged": True, "new_calculation": False})
    print(json.dumps({"counts": dict(Counter(s["split"] for s in samples)),
                      "geometry_pass": sum(s["geometry_review_pass"] for s in samples)}))


def review_splits() -> None:
    dataset = json.loads((DEST / "dataset_review.json").read_bytes())
    old = json.loads((OLD / "training_manifest.json").read_bytes())
    rows = []
    for split, samples in old["splits"].items():
        rows.extend({"id": "old/" + s["sample_id"], "split": split, "new": False,
                     "pose": read_poscar(OLD / s["structure_path"])} for s in samples)
    rows.extend({"id": s["sample_id"], "split": s["split"], "new": True,
                 "pose": read_poscar(DEST / s["structure_path"])} for s in dataset["samples"] if s["geometry_review_pass"])
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    ops = surface_pose_symmetries(slab)
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    tolerance = rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    priority = {"train": 0, "development": 1, "heldout": 2}
    pairs, excluded = [], {}
    for index, a in enumerate(rows):
        for b in rows[index + 1:]:
            if a["split"] == b["split"] or not (a["new"] or b["new"]):
                continue
            if expanded_symbols(a["pose"]) != expanded_symbols(b["pose"]):
                continue
            distance = equivalent_pose_rmsd(a["pose"], b["pose"], ops, remove_height_shift=False)
            if distance > tolerance:
                continue
            pairs.append({"first": a["id"], "second": b["id"], "surface_adsorbate_RMSD_A": distance})
            lower = a if priority[a["split"]] < priority[b["split"]] else b
            if not lower["new"]:
                # Do not retrospectively edit the already-trained source manifest.
                raise ValueError("new validation overlaps data already used by2185: " + repr(pairs[-1]))
            excluded.setdefault(lower["id"], []).append(b["id"] if lower is a else a["id"])
    retained = [s for s in dataset["samples"] if s["geometry_review_pass"] and s["sample_id"] not in excluded]
    write_json_exclusive(DEST / "split_review.json", {"source_dataset_sha256": sha256_file(DEST / "dataset_review.json"),
        "prior_manifest_sha256": sha256_file(OLD / "training_manifest.json"), "near_threshold_A": tolerance,
        "metric": "real clean-slab symmetries,xyPBC,H permutations; absolute height retained; no COM or Kabsch fit",
        "cross_split_near_pairs": pairs, "excluded_new_frames": excluded,
        "retained_sample_ids": [s["sample_id"] for s in retained],
        "retained_counts": dict(Counter(s["split"] for s in retained)),
        "prior_heldout_unchanged": True, "training_authorized": False, "checkpoint_updated": False,
        "new_pool_is_independent_heldout": False})
    print(json.dumps({"cross_split_pairs": len(pairs), "excluded": len(excluded),
                      "retained_counts": dict(Counter(s["split"] for s in retained))}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "prepare", "prepare-available", "review-splits"))
    args = parser.parse_args()
    {"collect": collect, "prepare": prepare, "prepare-available": lambda: prepare(True),
     "review-splits": review_splits}[args.action]()


if __name__ == "__main__":
    main()
