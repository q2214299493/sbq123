"""Prepare reviewed adsorption inputs; submission uses the owning executor only."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from scripts.artifact_io import sha256_file, write_json
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.neb_agent.submission import preflight, submit, submission_status
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, validate_decision
from scripts.vasp_inputs import build_fe110_adsorption_relaxation

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "vasp_batch_v1"
REMOTE = "~/sbq/Fe110/adsorption/fe110_five_c2_20261006"
POTCARS = {
    "Fe C H": ("Fe_C_H", "bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a"),
    "Fe C O H": ("Fe_C_O_H", "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"),
    "Fe O C H": ("Fe_O_C_H", "cfdeb95d5ce5ab92e2ff0c0cdd1cd3870fbbe3a929822c631e09fd828c511a4f"),
}


def prepare():
    if DEST.exists():
        raise FileExistsError("Do not overwrite an existing hash-bound VASP batch")
    sources = json.loads((BASE / "candidate_review.json").read_text())
    review = json.loads((BASE / "gpu_return_review.json").read_text())
    assert len(review["selected"]) == 9
    candidates = {f"{c['species_id']}_cfg{c['config_id']}": c for c in sources["candidates"]}
    records = {c["candidate"]: c for c in review["records"]}
    threshold_path = ROOT / "configs/true_fe110_production.yaml"
    thresholds = yaml.safe_load(threshold_path.read_text(encoding="utf-8"))
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    auth_source = Path(__file__).with_name("vasp_authorization.md")
    slab = read(ROOT / sources["slab"])
    now = datetime.now(timezone.utc).isoformat()
    entries = []
    for name in [*review["selected"], "03_cfg0"]:
        direct = name == "03_cfg0"
        candidate = candidates[name]
        source = ROOT / candidate["structure"] if direct else BASE / "gpu_batch_v4" / name / "output/job_2139/POSCAR"
        expected = candidate["structure_sha256"] if direct else records[name]["source_sha256"]
        assert sha256_file(source) == expected
        atoms = read(source)
        assert np.allclose(atoms.cell, slab.cell, atol=1e-10)
        assert np.allclose(atoms.positions[:18], slab.positions[:18], atol=1e-8)
        edges = connectivity_edges(atoms, list(range(45, len(atoms))), rules["connectivity"]["covalent_radius_scale"], rules["connectivity"]["minimum_bond_distance_angstrom"])
        actual = sorted(tuple(sorted(e)) for e in edges)
        expected_edges = sorted(tuple(e) for e in candidate["geometry_review"]["connectivity_edges_local_0based"])
        assert actual == expected_edges, (name, actual, expected_edges)
        minimum_contact = min(atoms.get_distance(i, j, mic=True) for i in range(45, len(atoms)) for j in range(45))
        assert minimum_contact >= rules["contact_validation"]["hard_contact_distance_angstrom"]
        run = DEST / (name + "_direct_vasp" if direct else name)
        run.mkdir(parents=True)
        shutil.copyfile(source, run / "POSCAR")
        build = build_fe110_adsorption_relaxation(run, cores=32)
        write_json(run / "candidate_manifest.json", {
            "species_id": candidate["species_id"], "care_code": candidate["care_code"],
            "formula": candidate["formula"], "connectivity": candidate["connectivity"],
            "source_structure": str(source), "source_sha256": expected,
            "source_role": "intact_pre_GPU_direct_VASP_fallback" if direct else "reviewed_GPU2139_prediction",
            "candidate_review_sha256": sha256_file(BASE / "candidate_review.json"),
            "gpu_return_review_sha256": sha256_file(BASE / "gpu_return_review.json"),
            "geometry_checks": {"cell_and_fixed_atoms_preserved": True, "target_edges_preserved": actual,
                                "minimum_surface_contact_A": minimum_contact},
            "builder": build, "scientific_status": "starting_candidate_only",
        })
        report = preflight(run, "adsorption_relaxation")
        assert report["passed"], report["errors"]
        bindings = {"thresholds": {"path": str(threshold_path), "sha256": sha256_file(threshold_path)},
                    "preflight": {"path": str(run / "submission_preflight.json"), "sha256": sha256_file(run / "submission_preflight.json")}}
        evidence = decide_execution({}, {}, thresholds, climb=False, path_reviewed=True,
                                    preflight=report, source_bindings=bindings)["EVIDENCE"]
        spec = (run / "POTCAR.spec").read_text().strip()
        potdir, potsha = POTCARS[spec]
        potcar = f"~/sbq/Fe110/potcars/{potdir}/POTCAR"
        remote = REMOTE + "/" + run.name
        auth = {
            "schema_version": 1, "document_kind": "user_execution_authorization",
            "action": "SUBMIT_VASP", "calculation_kind": "adsorption_relaxation", "authorized_at": now,
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
        assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_VASP"], decision.get("execution_authorization_error")
        validate_decision(decision)
        write_json(run / "decision.json", decision)
        entries.append({"name": run.name, "species_id": candidate["species_id"], "formula": candidate["formula"],
                        "connectivity": candidate["connectivity"], "workdir": str(run), "remote_dir": remote,
                        "cores": 32, "potcar_source": potcar, "potcar_sha256": potsha,
                        "bundle_sha256": report["bundle_sha256"], "decision_sha256": sha256_file(run / "decision.json")})
        print(run.name, "PREFLIGHT_AND_GATE_PASS", flush=True)
    write_json(DEST / "batch_manifest.json", {"created_at": now, "entries": entries})


def launch():
    batch = json.loads((DEST / "batch_manifest.json").read_text())
    # Check every input before the first external submission; never overwrite or retry an unknown reservation.
    for entry in batch["entries"]:
        run = Path(entry["workdir"])
        assert submission_status(run)["status"] == "NOT_RESERVED"
        assert sha256_file(run / "decision.json") == entry["decision_sha256"]
        validate_decision(json.loads((run / "decision.json").read_text()))
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
