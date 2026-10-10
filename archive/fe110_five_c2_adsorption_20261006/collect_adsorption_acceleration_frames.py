"""Read existing closed trajectories for a reviewed acceleration experiment only."""

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.io import read, write

from archive.fe110_five_c2_adsorption_20261006.prepare_c2_force_diagnostic import verify_frame
from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "adsorption_acceleration_rebuild_v1"
# Freeze whole-job assignments before any new predictions/training.
SPLITS = {"01_cfg1": "train", "02_cfg2": "train", "04_cfg2": "train", "05_cfg0": "train",
          "04_cfg0": "development", "04_cfg1": "heldout", "05_cfg1": "heldout"}


def selected_steps(total):
    if total < 5:
        raise ValueError("trajectory too short")
    return sorted({1, 2, 5, max(1, round(total * .25)), max(1, round(total * .5)),
                   max(1, round(total * .75)), total - 1, total})


# Dependency-free remote reader. Complete streaming parse, compact selected output.
REMOTE_READER = r'''
import base64,hashlib,json,re,sys
from pathlib import Path
for record in RECORDS:
 print('reading '+record['name'],file=sys.stderr,flush=True)
 root=Path(record['remote_dir'].replace('~',str(Path.home()),1)); out=root/'OUTCAR'
 before=out.stat(); h=hashlib.sha256(); frames=[]
 iteration=None; reached=False; current=None
 with out.open('rb') as f:
  def line():
   value=f.readline(); h.update(value); return value
  while True:
   offset=f.tell(); text=line()
   if not text: break
   match=re.search(rb'Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)',text)
   if match:
    iteration=tuple(map(int,match.groups())); reached=False
   if b'aborting loop because EDIFF is reached' in text: reached=True
   if b'TOTAL-FORCE (eV/Angst)' in text:
    raw=text; rows=[]; tokens=[]
    while True:
     value=line(); raw+=value; fields=value.split()
     if len(fields)==6:
      try: row=[float(v) for v in fields]
      except ValueError: continue
      rows.append(row); tokens.append([v.decode() for v in fields[:3]])
     elif rows: break
     elif not value: break
    if not iteration or len(rows) not in (48,49): raise ValueError('invalid force frame')
    current={'ionic_step':iteration[0],'electronic_iteration':iteration[1],
             'EDIFF_marker_before_force':reached,'positions_A':[r[:3] for r in rows],
             'position_tokens':tokens,'forces_eV_per_A':[r[3:] for r in rows],
             'source_byte_range':[offset,f.tell()],'force_table_base64':base64.b64encode(raw).decode()}
    frames.append(current)
   if b'free  energy   TOTEN' in text and current is not None:
    current['toten_eV']=float(text.split()[4])
 after=out.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('source changed')
 with out.open('rb') as f:
  f.seek(max(0,before.st_size-100000)); tail=f.read(100000)
 if b'reached required accuracy' not in tail or b'General timing and accounting informations' not in tail:
  raise ValueError('source not normally force-converged')
 total=frames[-1]['ionic_step']; wanted=set(selected_steps(total))
 files={}
 for name in ('POSCAR','CONTCAR','INCAR','KPOINTS','OSZICAR','XDATCAR'):
  p=root/name
  if p.stat().st_size>2000000: raise ValueError('source file exceeds inspection budget: '+name)
  files[name]=base64.b64encode(p.read_bytes()).decode()
 print(json.dumps({'record':record,'frames':[r for r in frames if r['ionic_step'] in wanted],
                   'total_steps':total,'OUTCAR_sha256':h.hexdigest(),'OUTCAR_bytes':before.st_size,
                   'normal_completion':True,'files':files}),flush=True)
'''


def collect():
    DEST.mkdir(exist_ok=False)
    records = json.loads((BASE / "vasp_batch_v1/submission_summary.json").read_text())["records"]
    selected = [{**r, "split": SPLITS[r["name"]]} for r in records if r["name"] in SPLITS]
    if len(selected) != len(SPLITS):
        raise ValueError("source job missing")
    selection_source = "def selected_steps(total):\n return sorted({1,2,5,max(1,round(total*.25)),max(1,round(total*.5)),max(1,round(total*.75)),total-1,total})\n"
    code = "RECORDS=" + repr(selected) + "\n" + selection_source + REMOTE_READER
    write_json(DEST / "collection_request.json", {"records": selected, "split_unit": "whole_VASP_job",
        "remote_reader_sha256": hashlib.sha256(code.encode()).hexdigest(), "new_calculation": False})
    with (DEST / "remote_extraction.jsonl").open("xb") as output, (DEST / "collection_stderr.txt").open("xb") as errors:
        process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3 -"],
                                   stdin=subprocess.PIPE, stdout=output, stderr=errors)
        process.stdin.write(code.encode())
        process.stdin.close()
        try:
            exit_code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait()
    write_json(DEST / "collection_receipt.json", {"exit_code": exit_code,
        "output_sha256": sha256_file(DEST / "remote_extraction.jsonl")})
    if exit_code:
        raise RuntimeError("read-only collection failed; preserve receipt, no calculation retried")
    if (DEST / "remote_extraction.jsonl").stat().st_size > 15000000:
        raise ValueError("unexpected payload size")
    print("COLLECTED_EXISTING_TRAJECTORIES_ONLY")


def prepare():
    target = DEST / "dataset_review.json"
    if target.exists():
        raise FileExistsError(target)
    receipt = json.loads((DEST / "collection_receipt.json").read_text())
    if receipt["exit_code"] != 0 or receipt["output_sha256"] != sha256_file(DEST / "remote_extraction.jsonl"):
        raise ValueError("collection not verified")
    docs = [json.loads(line) for line in (DEST / "remote_extraction.jsonl").read_text().splitlines()]
    if {d["record"]["name"] for d in docs} != set(SPLITS):
        raise ValueError("incomplete source jobs")
    samples = []
    for doc in docs:
        record = doc["record"]
        folder = DEST / "sources" / record["name"]
        folder.mkdir(parents=True, exist_ok=False)
        for name, value in doc["files"].items():
            (folder / name).write_bytes(base64.b64decode(value, validate=True))
        for name in ("POSCAR", "INCAR", "KPOINTS"):
            if sha256_file(folder / name) != sha256_file(Path(record["workdir"]) / name):
                raise ValueError("submitted input changed")
        incar = validate_parameters(folder / "INCAR")
        initial = read(folder / "POSCAR", format="vasp")
        trajectory = read(folder / "XDATCAR", index=":", format="vasp-xdatcar")
        osz = parse_oszicar(folder / "OSZICAR")
        cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"] if c["complete"]}
        if len(trajectory) != doc["total_steps"]:
            raise ValueError("XDATCAR indexing needs explicit review")
        for frame in doc["frames"]:
            step = frame["ionic_step"]
            cycle = cycles[step]
            if not frame["EDIFF_marker_before_force"] or cycle["iteration"] != frame["electronic_iteration"]:
                raise ValueError("force label SCF association failed")
            if frame["electronic_iteration"] >= int(incar["NELM"]):
                raise ValueError("exhausted SCF frame")
            atoms = trajectory[step - 1]
            atoms.set_constraint(initial.constraints)
            if atoms.get_chemical_symbols() != initial.get_chemical_symbols() or not np.allclose(atoms.cell, initial.cell):
                raise ValueError("trajectory identity changed")
            forces = verify_frame(atoms, frame)
            if "toten_eV" not in frame:
                raise ValueError("frame energy missing")
            if abs(frame["toten_eV"] - osz["energies"][step - 1]) > 1e-4:
                raise ValueError("OUTCAR energy associated with wrong ionic frame")
            sid = record["name"] + "_step" + str(step).zfill(3)
            path = DEST / "structures" / (sid + ".vasp")
            path.parent.mkdir(exist_ok=True)
            write(path, atoms, format="vasp", direct=True, vasp5=True)
            table = folder / (sid + "_force_table.txt")
            table.write_bytes(base64.b64decode(frame["force_table_base64"], validate=True))
            samples.append({"sample_id": sid, "source_job_id": record["job_id"], "source_name": record["name"],
                "split": record["split"], "ionic_step": step, "structure_path": path.relative_to(DEST).as_posix(),
                "structure_sha256": sha256_file(path), "symbols": atoms.get_chemical_symbols(),
                "fixed_atom_indices_0based": list(range(18)), "forces_eV_per_A": forces.tolist(),
                "toten_eV_force_label_only": frame["toten_eV"], "electronic_converged": True,
                "source_OUTCAR_sha256": doc["OUTCAR_sha256"], "source_force_table_sha256": sha256_file(table),
                "source_XDATCAR_sha256": sha256_file(folder / "XDATCAR"),
                "total_magnetization_muB": osz["magnetization_history_muB"][step - 1]
                    if len(osz["magnetization_history_muB"]) == doc["total_steps"] else None,
                "geometry_precision": "XDATCAR coordinates checked against OUTCAR printed-position precision",
                "chemistry_review": "PENDING", "training_eligible": False})
    counts = {split: sum(s["split"] == split for s in samples) for split in ("train", "development", "heldout")}
    write_json(target, {"status": "PREPARED_TRAJECTORY_LABELS_PENDING_CHEMISTRY_DEDUP_REPLAY_REVIEW",
        "counts": counts, "split_unit": "whole_job_no_random_frame_split", "source_job_splits": SPLITS,
        "samples": samples, "species03_CHCO_coverage": False, "independent_generalization_proved": False,
        "source_collection_sha256": sha256_file(DEST / "remote_extraction.jsonl"),
        "training_authorized": False, "gpu_submitted": False, "vasp_submitted": False})
    print(json.dumps({"sample_counts": counts, "status": "PREPARED_FOR_REVIEW_NOT_TRAINING"}))


def validate_parameters(path):
    incar = read_incar_values(path)
    if (float(incar["SIGMA"]) != .2 or int(incar["ISMEAR"]) != 1
            or float(incar["ENCUT"]) != 400 or int(incar["ISPIN"]) != 2):
        raise ValueError("incompatible production parameters")
    return incar


def review():
    import yaml

    from scripts.adsmind_lite.relaxed_analysis import connectivity_change, connectivity_edges
    from scripts.matris_training_exclusions import structure_equivalence_fingerprint
    from scripts.neb_agent.utils_structure import read_poscar

    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text())
    data = json.loads((DEST / "dataset_review.json").read_text())
    records, seen, overlaps = [], {}, []
    for sample in data["samples"]:
        path = DEST / sample["structure_path"]
        if sha256_file(path) != sample["structure_sha256"]:
            raise ValueError("reviewed structure changed")
        atoms = read(path, format="vasp")
        initial = read(DEST / "sources" / sample["source_name"] / "POSCAR", format="vasp")
        atoms.pbc = initial.pbc = [True, True, False]
        ads = [i for i, symbol in enumerate(atoms.get_chemical_symbols()) if symbol != "Fe"]
        connectivity = rules["connectivity"]
        kwargs = {"scale": connectivity["covalent_radius_scale"], "minimum": connectivity["minimum_bond_distance_angstrom"]}
        chemistry = connectivity_change(len(ads), connectivity_edges(initial, ads, **kwargs), connectivity_edges(atoms, ads, **kwargs))
        distances = atoms.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        minimum = float(distances.min())
        equivalent = structure_equivalence_fingerprint(read_poscar(path))
        previous = seen.setdefault(equivalent, sample)
        if previous["split"] != sample["split"]:
            overlaps.append([previous["sample_id"], sample["sample_id"]])
        fixed_ok = bool(np.allclose(atoms.positions[:18], initial.positions[:18], atol=1e-6, rtol=0))
        records.append({"sample_id": sample["sample_id"], "split": sample["split"], "chemistry": chemistry,
            "minimum_pair_distance_A": minimum, "fixed_coordinates_preserved": fixed_ok,
            "structure_equivalence_sha256": equivalent,
            "geometry_pass": not chemistry["connectivity_changed"] and fixed_ok
                and minimum >= rules["contact_validation"]["hard_contact_distance_angstrom"]})
    target = DEST / "geometry_split_review.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, {"records": records, "cross_split_equivalent_structures": overlaps,
        "all_geometry_pass": all(r["geometry_pass"] for r in records),
        "exact_equivalence_split_pass": not overlaps, "near_duplicate_and_site_review": "PENDING",
        "source_dataset_sha256": sha256_file(DEST / "dataset_review.json"), "rules_sha256": sha256_file(rules_path),
        "training_eligible": False})
    replay = ROOT / "outputs/aqcat25_fe45_calibration_v1/labels.json"
    plan = DEST / "acceleration_adjustment_plan.json"
    write_json(plan, {
        "status": "LOCAL_DATA_AND_PERFORMANCE_REVIEW_PREPARED_NOT_EXECUTION_PACKAGE",
        "scope": "current Fe110 C2 adsorption family only; no TS executor or global model role change",
        "dataset_sha256": sha256_file(DEST / "dataset_review.json"), "geometry_split_review_sha256": sha256_file(target),
        "counts": data["counts"], "whole_job_split": SPLITS,
        "base_checkpoint": {"backend": "aqcat25", "sha256": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"},
        "matris_role": "fixed_structure_comparison_not_automatic_replacement",
        "replay_candidate": {"path": replay.relative_to(ROOT).as_posix(), "sha256": sha256_file(replay),
                             "sample_count": 13, "SIGMA_and_source_binding_review": "PENDING_NOT_TRAINING_ELIGIBLE"},
        "training_objective": "correct off-equilibrium and near-minimum C/O forces while retaining movable Fe/H quality; keep fixedFe0-17 excluded",
        "model_validation": "report adsorbate/Fe/C/O/H separately, force directions and DFT-minimum drift; no promotion from overall RMSE alone",
        "performance_test": {"cases": ["04_cfg1", "05_cfg1"], "arms": ["raw_seed_direct_VASP", "frozen_AQ_baseline_plus_VASP", "candidate_checkpoint_plus_VASP"],
            "same_original_seed_required": True, "same_reviewed_final_minimum_required": True,
            "locked_VASP_parameters_and_resources_required": True, "reuse_existing_controls_if_compatible": True,
            "account": ["VASP_ionic_steps", "VASP_elapsed_seconds", "GPU_elapsed_seconds", "incremental_label_and_training_cost", "amortization_and_break_even"],
            "desired_reduction": "substantial reduction, not a numerical physics/stop threshold; target to be reviewed before executing comparison"},
        "remaining_before_training": ["near-duplicate/site and replay compatibility review", "adsorption-specific training adapter; do not mislabel trajectory frames as TS labels or converged endpoints", "reviewed training settings and explicit GPU authorization"],
        "benchmark_implemented": "scripts/adsorption/acceleration_benchmark.py",
        "training_authorized": False, "gpu_submitted": False, "vasp_submitted": False,
        "achieved_speedup": None, "species03_CHCO_coverage": False})
    print(json.dumps({"counts": data["counts"], "geometry_pass": all(r["geometry_pass"] for r in records),
                      "cross_split_equivalents": len(overlaps), "training_submitted": False}))


def record():
    from scripts.state_manager.models import validate_event

    previous_id = "task-fe110-c2-matris2180-compared-20261010"
    source = ROOT / "modules/state_handoff/events" / (previous_id + ".json")
    event = json.loads(source.read_text())
    event_id = "task-fe110-c2-acceleration-adjustment-prepared-20261010"
    target = source.parent / (event_id + ".json")
    if target.exists():
        raise FileExistsError(target)
    now = datetime.now(timezone.utc).isoformat()
    paths = [DEST / name for name in ("collection_receipt.json", "dataset_review.json", "geometry_split_review.json", "acceleration_adjustment_plan.json")]
    paths.extend([ROOT / "docs/reviews/fe110_adsorption_acceleration_adjustment_20261010.md",
                  ROOT / "scripts/adsorption/acceleration_benchmark.py",
                  BASE / "adsorption_acceleration_rebuild_v1/collection_failure.json"])
    event.update(event_id=event_id, occurred_at=now, recorded_at=now, supersedes=[previous_id],
        summary="Prepare existing-trajectory model-adaptation data and matched total-cost benchmark for C2 adsorption; 56 label candidates, no training or new scientific job.",
        evidence=[{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p), "authority": "module_validation", "observed_at": now} for p in paths])
    event["payload"].update(
        objective="Optimize the five exact Fe110 C2 adsorption identities and validate whether GPU-assisted model adaptation actually reduces compatible VASP relaxation work and total compute cost.",
        current_evidence=[
            "Previous exact-structure comparison shows small ML force is not DFT readiness; MatRIS improves C/O but worsens final Fe/H, no automatic model replacement.",
            "Read-only existing-output collection v1 timed out; failure preserved. Corrected streaming v2 completed without new GPU/VASP calculation.",
            "Seven closed trajectories yield 56 source-bound frame labels: train32, development8, whole-job-heldout16. EDIFF/cycle/energy/force/coordinate checks passed.",
            "All56 geometry checks passed; zero cross-split strict equivalents. Near-duplicate/site review, replay compatibility and adsorption training adapter remain required.",
            "Implemented matched-run step/time/GPU/shared-cost/amortization comparison. No training submitted, checkpoint promoted or achieved acceleration measured.",
            "Last CHCO snapshot:9839757 fragmented RUN,9842107 intact RUN,repair9842136 PEND; no live status recheck or job mutation this preparation step."
        ],
        one_executable_step="Complete adsorption-specific training-input adaptation and near-duplicate/replay compatibility review from the frozen56 frames; present one bounded GPU training request for separate authorization.",
        submission_boundary="Local preparation only. No new GPU/VASP job, training, model promotion, stop or VASP parameter change authorized.",
        authoritative_references=["configs/execution_backends.yaml", "modules/adsorption_workflow/README.md", "configs/true_fe110_production.yaml"]
            + [p.relative_to(ROOT).as_posix() for p in paths])
    validate_event(event)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["collect", "prepare", "review", "record"])
    parser.add_argument("--destination-name", default=DEST.name)
    args = parser.parse_args()
    if Path(args.destination_name).name != args.destination_name or not args.destination_name.startswith("adsorption_acceleration_rebuild_"):
        raise ValueError("unsafe destination name")
    DEST = BASE / args.destination_name
    {"collect": collect, "prepare": prepare, "review": review, "record": record}[args.action]()
