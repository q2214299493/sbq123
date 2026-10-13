"""Bounded 15-candidate handoff using existing builders and canonical executor."""
import argparse
import itertools
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature, pose_measurements
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.neb_agent.submission import preflight, submit, submission_status
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action, validate_decision
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.workflow_geometry import minimum_image_delta_xy

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
GPU = BASE / "gpu_direct_v3"
DEST = BASE / "vasp_batch_v1"
REMOTE = "~/sbq/Fe110/adsorption/fe110_c2_06_10_20261013_v1"
EXPECTED = [f"{code:02}_{letter}" for code in range(6, 11) for letter in "ABC"]
RECLASSIFIED = {"06_A": "CO* + C* + H*", "06_B": "CO* + C* + H*", "09_B": "CH2* + CO*"}
POTCARS = {
    "Fe C H": ("Fe_C_H", "bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a"),
    "Fe C O H": ("Fe_C_O_H", "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"),
    "Fe O C H": ("Fe_O_C_H", "cfdeb95d5ce5ab92e2ff0c0cdd1cd3870fbbe3a929822c631e09fd828c511a4f"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare():
    require(not DEST.exists(), "Existing VASP package must not be overwritten")
    candidates_file = BASE / "candidates_v2/candidate_review.json"
    candidates = load_json_object(candidates_file)
    indexed = {row["name"]: row for row in candidates["candidates"]}
    returned = load_json_object(GPU / "return_validation.json")
    require([row["candidate"] for row in returned["rows"]] == EXPECTED, "Unexpected batch")
    require(returned["all_manifest_bindings_pass"] and returned["CUDA_verified"] == 15,
            "CUDA return validation missing")
    inventory = load_json_object(GPU / "output_inventory.json")["files"]
    for row in inventory:
        path = GPU / row["path"]
        require(path.stat().st_size == row["byte_size"] and sha256_file(path) == row["sha256"],
                f"Returned artifact changed: {path}")
    clean_path = ROOT / candidates["source_slab"]
    require(sha256_file(clean_path) == candidates["source_slab_sha256"], "Clean slab changed")
    clean = read_poscar(clean_path)
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    threshold_path = ROOT / "configs/true_fe110_production.yaml"
    thresholds = yaml.safe_load(threshold_path.read_text())
    auth_source = Path(__file__).with_name("vasp_authorization.md")
    now = datetime.now(timezone.utc).isoformat()
    entries, reviewed, poses = [], [], {}
    for returned_row in returned["rows"]:
        name = returned_row["candidate"]
        candidate = indexed[name]
        source = GPU / name / "output/job_direct-fe110-c2-0610-20261013-v3/POSCAR"
        pose, initial = read_poscar(source), read_poscar(GPU / name / "POSCAR")
        symbols = expanded_symbols(pose)
        require(symbols == expanded_symbols(initial), name + ": atom order changed")
        require(np.isfinite(pose.frac).all() and np.allclose(pose.cell, clean.cell, atol=1e-8, rtol=0),
                name + ": invalid coordinates/cell")
        fixed_error = np.linalg.norm(minimum_image_delta_xy(pose.frac[:18] - clean.frac[:18]) @ clean.cell, axis=1).max()
        require(fixed_error < 1e-7, name + ": fixed coordinates changed")
        require(pose.flags == [("F", "F", "F")] * 18 + [("T", "T", "T")] * (len(symbols)-18),
                name + ": Selective Dynamics changed")
        measurement = pose_measurements(pose)
        minimum_contact = min(row["neighbors"][0]["distance_A"] for row in measurement["nearest_Fe"])
        require(minimum_contact >= rules["contact_validation"]["hard_contact_distance_angstrom"],
                name + ": emergency contact")
        if name not in RECLASSIFIED:
            require(molecular_signature(pose) == molecular_signature(initial), name + ": unexpected chemistry")
        require(returned_row["graph_preserved"] == (name not in RECLASSIFIED), name + ": chemistry flag mismatch")
        geometry = {
            "atom_order_cell_constraints_pass": True, "minimum_Fe_adsorbate_A": minimum_contact,
            "initial_species": candidate["connectivity"],
            "predicted_final_species": RECLASSIFIED.get(name, candidate["connectivity"]),
            "plausibility_status": "RECLASSIFY" if name in RECLASSIFIED else "PASS",
            "chemical_event": "dissociation" if name in RECLASSIFIED else "intact_adsorption",
            "source_sha256": sha256_file(source), **measurement,
            "user_review_scope": "All15 explicitly selected after chemistry review; predicted starting states only",
        }
        reviewed.append({"candidate": name, **geometry})
        poses[name] = pose
        run = DEST / name
        run.mkdir(parents=True)
        shutil.copyfile(source, run / "POSCAR")
        build = build_fe110_adsorption_relaxation(run, cores=32)
        write_json(run / "candidate_manifest.json", {
            "species_id": candidate["species_id"], "formula": candidate["formula"],
            "care_code": candidate["care_code"], "connectivity": candidate["connectivity"],
            "submitted_connectivity": geometry["predicted_final_species"],
            "source_structure": str(source), "source_sha256": sha256_file(source),
            "source_role": "reviewed_CUDA_direct_v3_prediction",
            "source_candidate_plan_sha256": sha256_file(candidates_file),
            "gpu_return_validation_sha256": sha256_file(GPU / "return_validation.json"),
            "source_clean_slab_sha256": candidates["source_slab_sha256"],
            "geometry_checks": geometry, "builder": build,
            "scientific_status": "starting_candidate_only_no_DFT_acceptance",
        })
        report = preflight(run, "adsorption_relaxation")
        require(report["passed"], str(report["errors"]))
        bindings = {"thresholds": {"path": str(threshold_path), "sha256": sha256_file(threshold_path)},
                    "preflight": {"path": str(run / "submission_preflight.json"), "sha256": sha256_file(run / "submission_preflight.json")}}
        evidence = decide_execution({}, {}, thresholds, climb=False, path_reviewed=True,
                                    preflight=report, source_bindings=bindings)["EVIDENCE"]
        potdir, potsha = POTCARS[(run / "POTCAR.spec").read_text().strip()]
        remote, potcar = REMOTE + "/" + name, f"~/sbq/Fe110/potcars/{potdir}/POTCAR"
        auth = {
            "schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
            "calculation_kind": "adsorption_relaxation", "authorized_at": now,
            "source": {"path": str(auth_source), "sha256": sha256_file(auth_source)},
            "target": {"server_alias": "sunboquan-codex", "remote_dir": remote},
            "workdir_identity": workdir_identity(run), "bundle_sha256": report["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(evidence),
            "potcar": {"source": potcar, "sha256": potsha, "spec_sha256": report["files"]["POTCAR.spec"]},
        }
        write_json(run / "user_execution_authorization.json", auth)
        bindings["authorization"] = {"path": str(run / "user_execution_authorization.json"), "sha256": sha256_file(run / "user_execution_authorization.json")}
        decision = decide_execution({}, {}, thresholds, climb=False, path_reviewed=True,
                                    preflight=report, source_bindings=bindings, authorization=auth)
        require(decision["ALLOWED_ACTIONS"] == ["SUBMIT_VASP"], str(decision.get("execution_authorization_error")))
        validate_decision(decision)
        write_json(run / "decision.json", decision)
        entries.append({"name": name, "species_id": candidate["species_id"], "formula": candidate["formula"],
                        "connectivity": candidate["connectivity"], "submitted_connectivity": geometry["predicted_final_species"],
                        "workdir": str(run), "remote_dir": remote, "cores": 32,
                        "potcar_source": potcar, "potcar_sha256": potsha, "bundle_sha256": report["bundle_sha256"],
                        "decision_sha256": sha256_file(run / "decision.json")})
        print(name, "PREFLIGHT_AND_SUBMIT_VASP_GATE_PASS", flush=True)
    operations = surface_pose_symmetries(clean)
    pairs = [{"pair": [a,b], **surface_equivalence(poses[a], poses[b], clean, operations)}
             for a,b in itertools.combinations(EXPECTED,2)
             if a[:2] == b[:2] and a not in RECLASSIFIED and b not in RECLASSIFIED]
    write_json(DEST / "structure_review.json", {"rows": reviewed, "same_species_intact_pairwise": pairs,
                                               "scientific_acceptance": False})
    write_json(DEST / "batch_manifest.json", {"created_at": now, "entries": entries,
                                              "structure_review_sha256": sha256_file(DEST / "structure_review.json")})


def launch():
    batch = load_json_object(DEST / "batch_manifest.json")
    require([row["name"] for row in batch["entries"]] == EXPECTED, "Wrong batch scope")
    for entry in batch["entries"]:
        run = Path(entry["workdir"])
        require(submission_status(run)["status"] == "NOT_RESERVED", "Existing reservation: " + entry["name"])
        require(sha256_file(run / "decision.json") == entry["decision_sha256"], "Decision changed")
        decision = load_json_object(run / "decision.json")
        require_action(run / "decision.json", "SUBMIT_VASP", decision["state_sha256"])
    for entry in batch["entries"]:
        run = Path(entry["workdir"])
        result = submit(run, run / "decision.json", "sunboquan-codex", entry["remote_dir"],
                        entry["potcar_source"], entry["potcar_sha256"], "SUBMIT_VASP")
        print(entry["name"], result["job_id"], result["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    launch() if args.submit else prepare()
