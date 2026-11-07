"""Collect unchanged GPU evidence and review exact chemistry before VASP preparation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

import numpy as np
from ase.io import read
import yaml

from archive.fe110_c2_dual_gpu_20261106.deploy import connection
from archive.fe110_c2_gpu_repair_20261107.prepare import OUT as GPU_OUT, REMOTE as GPU_REMOTE
from archive.fe110_pair2_20261027.review import audit_frames, post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature, pose_measurements
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from archive.fe110_adsorption_validation_20261018.review import surface_metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_c2_site_supplement_20261106/vasp_handoff_20261107_v1"
PACKAGE = GPU_OUT / "aqcat_gpu/package"
NAMES = ["05_S1", "05_S2", "06_S1", "06_S2", "07_S1", "09_S1", "11_S1", "12_S1", "13_S1", "14_S1", "18_S1", "18_S2"]
SELECTED = [name for name in NAMES if name not in {"06_S1", "09_S1"}]
AUTH = ROOT / "docs/reviews/fe110_c2_supplement_vasp_20261107_user_authorization.md"


def collect():
    OUT.mkdir(exist_ok=False)
    request = load_json_object(PACKAGE / "request.json")
    paths = ["output/" + name for name in ("cases.json", "producer_exit_record.json", "device_commands.json", "gpu_admission.json", "model_device.json")]
    paths += [f"output/finetune/{name}/seed/{filename}" for name in NAMES
              for filename in ("POSCAR", "case_record.json", "optimization.traj", "optimizer.log")]
    code = '''import hashlib,json
from pathlib import Path
root=Path(ROOT);entries=[]
for name in PATHS:
 p=root/name
 assert p.is_file() and not p.is_symlink() and p.stat().st_size<10000000
 entries.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
assert sum(x['bytes'] for x in entries)<100000000
print(json.dumps({'root':ROOT,'files':entries}))
'''
    args, destination = connection("aqcat_gpu")
    result = subprocess.run(args + ["-T", destination, "python3 -c " + shlex.quote(
        "ROOT=" + repr(GPU_REMOTE) + "\nPATHS=" + repr(paths) + "\n" + code)], capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[:2000])
    manifest = json.loads(result.stdout)
    with (OUT / "collection_manifest.json").open("xb") as handle:
        handle.write(result.stdout)
    archive = OUT / "returned.tar"
    with archive.open("xb") as stdout, (OUT / "collection.stderr").open("xb") as stderr:
        result = subprocess.run(args + ["-T", destination,
            shlex.join(["tar", "-cf", "-", "-C", GPU_REMOTE, *paths])], stdout=stdout, stderr=stderr, timeout=90)
    if result.returncode:
        raise RuntimeError("collection failed; preserve partial archive and inspect stderr")
    returned = OUT / "returned"
    expected = {entry["path"]: entry for entry in manifest["files"]}
    with tarfile.open(archive) as handle:
        seen = set()
        for member in handle:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("unexpected collection member")
            target = returned / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.extractfile(member) as source, target.open("xb") as destination_file:
                shutil.copyfileobj(source, destination_file)
            if target.stat().st_size != expected[member.name]["bytes"] or sha256_file(target) != expected[member.name]["sha256"]:
                raise ValueError("collected bytes changed")
            seen.add(member.name)
        if seen != set(expected):
            raise ValueError("incomplete collection")
    producer = load_json_object(returned / "output/producer_exit_record.json")
    device = load_json_object(returned / "output/model_device.json")
    payload = load_json_object(returned / "output/cases.json")
    if (producer["exit_code"] != 0 or producer["request_sha256"] != sha256_file(PACKAGE / "request.json")
            or producer["scheduler_job_id"] != "11721" or device["model_devices"] != ["cuda:0"]
            or payload["model_sha256"] != request["model"]["sha256"]):
        raise ValueError("native producer/model/request identity mismatch")
    write_json_exclusive(OUT / "collection_receipt.json", {"status": "BYTE_VERIFIED", "files": len(expected),
        "archive_sha256": sha256_file(archive), "model_sha256": payload["model_sha256"],
        "request_sha256": producer["request_sha256"], "scheduler_job_id": "11721", "scientific_acceptance": False})
    print("COLLECTED", len(expected), "hash-verified files", flush=True)


def review():
    request = load_json_object(PACKAGE / "request.json")
    payload = load_json_object(OUT / "returned/output/cases.json")
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    manifest = load_json_object(OUT / "collection_manifest.json")
    if any(sha256_file(OUT / "returned" / item["path"]) != item["sha256"] for item in manifest["files"]):
        raise ValueError("collection changed")
    rows = []
    for case, record in zip(request["cases"], payload["cases"], strict=True):
        if case["name"] != record["name"] or case["seed_sha256"] != record["source_structure_sha256"]:
            raise ValueError("case/source identity differs")
        folder = OUT / "returned/output/finetune" / case["name"] / "seed"
        seed, final = read_poscar(PACKAGE / case["seed_path"]), read_poscar(folder / "POSCAR")
        frames = read(folder / "optimization.traj", index=":")
        if expanded_symbols(seed) != expanded_symbols(final) or not np.array_equal(seed.flags, final.flags):
            raise ValueError("atom order/constraint mismatch")
        audit = audit_frames(seed, frames, final)
        post = post_relaxation_geometry(seed, final, audit, rules)
        signature_error = None
        try:
            exact = molecular_signature(seed) == molecular_signature(final) and audit["final_graph_preserved"]
        except ValueError as error:
            exact = False
            signature_error = str(error)
        if record["optimizer_steps"] + 1 != len(frames):
            raise ValueError("trajectory/step count mismatch")
        rows.append({**record, "initial_graph": audit["seed_graph"], "final_graph": audit["final_graph"],
            "exact_target_graph_retained": exact, "signature_error": signature_error,
            "trajectory_audit": audit, "geometry_review": post,
            "initial_measurements": pose_measurements(seed), "final_measurements": pose_measurements(final),
            "original_POSCAR": str(PACKAGE / case["seed_path"]), "ML_final_POSCAR": str(folder / "POSCAR"),
            "requested_source": "original" if case["name"] == "06_S2" else "ML_final",
            "ML_initial_structure_eligible": bool(exact and post["diagnostic_DFT_geometry_ready"] and record["converged"]),
            "scientific_acceptance": False})
    document = {"status": "CHEMISTRY_REVIEW_NOT_SCIENTIFIC_ACCEPTANCE", "cases": rows,
        "created_at": datetime.now(timezone.utc).isoformat(), "model_checkpoint_sha256": payload["model_sha256"],
        "source_files": source_file_manifest([OUT / "collection_manifest.json", OUT / "collection_receipt.json", PACKAGE / "request.json", rules_path]
                                             + [Path(row[key]) for row in rows for key in ("original_POSCAR", "ML_final_POSCAR")])}
    write_json_exclusive(OUT / "ML_results_review.json", document)
    for row in rows:
        print(row["name"], "ML_converged=", row["converged"], "graph_retained=", row["exact_target_graph_retained"],
              "geometry=", row["geometry_review"]["diagnostic_DFT_geometry_ready"],
              "fragments=", row["geometry_review"]["fragment_formulas_from_connectivity"], flush=True)


def select():
    reviewed = load_json_object(OUT / "ML_results_review.json")
    request = load_json_object(PACKAGE / "request.json")
    native_exit = OUT / "returned/output/producer_exit_record.json"
    exit_adapter = OUT / "producer_exit_handoff_adapter.json"
    write_json_exclusive(exit_adapter, {"gpu_job_id": "11721", "exit_code": 0,
        "native_exit_record_path": str(native_exit), "native_exit_record_sha256": sha256_file(native_exit)})
    rows, handoffs = [], []
    for row, case in zip(reviewed["cases"], request["cases"], strict=True):
        original_path = PACKAGE / case["handoff_path"]
        original = validate_handoff(original_path, root=PACKAGE, schema_path=PACKAGE / "handoff.schema.json")
        copied = OUT / "source_handoffs" / (case["name"] + ".json")
        copied.parent.mkdir(exist_ok=True)
        with copied.open("xb") as handle:
            handle.write(original_path.read_bytes())
        final = Path(row["ML_final_POSCAR"])
        symbols = expanded_symbols(read_poscar(final))
        frames = read(final.parent / "optimization.traj", index=":")
        document = {key: original[key] for key in ("schema_version", "handoff_id", "workflow_kind", "source_workflow_sha256", "adsorption", "restrictions")}
        document.update(direction="gpu_to_work", source_handoff={"path": copied.relative_to(OUT).as_posix(), "sha256": sha256_file(copied)},
            candidate_structure={"path": final.relative_to(OUT).as_posix(), "sha256": sha256_file(final), "format": "vasp_poscar",
                                 "atom_count": len(symbols), "atom_order_sha256": atom_order_sha256(symbols)},
            producer={"backend": "aqcat_gpu", "hostname": "MZ73", "gpu_job_id": "11721",
                      "model_identifier": original["model"]["identifier"], "checkpoint_sha256": reviewed["model_checkpoint_sha256"]},
            result={"result_class": "predicted_adsorption_candidate_only", "optimizer_status": "converged" if row["converged"] else "unfinished",
                    "optimizer_steps": row["optimizer_steps"],
                    "predicted_energy": {"value": float(frames[-1].get_potential_energy()), "unit": "eV", "reportable_dft": False},
                    "predicted_force": {"fmax": row["ML_movable_fmax_eV_A"], "unit": "eV/A", "reportable_dft": False},
                    "geometry_before": row["initial_measurements"], "geometry_after": row["geometry_review"],
                    "connectivity_status": "pass" if row["exact_target_graph_retained"] else "fail",
                    "structure_invariants": {"atom_order_preserved": True, "cell_preserved": True, "fixed_atoms_preserved": True}},
            domain_assessment={"calibration_id": None, "status": "out_of_domain" if len(symbols) - 45 > 6 else "uncalibrated",
                               "method": "explicit_checkpoint_and_target_motif_review",
                               "reasons": ["This frozen checkpoint/target motif has no applicable force calibration;no energy ranking or speedup claim."]},
            producer_exit_record={"path": exit_adapter.relative_to(OUT).as_posix(), "sha256": sha256_file(exit_adapter),
                                  "status": "success", "exit_code": 0, "evidence_class": "producer_process_only_not_scheduler_accounting"})
        handoff = OUT / "return_handoffs" / (case["name"] + ".json")
        handoff.parent.mkdir(exist_ok=True)
        write_json_exclusive(handoff, document)
        validate_handoff(handoff, root=OUT, schema_path=PACKAGE / "handoff.schema.json")
        handoffs.append(handoff)
        if row["name"] not in SELECTED:
            continue
        use_original = row["name"] == "06_S2"
        if not use_original and not row["ML_initial_structure_eligible"]:
            raise ValueError("requested ML source is not chemically eligible")
        source = Path(row["original_POSCAR"] if use_original else row["ML_final_POSCAR"])
        if molecular_signature(read_poscar(source)) != molecular_signature(read_poscar(Path(row["original_POSCAR"]))):
            raise ValueError("selected chemistry differs from intended target")
        rows.append({**row, "selected_for_DFT": str(source), "selected_POSCAR_sha256": sha256_file(source),
                     "source_role": "reviewed_original_no_ML" if use_original else "ML_pre_relaxed",
                     "return_handoff": str(handoff), "original_motif_DFT_coverage_not_inferred_from_ML": True})
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    slab = read_poscar(slab_path)
    operations = surface_pose_symmetries(slab)
    comparisons = []
    for index, row in enumerate(rows):
        for prior in rows[:index]:
            if row["name"][:2] != prior["name"][:2]:
                continue
            metrics = surface_metrics(read_poscar(Path(prior["selected_for_DFT"])), read_poscar(Path(row["selected_for_DFT"])), slab, operations)
            if metrics["adsorbate_RMSD_A"] <= .20 and metrics["movable_Fe_RMSD_A"] <= .05:
                raise ValueError("selected duplicate: " + prior["name"] + "/" + row["name"])
            comparisons.append({"first": prior["name"], "second": row["name"], "metrics": metrics})
    if [row["name"] for row in rows] != SELECTED or sum(row["source_role"] == "ML_pre_relaxed" for row in rows) != 9:
        raise ValueError("latest ten-job scope changed")
    write_json_exclusive(OUT / "selection_review.json", {"status": "TEN_INITIAL_STRUCTURES_REVIEWED_NOT_ACCEPTED_RESULTS",
        "cases": rows, "skipped_by_latest_user_instruction": ["06_S1", "09_S1"], "same_species_duplicate_comparisons": comparisons,
        "source_files": source_file_manifest([AUTH, OUT / "ML_results_review.json", slab_path] + handoffs
                                             + [Path(row["selected_for_DFT"]) for row in rows])})
    print("SELECTED10:9 ML+06_S2 original;skipped06_S1/09_S1;12 return handoffs PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("collect", "review", "select"))
    {"collect": collect, "review": review, "select": select}[parser.parse_args().phase]()
