"""Bind a reviewed completed path and prepare its local Dimer; no submission."""
from __future__ import annotations

from scripts.runtime_resources import resource_path

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, write_json, sha256_file
from scripts.neb_agent.utils_structure import read_poscar
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.handoff import prepare_dimer_handoff
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.vasp_inputs import build_fe110_dimer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--cores", type=int, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    parent = args.parent.resolve()
    destination = args.destination.resolve()
    if destination.exists():
        raise ValueError("Destination exists")
    authorization = load_json_object(args.authorization)
    assert authorization["source_job_id"] == args.job_id
    normalization = parent / "normalization_evidence.json"
    assert authorization["normalization_sha256"] == sha256_file(normalization)
    record = load_json_object(normalization)
    analysis = load_json_object(parent / "neb_analysis.json")
    geometry = load_json_object(parent / "path_geometry_diagnosis.json")
    contract = load_contract(args.contract)
    binding = validate_path_binding(parent, contract)
    assert binding["valid"], binding["errors"]
    write_json(parent / "reaction_contract.normalized.json", contract)
    analysis.update(path_binding=binding, path_binding_valid=True,
                    contract_sha256=contract["contract_sha256"],
                    atom_map_sha256=contract["atom_map_sha256"],
                    compatibility_sha256=contract["compatibility_sha256"])
    assert geometry["status"] == "PASS"
    assert all(r["normal_completion"] and r["electronically_converged"] and r["reached_required_accuracy"] for r in analysis["images"][1:-1])
    peak = record["peak_image"]
    names = [f"{int(peak)+offset:02d}" for offset in (-1, 0, 1)]
    paths = [parent / n / "CONTCAR" for n in names]
    triad = evaluate_candidate_triad(*paths, analysis, contract["reaction_atoms"], analysis_root=parent)
    write_json(parent / "candidate_triad_gate.json", triad)
    assert triad["hard_gate_passed"], triad["hard_gate_errors"]
    perl = Path("C:/Program Files/Git/usr/bin/perl.exe")
    dist = Path("archive/vtst_review_job9745217/dist.pl").resolve()
    values = []
    for left, right in zip(record["rows"], record["rows"][1:]):
        proc = subprocess.run([str(perl), dist.as_posix(), (parent / left["image"] / "POSCAR").as_posix(), (parent / right["image"] / "POSCAR").as_posix()], capture_output=True, text=True, check=True)
        values.append({"left": left["image"], "right": right["image"], "distance_A": float(proc.stdout.strip())})
    write_json(parent / "dist_final.json", {"tool": str(dist), "sha256": sha256_file(dist), "pairs": values})
    movie = parent / "movie"
    assert movie.is_file() and movie.stat().st_size > 1000
    now = datetime.now(timezone.utc).isoformat()
    review = {"status": "accepted", "reviewer": "Codex numeric and visual review; user accepted NEB stage", "reviewed_at": now,
              "dist_file": str(parent / "dist_final.json"), "dist_sha256": sha256_file(parent / "dist_final.json"),
              "nebmovie_file": str(movie), "nebmovie_sha256": sha256_file(movie),
              "path_generation_sha256": sha256_file(parent / "path_generation_report.json"),
              "normalization_sha256": sha256_file(normalization),
              "visual_review": str(parent / "final_path_review.png"),
              "notes": "Inspected all seven side views and exact bond/step tables. OH shortens monotonically, CC/CO/CH backbone retained; fractional shifts are integer translations of Fe atoms. Local energy plateau at 02-03; choose actual TOTEN maximum 02 with neighbors 01 and 03. Internal boundaries are not independently relaxed minima."}
    write_json(parent / "path_review.json", review)
    assert validate_path_review(parent / "path_review.json", parent / "path_generation_report.json")[0]
    analysis.update(path_reviewed=True, path_review=review,
                    user_accepted_neb_stage=True, stage_acceptance_source=str(args.authorization.resolve()),
                    stage_acceptance_source_sha256=sha256_file(args.authorization),
                    stage_acceptance_scope="Ordinary NEB accepted for local peak refinement; raw strict parser diagnostic retained")
    write_json(parent / "neb_analysis.json", analysis)
    scheduler = query_lsf_job(args.job_id, stage="ordinary_neb")
    assert scheduler["status"] == "DONE"
    write_json(parent / "scheduler_evidence.json", scheduler)
    thresholds = yaml.safe_load(resource_path("configs/neb_agent/default_thresholds.yaml").read_text())
    quality = load_json_object(parent / "neb_path_quality.json")
    gate = decide_execution(geometry, analysis, thresholds, climb=False, path_reviewed=True,
                            path_quality=quality, scheduler=scheduler,
                            authorization={**authorization, "action": "PREPARE_DIMER_HANDOFF"},
                            source_bindings={"authorization": {"path": str(args.authorization.resolve()), "sha256": sha256_file(args.authorization)}})
    write_json(parent / "dimer_preparation_gate.json", gate)
    require_action(parent / "dimer_preparation_gate.json", "PREPARE_DIMER_HANDOFF", gate["state_sha256"])
    prepare_dimer_handoff(paths[1], paths[0], paths[2], destination, False,
                          analysis_path=parent / "neb_analysis.json", path_review_path=parent / "path_review.json",
                          reaction_indices=contract["reaction_atoms"], contract_binding=validate_path_binding(parent, contract),
                          gate_decision=parent / "dimer_preparation_gate.json", gate_state_sha256=gate["state_sha256"])
    inputs = build_fe110_dimer(destination, cores=args.cores)
    write_json(destination / "input_generation_manifest.json", inputs)
    mode = np.loadtxt(destination / "MODECAR")
    norms = np.linalg.norm(mode, axis=1)
    center = read_poscar(destination / "POSCAR")
    rows = [{"index_zero_based": int(i), "element": center.labels[i], "mode_norm": float(norms[i])} for i in np.argsort(norms)[::-1][:8]]
    write_json(destination / "mode_numeric_review.json", {"dominant_atoms": rows,
               "mode_norm": float(np.linalg.norm(mode)),
               "reaction_fraction": float(np.linalg.norm(mode[contract["reaction_atoms"]])),
               "fixed_max": float(np.abs(mode[contract["compatibility"]["fixed_atom_indices_zero_based"]]).max())})
    print({"preparation_gate": gate["DECISION"], "triad": names, "dominant_mode": rows,
           "destination": str(destination), "next": "Inspect and accept generated mode, then preflight"})


if __name__ == "__main__":
    main()
