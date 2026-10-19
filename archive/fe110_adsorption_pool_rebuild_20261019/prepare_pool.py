"""Read existing closed VASP jobs and prepare an isolated adsorption data pool."""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import inspect
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from ase.io import read, write

from archive.fe110_adsorption_calibration_20261018.prepare_current_trajectories import check_inputs, restore_input_lattice
from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import REMOTE_READER, verify_frame
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.adsorption.force_finetune import load_manifest
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values

from .roles import ROLE_WEIGHTS, atom_weights, pose_distance, pose_variants, role_groups

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
DEST = BASE / "adsorption_pool_rebuild_20261019_v1"
PREPARED_NAME = "prepared_v2"
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6"
BOUNDARY = BASE / "adsorption_06c_force_comparison_20261019_v1"
SPLITS = {"06_A": "train", "06_B": "train", "06_C": "train", "07_A": "train", "07_B": "train",
          "07_C": "train", "08_A": "train", "08_B": "development", "08_C": "train",
          "09_A": "development", "09_B": "train", "09_C": "heldout", "10_A": "heldout"}


def selected_steps(total):
    if total < 5:
        raise ValueError("trajectory too short")
    return sorted({1, 2, 3, 4, 5, total-1, total,
                   max(1, round(total*.25)), max(1, round(total*.5)), max(1, round(total*.75)),
                   *(round(1+(total-1)*i/15) for i in range(16))})


def reader_source(record: dict, version: int = 2) -> str:
    reader = REMOTE_READER
    changes = {
        "len(rows) not in (48,49)": "len(rows)!=record['atom_count']",
        "if b'reached required accuracy' not in tail or b'General timing and accounting informations' not in tail:":
            "if b'General timing and accounting informations' not in tail:",
        "'normal_completion':True,'files':files": "'normal_completion':True,'files':files,'ionic_converged':b'reached required accuracy' in tail,'POTCAR_sha256':hashlib.sha256((root/'POTCAR').read_bytes()).hexdigest()",
    }
    for old, new in changes.items():
        if reader.count(old) != 1:
            raise ValueError("reviewed reader version changed")
        reader = reader.replace(old, new)
    if version == 2:
        # Preserve byte ranges while avoiding one filesystem tell() per line.
        if reader.count("with out.open('rb') as f:") != 2 or reader.count("f.tell()") != 2:
            raise ValueError("reviewed reader IO layout changed")
        reader = reader.replace("out.open('rb')", "out.open('rb',buffering=1024*1024)")
        reader = reader.replace("  def line():", "  byte_cursor=[0]\n  def line():")
        reader = reader.replace("h.update(value); return value", "h.update(value); byte_cursor[0]+=len(value); return value")
        reader = reader.replace("f.tell()", "byte_cursor[0]")
    elif version != 1:
        raise ValueError("unknown reader version")
    return "RECORDS=" + repr([record]) + "\n" + inspect.getsource(selected_steps) + reader


def source_records() -> list:
    records = json.loads((BASE / "vasp_batch_v1/submission_summary.json").read_bytes())["records"]
    result = []
    for row in records:
        if row["name"] in SPLITS:
            result.append({**row, "split": SPLITS[row["name"]],
                "atom_count": len(expanded_symbols(read_poscar(Path(row["workdir"]) / "POSCAR")))})
    if {r["name"] for r in result} != set(SPLITS):
        raise ValueError("closed-job source map incomplete")
    return result


def verified_collection(record: dict) -> Path | None:
    root = DEST / "raw" / record["name"]
    for folder, version in ((root, 1), (root / "attempt_v2", 2)):
        receipt = folder / "receipt.json"
        if not receipt.exists():
            continue
        old = json.loads(receipt.read_bytes())
        if old["exit_code"]:
            continue
        expected = hashlib.sha256(reader_source(record, version).encode()).hexdigest()
        if old["reader_sha256"] != expected or old["output_sha256"] != sha256_file(folder / "source.json"):
            raise ValueError("successful collection binding changed:" + record["name"])
        return folder
    return None


def collect_one(record: dict) -> dict:
    if verified_collection(record) is not None:
        return {"name": record["name"], "status": "REUSED_VERIFIED_COLLECTION"}
    folder = DEST / "raw" / record["name"] / "attempt_v2"
    folder.mkdir(parents=True, exist_ok=True)
    output, errors, receipt = folder / "source.json", folder / "stderr.txt", folder / "receipt.json"
    code = reader_source(record)
    if receipt.exists() or output.exists() or errors.exists():
        raise FileExistsError("preserved v2 attempt exists;inspect before any further retry")
    with output.open("xb") as stdout, errors.open("xb") as stderr:
        try:
            completed = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3 -"],
                input=code.encode(), stdout=stdout, stderr=stderr, timeout=300, check=False)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    write_json_exclusive(receipt, {"exit_code": exit_code, "reader_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "output_sha256": sha256_file(output), "source_job_id": record["job_id"], "reader_version": 2,
        "timeout_seconds": 300, "remote_mutation": False})
    if exit_code:
        raise RuntimeError("source collection failed:" + record["name"] + ";preserved stderr/receipt")
    return {"name": record["name"], "status": "READ_ONLY_COLLECTED"}


def collect(names: list[str] | None = None) -> None:
    records = source_records()
    DEST.mkdir(exist_ok=True)
    request = DEST / "collection_request.json"
    payload = {"records": records, "selection": "early1-5,equispaced,quartiles,last2;no model-error-dependent test selection",
        "whole_job_splits": SPLITS, "excluded_live_jobs": ["10_B", "10_C"], "training_authorized": False,
        "new_calculation": False, "reader_source_sha256": hashlib.sha256(REMOTE_READER.encode()).hexdigest()}
    if request.exists():
        if json.loads(request.read_bytes()) != payload:
            raise ValueError("frozen collection request changed")
    else:
        write_json_exclusive(request, payload)
    selected = [r for r in records if names is None or r["name"] in names]
    if names and set(names) != {r["name"] for r in selected}:
        raise ValueError("unknown source name")
    repair = DEST / "collection_io_repair_v2.json"
    if not repair.exists():
        previous = []
        for record in records:
            folder = DEST / "raw" / record["name"]
            receipt = folder / "receipt.json"
            previous.append({"name": record["name"], "receipt": json.loads(receipt.read_bytes()) if receipt.exists() else None,
                "state": "RECORDED_ATTEMPT" if receipt.exists() else "INTERRUPTED_NO_RECEIPT" if folder.exists() else "NOT_STARTED",
                "partial_files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in folder.glob("*") if p.is_file()}})
        write_json_exclusive(repair, {"previous_attempts": previous, "reason": "large OUTCAR diagnostic reads exceeded120s;bulk read-only collector stopped",
            "changes": "1MiB buffer,logical byte cursor replacing per-line filesystem tell,sequential reads,300s IO deadline",
            "source_parser_science_changed": False, "successful_v1_reused": True, "original_files_overwritten": False,
            "v2_reader_sha256_by_job": {r["name"]: hashlib.sha256(reader_source(r).encode()).hexdigest() for r in records}})
    for record in selected:
        print(json.dumps(collect_one(record)), flush=True)


def copy_structure(path: Path, output: Path, sid: str) -> tuple[str, str]:
    target = output / "structures" / (sid + ".vasp")
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    shutil.copyfile(path, target)
    return target.relative_to(output).as_posix(), sha256_file(target)


def normalize_energy_metadata(row: dict) -> None:
    """Map a previously source-validated replay value, without changing energy."""
    energy = row["energy_eV_force_label_only"]
    if not np.isfinite(energy):
        raise ValueError("nonfinite force-label energy metadata")
    original = row.get("toten_eV_force_label_only", row.get("final_toten_eV", energy))
    if original != energy:
        raise ValueError("inconsistent force-label energy aliases")
    row["toten_eV_force_label_only"] = energy


def source_name(row: dict) -> str:
    return row.get("source_name", row["calculation_group"])


def prepare_new(output: Path) -> tuple[list, list]:
    rows, rejected = [], []
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    for record in source_records():
        folder = verified_collection(record)
        if folder is None:
            raise ValueError("no successful bound collection:" + record["name"])
        receipt = json.loads((folder / "receipt.json").read_bytes())
        if receipt["exit_code"] or receipt["output_sha256"] != sha256_file(folder / "source.json"):
            raise ValueError("unverified raw collection")
        if (folder / "source.json").stat().st_size > 5000000:
            raise ValueError("per-job payload cap")
        doc = json.loads((folder / "source.json").read_bytes())
        if not doc["normal_completion"] or doc["POTCAR_sha256"] != record["potcar_sha256"] or doc["record"] != record:
            raise ValueError("source binding/normal completion/POTCAR mismatch")
        target = output / "sources" / record["name"]
        target.mkdir(parents=True, exist_ok=False)
        for name, encoded in doc["files"].items():
            if name not in {"POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR"}:
                raise ValueError("unexpected source file")
            (target / name).write_bytes(base64.b64decode(encoded, validate=True))
        check_inputs(target, record)
        initial = read(target / "POSCAR", format="vasp")
        trajectory = read(target / "XDATCAR", index=":", format="vasp-xdatcar")
        osz = parse_oszicar(target / "OSZICAR")
        cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"] if c["complete"]}
        if len(trajectory) != doc["total_steps"] or [f["ionic_step"] for f in doc["frames"]] != selected_steps(doc["total_steps"]):
            raise ValueError("trajectory step association mismatch")
        intended = sorted(connectivity(read_poscar(target / "POSCAR"), list(range(45, len(initial)))))
        for frame in doc["frames"]:
            step = frame["ionic_step"]
            sid = record["name"] + "_step" + str(step).zfill(3)
            cycle = cycles.get(step)
            if (not frame["EDIFF_marker_before_force"] or not cycle or cycle["iteration"] != frame["electronic_iteration"]
                    or frame["electronic_iteration"] >= int(read_incar_values(target / "INCAR")["NELM"])):
                rejected.append({"sample_id": sid, "reason": "electronic_cycle_not_eligible"})
                continue
            atoms = trajectory[step-1]
            restore_input_lattice(atoms, initial, target / "XDATCAR")
            atoms.set_constraint(initial.constraints)
            atoms.pbc = [True, True, False]
            forces = verify_frame(atoms, frame)
            if abs(frame["toten_eV"]-osz["energies"][step-1]) > 1e-4:
                raise ValueError("energy/frame association mismatch")
            distances = atoms.get_all_distances(mic=True)
            np.fill_diagonal(distances, np.inf)
            fixed_delta = atoms.get_scaled_positions(wrap=False)[:18]-slab.frac[:18]
            fixed_delta[:, :2] -= np.round(fixed_delta[:, :2])
            if np.max(np.abs(fixed_delta @ slab.cell)) > 1e-7 or not np.allclose(atoms.cell, slab.cell, atol=1e-8, rtol=0):
                raise ValueError("fixed clean-slab/cell branch changed")
            if distances.min() < rules["contact_validation"]["hard_contact_distance_angstrom"]:
                rejected.append({"sample_id": sid, "reason": "verified_hard_contact"})
                continue
            path = output / "structures" / (sid + ".vasp")
            path.parent.mkdir(exist_ok=True)
            write(path, atoms, format="vasp", direct=True, vasp5=True)
            table = target / (sid + "_force_table.txt")
            table.write_bytes(base64.b64decode(frame["force_table_base64"], validate=True))
            rows.append({"sample_id": sid, "source_name": record["name"], "source_job_id": record["job_id"],
                "calculation_group": "current_vasp_job_" + record["job_id"], "split": record["split"], "origin": "expanded_closed_trajectory",
                "ionic_step": step, "source_total_steps": doc["total_steps"], "structure_path": path.relative_to(output).as_posix(),
                "structure_sha256": sha256_file(path), "symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18)),
                "forces_eV_per_A": forces.tolist(), "energy_eV_force_label_only": frame["toten_eV"], "toten_eV_force_label_only": frame["toten_eV"],
                "source_OUTCAR_sha256": doc["OUTCAR_sha256"], "source_XDATCAR_sha256": sha256_file(target / "XDATCAR"),
                "source_force_table_sha256": sha256_file(table), "electronic_converged": True, "geometry_review_pass": True,
                "total_magnetization_muB": osz["magnetization_history_muB"][step-1] if len(osz["magnetization_history_muB"]) == doc["total_steps"] else None,
                "source_POTCAR_sha256": doc["POTCAR_sha256"],
                "geometry_review_scope": "finite/noncollision/fixed/order/cell diagnostic;changed chemistry retained,not accepted minimum",
                "original_graph_preserved": sorted(connectivity(read_poscar(path), list(range(45, len(atoms))))) == intended,
                "parent_ionic_converged": doc["ionic_converged"], "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
                "stage": "early" if step <= 5 else "last2" if step >= doc["total_steps"]-1 else "middle", "minimum_pair_distance_A": float(distances.min()),
                "accepted_endpoint": False, "reportable_final_energy": False, "training_authorized": False})
    return rows, rejected


def assemble_candidates(output: Path) -> tuple[list, list]:
    old = load_manifest(OLD / "training_manifest.json")
    rows, rejected = prepare_new(output)
    for split, samples in old["splits"].items():
        for original in samples:
            row = copy.deepcopy(original)
            row["sample_id"] = "prior__" + row["sample_id"]
            row["structure_path"], row["structure_sha256"] = copy_structure(OLD / original["structure_path"], output, row["sample_id"])
            row.update(split="observed_heldout" if split == "heldout" else split, origin="prior_reviewed_pool",
                       stage="replay" if "legacy_vasp" in row["calculation_group"] else "prior_trajectory",
                       prior_sample_id=original["sample_id"], prior_split=split,
                       prior_2185_exposure={"train": "weight_updates", "development": "epoch_selection", "heldout": "observed_after_candidate_selection"}[split])
            rows.append(row)
    labels = BOUNDARY / "dataset_review.json"
    if sha256_file(labels) != "7d2846f693b14a577faf509fe0fd2834e94ca9a516281c1a4af6f5f3f1accdff":
        raise ValueError("reviewed boundary labels changed")
    for original in json.loads(labels.read_bytes())["samples"]:
        row = copy.deepcopy(original)
        row["structure_path"], row["structure_sha256"] = copy_structure(BOUNDARY / row["structure_path"], output, row["sample_id"])
        row.update(split="train", origin="actual_ML_failure_boundary", stage="failure_boundary", calculation_group="ML_failure_lineage_06_C",
                   energy_eV_force_label_only=row["toten_eV_force_label_only"], accepted_endpoint=False, reportable_final_energy=False)
        rows.append(row)
    for row in rows:
        normalize_energy_metadata(row)
        atoms = read(output / row["structure_path"], format="vasp")
        row["training_authorized"] = False
        row["force_role_groups"] = role_groups(atoms)
        row["proposed_per_atom_loss_weights"] = atom_weights(row["force_role_groups"], len(atoms)).tolist()
        row["group_radius_A_proposed_not_geometry_gate"] = 3.
        row["structure_equivalence_sha256"] = row["structure_sha256"]
        carbons = [i for i, s in enumerate(row["symbols"]) if s == "C"]
        row["carbon_nearest_Fe_A"] = [min(float(atoms.get_distance(i, j, mic=True)) for j in range(45)) for i in carbons]
        row["C_C_distance_A"] = float(atoms.get_distance(*carbons, mic=True)) if len(carbons) == 2 else None
        row["formula_without_slab"] = atoms[45:].get_chemical_formula()
    return rows, rejected


def collapse_redundant(retained: list, distance) -> tuple[list, list]:
    """Collapse only same-job,near-geometry AND force-similar new frames."""
    redundant, kept = [], []
    for row in retained:
        match = None
        if row["origin"] == "expanded_closed_trajectory":
            for previous in kept:
                if previous["calculation_group"] != row["calculation_group"]:
                    continue
                delta = np.linalg.norm(np.asarray(row["forces_eV_per_A"])[18:]-np.asarray(previous["forces_eV_per_A"])[18:], axis=1).max()
                if delta <= .02 and distance(row, previous) <= .02:
                    match = previous["sample_id"]
                    break
        if match:
            redundant.append({"sample_id": row["sample_id"], "represented_by": match, "reason": "same_job_near_geometry_and_force"})
        else:
            kept.append(row)
    return kept, redundant


def cross_partition_pairs(rows: list, distance, tolerance: float):
    for i, a in enumerate(rows):
        for b in rows[i+1:]:
            if a["split"] != b["split"]:
                rmsd = distance(a, b)
                if rmsd <= tolerance:
                    yield a, b, rmsd


def split_review(rows: list, output: Path) -> tuple[list, list, list]:
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    operations = surface_pose_symmetries(slab)
    tolerance = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    poses = {r["sample_id"]: read_poscar(output / r["structure_path"]) for r in rows}
    variants = {sid: pose_variants(pose, operations) for sid, pose in poses.items()}
    prior = [r for r in rows if r["origin"] == "prior_reviewed_pool"]
    new = [r for r in rows if r["origin"] != "prior_reviewed_pool"]
    excluded, pairs = {}, []
    priority = {"train": 0, "development": 1, "heldout": 2, "observed_heldout": 3}

    def distance(a, b):
        if Counter(a["symbols"]) != Counter(b["symbols"]):
            return float("inf")
        return pose_distance(poses[a["sample_id"]], variants[b["sample_id"]])

    for a, b, rmsd in cross_partition_pairs(prior, distance, tolerance):
        lower = a if priority[a["split"]] < priority[b["split"]] else b
        excluded.setdefault(lower["sample_id"], []).append(b["sample_id"] if lower is a else a["sample_id"])
        pairs.append({"first": a["sample_id"], "second": b["sample_id"], "rmsd_A": rmsd, "reason": "rebuild_prior_pool_with_same_element_permutation_audit"})
    for a in new:
        for b in prior:
            if a["split"] == b["split"]:
                continue
            rmsd = distance(a, b)
            if rmsd <= tolerance:
                excluded.setdefault(a["sample_id"], []).append(b["sample_id"])
                pairs.append({"first": a["sample_id"], "second": b["sample_id"], "rmsd_A": rmsd, "reason": "protect_prior_split_or_prior_checkpoint_exposure"})
    for a, b, rmsd in cross_partition_pairs(new, distance, tolerance):
        if a["sample_id"] in excluded or b["sample_id"] in excluded:
            continue
        lower = a if priority[a["split"]] < priority[b["split"]] else b
        excluded.setdefault(lower["sample_id"], []).append(b["sample_id"] if lower is a else a["sample_id"])
        pairs.append({"first": a["sample_id"], "second": b["sample_id"], "rmsd_A": rmsd, "reason": "new_whole_job_split_protection"})
    retained = [r for r in rows if r["sample_id"] not in excluded]
    # These sampling tolerances are not physical validity gates.
    kept, redundant = collapse_redundant(retained, distance)
    exclusions = [{"sample_id": sid, "neighbors": neighbors, "reason": "cross_split_near_overlap"} for sid, neighbors in excluded.items()]
    return kept, exclusions+redundant, pairs


def prepare() -> None:
    output = DEST / PREPARED_NAME
    failed = DEST / "prepared"
    repair = DEST / "preparation_schema_repair_v2.json"
    if failed.exists() and not repair.exists():
        write_json_exclusive(repair, {"cause": "13 prior canonical-validated replay rows contain energy_eV_force_label_only but no source-catalog TOTEN alias",
            "failed_manifest_sha256": sha256_file(failed / "training_manifest.json"),
            "failed_catalog_sha256": sha256_file(failed / "candidate_labels.json"),
            "repair": "add exact-value TOTEN metadata alias to rebuilt catalog before hashing;do not change scientific parser",
            "failed_package_preserved": True, "energies_forces_structures_changed": False,
            "new_package": PREPARED_NAME, "remote_or_training_action": False})
    output.mkdir(exist_ok=False)
    rows, rejected = assemble_candidates(output)
    kept, excluded, pairs = split_review(rows, output)
    catalog = output / "candidate_labels.json"
    write_json_exclusive(catalog, {"samples": rows, "rejected_frames": rejected, "new_VASP": False, "training_authorized": False})
    for row in kept:
        row["label_source"] = {"path": "candidate_labels.json", "sha256": sha256_file(catalog), "sample_id": row["sample_id"]}
    splits = {name: [r for r in kept if r["split"] == name] for name in ("train", "development", "heldout")}
    if any(not group for group in splits.values()):
        raise ValueError("a new split is empty after leakage protection;review sources,do not weaken protection")
    observed = [r for r in kept if r["split"] == "observed_heldout"]
    if len(observed) != 16:
        raise ValueError("original observed16heldout changed")
    train = splits["train"]
    jobs = {r["calculation_group"] for r in train}
    job_stages = {job: {r["stage"] for r in train if r["calculation_group"] == job} for job in jobs}
    frequencies = Counter((r["calculation_group"], r["stage"]) for r in train)
    for row in train:
        job = row["calculation_group"]
        row["proposed_source_stage_sampling_probability"] = 1. / (len(jobs)*len(job_stages[job])*frequencies[(job, row["stage"])])
    manifest = {"document_kind": "aqcat25_adsorption_force_training_manifest", "schema_version": 1,
        "training_target": "forces_only", "energy_loss_coefficient": 0, "reportable_final_energy": False,
        "splits": splits, "quarantined_observed_heldout": observed, "prior_manifest_sha256": sha256_file(OLD / "training_manifest.json"),
        "training_authorized": False, "model_promoted": False, "new_VASP": False}
    write_json_exclusive(output / "training_manifest.json", manifest)
    load_manifest(output / "training_manifest.json")
    write_reports(output, manifest, rows, rejected, excluded, pairs)


def write_reports(output: Path, manifest: dict, rows: list, rejected: list, excluded: list, pairs: list) -> None:
    splits = manifest["splits"]
    observed = manifest["quarantined_observed_heldout"]
    kept = [r for group in splits.values() for r in group] + observed
    counts = {name: len(group) for name, group in splits.items()}
    report = {"status": "LOCAL_POOL_REVIEW_REQUIRED_NOT_TRAINING_EXECUTABLE", "counts": counts, "candidate_count": len(rows),
        "prior_observed_heldout_preserved": len(observed), "whole_job_splits": SPLITS, "excluded": excluded, "rejected_frames": rejected,
        "cross_split_near_pairs_before_exclusion": pairs, "near_isolation_A": .2, "near_rule_is_physical_acceptance_gate": False,
        "same_element_permutation_scope": "C/H/O for split audit only;stored order and force arrays untouched",
        "stage_counts": {name: dict(Counter(r["stage"] for r in group)) for name, group in splits.items()},
        "source_job_counts": {name: len({r["calculation_group"] for r in group}) for name, group in splits.items()},
        "formula_counts": {name: dict(Counter(r["formula_without_slab"] for r in group)) for name, group in splits.items()},
        "source_frame_counts": {name: dict(Counter(source_name(r) for r in group)) for name, group in splits.items()},
        "chemistry_change_retained": sum(r.get("original_graph_preserved") is False for r in kept),
        "manifest_sha256": sha256_file(output / "training_manifest.json"), "training_authorized": False,
        "limits": ["old16 observed test data are quarantined,not a fresh blind test", "new heldout jobs were previously candidate-screened;not unrestricted chemical extrapolation", "running10B/10C excluded", "sampling tolerances are not physical gates", "no speedup or training effectiveness demonstrated"]}
    write_json_exclusive(output / "pool_review.json", report)
    policy = {"status": "PROPOSED_REVIEW_REQUIRED_NO_TRAINING", "baseline_control": "existing uniform movable-atom force loss",
        "problem_evidence": {"path": str((BOUNDARY / "force_comparison_review.json").relative_to(ROOT)),
            "sha256": sha256_file(BOUNDARY / "force_comparison_review.json")},
        "candidate_objective": "weighted mean of per-role mean force-vector error;exclude fixedFe;do not use fixedC46 index",
        "role_weights_initial_trial_only": ROLE_WEIGHTS, "role_radius_A_initial_trial_only": 3.,
        "sample_balancing": "balance source jobs and early/middle/last/failure/replay strata within train only",
        "checkpoint_selection": "development C and nearbyFe errors plus O/H/replay retention;not overall Fe-dominated mean",
        "retention_review": "use development error scale and relative regressions;no zero-tolerance retention gate or uncalibrated hard threshold",
        "early_stopping": "development learning curve within separately authorized compute budget;not mechanically4epochs",
        "heldout_use": "only final candidate;no gradients,epoch selection or repeated tuning",
        "runtime_integration_required_before_training": True, "training_authorized": False,
        "reference_implementation_scope": "roles.grouped_vector_loss is NumPy QA only;currentFairchem runtime does not consume proposed_* fields",
        "initialization_review": "compare unmodified AQCat25 and2185 on development;choose starting checkpoint without consulting newheldout",
        "scope": "adsorption force correction only;no transfer claim toTS or allFe chemistry",
        "future_acceptance": "same-structure force validation followed by matched-seed,VASP-protocol and final-chemistry steps/time benchmark"}
    write_json_exclusive(output / "training_adjustment_review.json", policy)
    coverage = {}
    for split, samples in splits.items():
        role_values = {role: [] for role in ROLE_WEIGHTS}
        for row in samples:
            norms = np.linalg.norm(np.asarray(row["forces_eV_per_A"]), axis=1)
            for role, indices in row["force_role_groups"].items():
                role_values[role].extend(norms[indices].tolist())
        coverage[split] = {role: {"atom_labels": len(values), "DFT_force_norm_quantiles_eV_A":
            np.quantile(values, [0, .25, .5, .75, 1]).tolist() if values else []} for role, values in role_values.items()}
    write_json_exclusive(output / "label_coverage_review.json", {"scope": "DFT label coverage,not model errors or measured speedup",
        "by_split_and_role": coverage, "force_norm_quantile_order": [0, .25, .5, .75, 1],
        "chemistry_changed_samples": [r["sample_id"] for r in kept if r.get("original_graph_preserved") is False],
        "magnetic_scope": "same approved spin-polarized input branch and converged SCF;global magnetic minimum not established for every frame",
        "training_authorized": False})
    with (output / "pool_inventory.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "split", "source_name", "calculation_group", "ionic_step", "formula", "stage", "movable_fmax_eV_A", "C_C_A", "carbon_nearest_Fe_A", "proposed_train_sampling_probability"])
        for row in kept:
            writer.writerow([row["sample_id"], row["split"], source_name(row), row["calculation_group"], row.get("ionic_step"), row["formula_without_slab"], row["stage"], row.get("movable_fmax_eV_A"), row["C_C_distance_A"], json.dumps(row["carbon_nearest_Fe_A"]), row.get("proposed_source_stage_sampling_probability")])
    print(json.dumps({"status": report["status"], "counts": counts, "observed_heldout": len(observed),
        "excluded": len(excluded), "rejected_frames": len(rejected), "source_jobs": report["source_job_counts"]}, ensure_ascii=False))


def resume_review() -> None:
    """Resume after report-only failure,never regenerate an existing manifest."""
    output = DEST / PREPARED_NAME
    manifest = load_manifest(output / "training_manifest.json")
    catalog = json.loads((output / "candidate_labels.json").read_bytes())
    kept, excluded, pairs = split_review(catalog["samples"], output)
    actual = [r for group in manifest["splits"].values() for r in group] + manifest["quarantined_observed_heldout"]
    if {(r["sample_id"], r["split"]) for r in kept} != {(r["sample_id"], r["split"]) for r in actual}:
        raise ValueError("resumed review differs from existing manifest")
    write_json_exclusive(output / "report_finalization_repair.json", {
        "cause": "prior replay rows use calculation_group provenance but no optional source_name;report-only KeyError",
        "repair": "report source_name falls back to actual calculation_group;resume only after canonical manifest validation",
        "manifest_sha256": sha256_file(output / "training_manifest.json"), "catalog_sha256": sha256_file(output / "candidate_labels.json"),
        "manifest_or_labels_overwritten": False, "remote_or_training_action": False})
    write_reports(output, manifest, catalog["samples"], catalog["rejected_frames"], excluded, pairs)


def verify() -> None:
    output = DEST / PREPARED_NAME
    manifest = load_manifest(output / "training_manifest.json")
    original = load_manifest(OLD / "training_manifest.json")
    observed = manifest["quarantined_observed_heldout"]
    expected = {r["sample_id"]: r for r in original["splits"]["heldout"]}
    if {r["prior_sample_id"] for r in observed} != set(expected):
        raise ValueError("observed heldout membership changed")
    for row in observed:
        old = expected[row["prior_sample_id"]]
        if any(row[key] != old[key] for key in ("structure_sha256", "forces_eV_per_A", "source_OUTCAR_sha256", "calculation_group")):
            raise ValueError("observed heldout label changed")
    rows = [r for group in manifest["splits"].values() for r in group] + observed
    previous24_path = BASE / "adsorption_calibration_20261018_v1/current_trajectories/dataset_review.json"
    if sha256_file(previous24_path) != "fd982424d088e1c4edf699394520108a0825d4fc26e7c0bd06f84cbcfac56d1a":
        raise ValueError("previous24 label source changed")
    previous24 = json.loads(previous24_path.read_bytes())["samples"]
    candidates = {r["sample_id"]: r for r in json.loads((output / "candidate_labels.json").read_bytes())["samples"]}
    for old in previous24:
        new = candidates[old["sample_id"]]
        keys = ("structure_sha256", "forces_eV_per_A", "source_OUTCAR_sha256", "source_force_table_sha256", "source_XDATCAR_sha256")
        if any(new[key] != old[key] for key in keys):
            raise ValueError("previous24 exact labels changed:" + old["sample_id"])
    if not np.isclose(sum(r["proposed_source_stage_sampling_probability"] for r in manifest["splits"]["train"]), 1.):
        raise ValueError("proposed train sampler is not normalized")
    groups = {}
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    operations = surface_pose_symmetries(slab)
    poses, variants = {}, {}
    for row in rows:
        old = groups.setdefault(row["calculation_group"], row["split"])
        if old != row["split"]:
            raise ValueError("whole-job leakage")
        atoms = read(output / row["structure_path"], format="vasp")
        if role_groups(atoms) != row["force_role_groups"] or not np.allclose(atom_weights(row["force_role_groups"], len(atoms)), row["proposed_per_atom_loss_weights"], rtol=0, atol=1e-14):
            raise ValueError("role/weight specification changed")
        pose = read_poscar(output / row["structure_path"])
        poses[row["sample_id"]] = pose
        variants[row["sample_id"]] = pose_variants(pose, operations)
    checked = 0
    for i, a in enumerate(rows):
        for b in rows[i+1:]:
            if a["split"] == b["split"] or Counter(a["symbols"]) != Counter(b["symbols"]):
                continue
            checked += 1
            if pose_distance(poses[a["sample_id"]], variants[b["sample_id"]]) <= .2:
                raise ValueError("retained cross-split near overlap:" + a["sample_id"] + "/" + b["sample_id"])
    result = {"status": "VERIFIED_PREPARED_POOL_NOT_TRAINING_AUTHORITY", "counts": {k: len(v) for k, v in manifest["splits"].items()},
        "observed_heldout": len(observed), "previous24_exactly_recovered": len(previous24),
        "previous24_retained": sum(r["sample_id"] in {o["sample_id"] for o in previous24} for r in rows),
        "cross_split_pairs_recomputed": checked,
        "manifest_sha256": sha256_file(output / "training_manifest.json"), "training_authorized": False}
    write_json_exclusive(output / "verification_receipt.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "prepare", "resume-review", "verify"))
    parser.add_argument("--names", nargs="+")
    args = parser.parse_args()
    if args.action == "collect":
        collect(args.names)
    elif args.action == "prepare":
        prepare()
    elif args.action == "resume-review":
        resume_review()
    else:
        verify()
