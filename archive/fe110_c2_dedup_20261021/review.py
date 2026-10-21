"""Source-bound endpoint review; no scientific execution, deletion or registry write."""
from __future__ import annotations

import argparse
import base64
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_adsorption_calibration_20261018.prepare_current_trajectories import check_inputs
from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import verify_frame
from archive.fe110_adsorption_pool_rebuild_20261019.prepare_pool import (
    reader_source, source_records, verified_collection,
)
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature, pose_measurements
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import final_scf_state, read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
DEST = BASE / "dedup_final_review_20261021_v1"
CLEAN = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
POLICY = ROOT / "configs/adsmind_lite/analysis_rules.yaml"


def prepare():
    old = load_json_object(BASE / "vasp_batch_v1/submission_summary.json")["records"]
    cache_records = {r["name"]: r for r in source_records()}
    records = []
    for r in old:
        records.append({**r, "cohort": "original15", "original_name": r["name"],
                        "atom_count": len(expanded_symbols(read_poscar(Path(r["workdir"]) / "POSCAR")))})
    paired = BASE / "adsorption_control_paired_vasp3_20261020_v1"
    plan = {(j["name"], j["arm"]): j for j in load_json_object(paired / "batch_manifest.json")["jobs"]}
    for r in load_json_object(paired / "submission_summary.json")["records"]:
        if r["name"] != "06_C":
            continue
        p = plan[r["name"], r["arm"]]
        candidate = load_json_object(ROOT / p["path"] / "candidate_manifest.json")
        records.append({**r, "name": "paired_" + r["name"] + "_" + r["arm"],
            "original_name": r["name"], "cohort": "paired06C", "species_id": "06",
            "formula": candidate["formula"], "connectivity": candidate["connectivity"],
            "workdir": str(ROOT / p["path"]), "potcar_sha256": p["potcar_sha256"], "atom_count": 49})
    DEST.mkdir(exist_ok=False)
    sources = []
    for r in records:
        path = verified_collection(cache_records[r["name"]]) if r["name"] in cache_records else None
        source = path / "source.json" if path else None
        sources.append({"record": r, "source": str(source) if source else None,
                        "source_sha256": sha256_file(source) if source else None,
                        "collection_receipt_sha256": sha256_file(path / "receipt.json") if path else None})
    write_json_exclusive(DEST / "request.json", {"sources": sources,
        "scope": "Original15 plus the two already converged paired06C outputs;no active-job snapshots in stable-state count.",
        "clean": {"path": str(CLEAN), "sha256": sha256_file(CLEAN)},
        "policy": {"path": str(POLICY), "sha256": sha256_file(POLICY)},
        "source": {"path": str(Path(__file__)), "sha256": sha256_file(Path(__file__))},
        "new_scientific_jobs": 0, "remote_mutation": False})
    print("PREPARED", len(sources), "REUSED", sum(s["source"] is not None for s in sources))


def collect_one(item):
    record = item["record"]
    folder = DEST / "collected" / record["name"]
    folder.mkdir(parents=True, exist_ok=False)
    code = reader_source(record, 2)
    with (folder / "source.json").open("xb") as out, (folder / "stderr.txt").open("xb") as err:
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "sunboquan-codex", "python3", "-"], input=code.encode(), stdout=out, stderr=err, timeout=180, check=False)
    write_json_exclusive(folder / "receipt.json", {"exit_code": result.returncode,
        "reader_sha256": hashlib.sha256(code.encode()).hexdigest(), "output_sha256": sha256_file(folder / "source.json"),
        "source_job_id": record["job_id"], "remote_mutation": False})
    if result.returncode:
        raise RuntimeError("read-only extraction failed:" + record["name"])
    return record["name"]


def collect():
    request = load_json_object(DEST / "request.json")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(collect_one, s) for s in request["sources"] if s["source"] is None]
        for future in as_completed(futures):
            print("COLLECTED", future.result(), flush=True)


def tail_collect():
    request = load_json_object(DEST / "request.json")
    source_path = Path(__file__).with_name("tail_reader.py")
    for item in request["sources"]:
        if item["source"] is not None:
            continue
        record = item["record"]
        folder = DEST / "collected_tail_v2" / record["name"]
        folder.mkdir(parents=True, exist_ok=False)
        code = "RECORDS=" + repr([record]) + "\n" + source_path.read_text(encoding="utf-8")
        with (folder / "source.json").open("xb") as out, (folder / "stderr.txt").open("xb") as err:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3", "-"],
                                    input=code.encode(), stdout=out, stderr=err, timeout=60, check=False)
        write_json_exclusive(folder / "receipt.json", {"exit_code": result.returncode,
            "reader_sha256": hashlib.sha256(code.encode()).hexdigest(), "reader_source_sha256": sha256_file(source_path),
            "output_sha256": sha256_file(folder / "source.json"), "remote_mutation": False})
        if result.returncode:
            raise RuntimeError("bounded final-frame extraction failed:" + record["name"])
        print("FINAL_FRAME_COLLECTED", record["name"], flush=True)


def analyze(item, slab, policy):
    record = item["record"]
    path = Path(item["source"]) if item["source"] else DEST / "collected_tail_v2" / record["name"] / "source.json"
    receipt = load_json_object(path.parent / "receipt.json")
    if receipt["exit_code"] or sha256_file(path) != receipt["output_sha256"]:
        raise ValueError("source extraction failed/changed")
    if item["source"]:
        # verified_collection checked the original v1/v2 reader before freezing.
        if (sha256_file(path) != item["source_sha256"]
                or sha256_file(path.parent / "receipt.json") != item["collection_receipt_sha256"]):
            raise ValueError("verified cached extraction binding changed")
    else:
        tail_source = Path(__file__).with_name("tail_reader.py")
        code = "RECORDS=" + repr([record]) + "\n" + tail_source.read_text(encoding="utf-8")
        if hashlib.sha256(code.encode()).hexdigest() != receipt["reader_sha256"]:
            raise ValueError("new extraction reader binding changed")
    source = load_json_object(path)
    if source["POTCAR_sha256"] != record["potcar_sha256"]:
        raise ValueError("POTCAR branch mismatch")
    folder = DEST / "structures" / record["name"]
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR"):
        data = base64.b64decode(source["files"][name], validate=True)
        target_file = folder / name
        if target_file.exists():
            if target_file.read_bytes() != data:
                raise ValueError("preserve changed restored evidence:" + str(target_file))
        else:
            with target_file.open("xb") as handle:
                handle.write(data)
    check_inputs(folder, record)
    initial, final = [read_poscar(folder / n) for n in ("POSCAR", "CONTCAR")]
    atoms = read(folder / "CONTCAR", format="vasp")
    atoms.pbc = [True, True, False]
    frame = max(source["frames"], key=lambda f: f["ionic_step"])
    if frame["ionic_step"] != source["total_steps"]:
        raise ValueError("not the source final force/energy frame")
    forces = verify_frame(atoms, frame)
    values = read_incar_values(folder / "INCAR")
    scf = final_scf_state(parse_oszicar(folder / "OSZICAR"), values)
    fmax = float(np.linalg.norm(forces[18:], axis=1).max())
    symbols = expanded_symbols(final)
    ads = list(range(45, len(symbols)))
    dist = np.linalg.norm(minimum_image_delta_xy(final.frac[:, None, :] - final.frac[None, :, :]) @ final.cell, axis=2)
    target = read_poscar(BASE / "candidates_v2" / record["original_name"] / "POSCAR")
    def signature(pose):
        try:
            return molecular_signature(pose)
        except ValueError:
            return None
    target_signature, final_signature = signature(target), signature(final)
    compatible = (expanded_symbols(initial) == symbols and final.flags == initial.flags
        and final.flags == [("F", "F", "F")] * 18 + [("T", "T", "T")] * (len(symbols) - 18)
        and np.allclose(final.cell, slab.cell, atol=1e-8, rtol=0)
        and np.max(np.abs(minimum_image_delta_xy(final.frac[:18] - slab.frac[:18]) @ slab.cell)) < 1e-7)
    graph = sorted(connectivity(final, ads))
    excluded = {(a + 45, b + 45) for a, b in graph}
    nonbonded = min(dist[i, j] for i in range(len(symbols)) for j in range(i + 1, len(symbols)) if (i, j) not in excluded)
    slab_motion = float(np.linalg.norm(minimum_image_delta_xy(final.frac[:45] - initial.frac[:45]) @ slab.cell, axis=1).max())
    technical = bool(source["normal_completion"] and source["ionic_converged"]
        and scf["electronically_converged"] and fmax <= .02)
    geometry = bool(compatible and nonbonded >= policy["contact_validation"]["hard_contact_distance_angstrom"]
        and slab_motion <= policy["surface_reconstruction"]["maximum_slab_displacement_angstrom"])
    intact = final_signature is not None and final_signature == target_signature
    return {"name": record["name"], "original_name": record["original_name"], "cohort": record["cohort"],
        "species_id": record["species_id"], "formula": record["formula"], "job_id": record["job_id"],
        "target_graph": record["connectivity"], "final_signature": final_signature,
        "final_edges_0based": [[a + 45, b + 45] for a, b in graph],
        "target_preserved": intact, "submitted_graph_preserved": sorted(connectivity(initial, ads)) == graph,
        "technical_convergence": technical, "geometry_checks_pass": geometry, "compatible": bool(compatible),
        "electronic": scf, "ionic_steps": source["total_steps"], "normal_completion": source["normal_completion"],
        "accuracy_marker": source["ionic_converged"], "fmax_eV_A": fmax, "toten_eV": frame["toten_eV"],
        "minimum_nonbonded_A": float(nonbonded), "slab_displacement_max_A": slab_motion,
        "eligible_target": technical and geometry and intact,
        "eligible_reclassified_review": technical and geometry and not intact,
        "measurements": pose_measurements(final), "directory": str(folder),
        "source": {"path": str(path), "sha256": sha256_file(path), "OUTCAR_sha256": source["OUTCAR_sha256"],
                   "OUTCAR_bytes": source["OUTCAR_bytes"], "POTCAR_sha256": source["POTCAR_sha256"],
                   "final_structure_sha256": sha256_file(folder / "CONTCAR")},
        "duplicate_of": None, "scientific_acceptance": False}


def review():
    request = load_json_object(DEST / "request.json")
    if sha256_file(DEST / "preparation_source_snapshot.py") != request["source"]["sha256"]:
        raise ValueError("original preparation source snapshot changed")
    if sha256_file(CLEAN) != request["clean"]["sha256"] or sha256_file(POLICY) != request["policy"]["sha256"]:
        raise ValueError("review policy/clean reference changed")
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    slab = read_poscar(CLEAN)
    rows = [analyze(item, slab, policy) for item in request["sources"]]
    for row in rows:
        print(row["name"], row["ionic_steps"], round(row["fmax_eV_A"], 6),
              "TARGET" if row["eligible_target"] else "RECLASSIFY_REVIEW" if row["eligible_reclassified_review"] else "NOT_QUALIFIED", flush=True)
    operations = surface_pose_symmetries(slab)
    poses = {r["name"]: read_poscar(Path(r["directory"]) / "CONTCAR") for r in rows}
    comparisons = []
    reps = []
    for row in sorted(rows, key=lambda r: (r["toten_eV"], r["name"])):
        if not row["eligible_target"]:
            continue
        for prior in reps:
            if row["formula"] != prior["formula"] or row["final_signature"] != prior["final_signature"]:
                continue
            metrics = surface_equivalence(poses[prior["name"]], poses[row["name"]], slab, operations)
            de = abs(row["toten_eV"] - prior["toten_eV"])
            duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= policy["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"] and de <= policy["duplicate_detection"]["energy_tolerance_ev"]
            comparisons.append({"first": prior["name"], "second": row["name"], **metrics, "dE_eV": de, "duplicate": duplicate})
            if duplicate:
                row["duplicate_of"] = prior["name"]
                break
        if row["duplicate_of"] is None:
            reps.append(row)
    write_json_exclusive(DEST / "review.json", {"rows": rows, "comparisons": comparisons,
        "representatives": [r["name"] for r in reps], "policy_sha256": sha256_file(POLICY),
        "clean_sha256": sha256_file(CLEAN), "source_sha256": sha256_file(Path(__file__)),
        "scientific_acceptance": False, "registry_written": False, "files_deleted": False,
        "scope": "Exact formula/final-chemistry,clean-slab symmetries,H permutations,fixed C roles;0.20A/0.05eV existing policy"})
    print("REPRESENTATIVES", [r["name"] for r in reps])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "collect", "tail_collect", "review"))
    args = parser.parse_args()
    {"prepare": prepare, "collect": collect, "tail_collect": tail_collect, "review": review}[args.phase]()


if __name__ == "__main__":
    main()
