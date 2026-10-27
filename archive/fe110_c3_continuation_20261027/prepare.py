"""Prepare one bounded C3 continuation from closed9922624;never submit."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from ase.geometry import find_mic
from ase.io import read
import yaml

from archive.fe110_grouped_inputs_20261025.prepare import timing
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.vasp_result_gate import read_incar_values

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
QC = BASE / "grouped_qc_20261026_v2"
SOURCE = QC / "collection/family_0099_step020"
OUTPUT = BASE / "c3_continuation_20261027_v1"
HOST = "sunboquan-codex"
REMOTE_SOURCE = "~/sbq/Fe110/reico_grouped14_20261025_v1/optimizations/family_0099_step020"
REMOTE_TARGET = "~/sbq/Fe110/reico_c3_continue_20261027_v1/family_0099_step020_from9922624"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def timing_budget(outcar, maximum_steps=300):
    reference = timing(outcar)
    steps = []
    with outcar.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = re.search(r"LOOP\+.*real time\s+([\d.]+)", line)
            if match:
                steps.append(float(match[1]))
    if len(steps) != 80 or reference["cores"] != 32 or any(t <= 0 for t in steps):
        raise ValueError("exact80-step32-core timing reference required")
    estimates = [sum(steps[-20:])/20*maximum_steps/3600,
                 reference["elapsed_seconds"]/80*maximum_steps/3600]
    return {"maximum_additional_ionic_steps": maximum_steps, "cores": 32,
        "reference": reference, "last20_mean_step_seconds": sum(steps[-20:])/20,
        "full_cap_reference_wall_hours": [min(estimates), max(estimates)],
        "full_cap_reference_core_hours": [min(estimates)*32, max(estimates)*32],
        "actual_convergence_can_stop_earlier": True, "not_a_cost_cap_or_confidence_interval": True,
        "queue_time_excluded": True, "monetary_price_per_core_hour": None}


def source_geometry(frames):
    first = read(SOURCE / "POSCAR", format="vasp")
    final = read(SOURCE / "CONTCAR", format="vasp")
    final.pbc = [True, True, False]
    _, move = find_mic(final.positions-first.positions, final.cell, pbc=[True, True, False])
    if first.get_chemical_symbols() != final.get_chemical_symbols() or not np.allclose(first.cell, final.cell, atol=1e-10, rtol=0):
        raise ValueError("source atom order or cell changed")
    fixed = sorted(int(i) for c in final.constraints for i in c.get_indices())
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    distances = final.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    environment = chemical_environment(final, rules["connectivity"])
    environment["adsorbate_edges_local_0based"] = [list(edge) for edge in environment["adsorbate_edges_local_0based"]]
    if (fixed != list(range(18)) or max(move[:18]) > 1e-7
            or distances.min() < rules["contact_validation"]["hard_contact_distance_angstrom"]
            or max(move[18:45]) > rules["surface_reconstruction"]["maximum_slab_displacement_angstrom"]
            or environment["adsorbate_component_count"] != 1 or environment["graph_signature"] != frames[-1]["graph_signature"]):
        raise ValueError("continuation geometry requires upstream review")
    return {"status": "PASS_CONTINUATION_CANDIDATE_ONLY", "atom_order_preserved": True,
        "fixed18_max_displacement_A": float(max(move[:18])), "movable_Fe_max_displacement_A": float(max(move[18:45])),
        "minimum_pair_distance_A": float(distances.min()), "environment": environment,
        "last20_force_eV_A": [{"step": r["ionic_step"], "fmax": r["movable_fmax_eV_A"]} for r in frames[-20:]],
        "late_force_oscillates_and_convergence_not_guaranteed": True, "accepted_endpoint": False}


def live_precheck():
    target = REMOTE_TARGET.replace("~/", "$HOME/", 1)
    command = ("date -u; bjobs -a -w 9922624; busers -w; "
               f"if [ -e {target} ]; then echo TARGET_EXISTS; else echo TARGET_ABSENT; fi; "
               f"if [ -e {target}.submission-reservation ]; then echo LOCK_EXISTS; else echo LOCK_ABSENT; fi; "
               f"cd {REMOTE_SOURCE} && sha256sum POSCAR CONTCAR INCAR KPOINTS OUTCAR OSZICAR POTCAR")
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ControlMaster=no",
            "-o", "ControlPath=none", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", HOST, command]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=45, check=False)
    except subprocess.TimeoutExpired as exc:
        from datetime import datetime, timezone
        partial = exc.stdout or b""
        save_once(OUTPUT / ("precheck_timeout_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + ".json"),
                  {"command": command, "partial_stdout": partial.decode(errors="replace") if isinstance(partial, bytes) else partial,
                   "timeout_seconds": 45, "submitted": False})
        raise
    result = {"command": command, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
              "remote_writes": False}
    save_once(OUTPUT / "remote_precheck.json", result)
    if p.returncode or "TARGET_EXISTS" in p.stdout or "LOCK_EXISTS" in p.stdout:
        raise ValueError("source/target precheck incomplete or reserved")
    hashes = {m[2]: m[1] for m in re.finditer(r"^([0-9a-f]{64})\s+(\S+)\s*$", p.stdout, re.M)}
    receipt = load_json_object(SOURCE / "collection.json")
    if any(hashes.get(name) != receipt["remote"]["files"][name]["sha256"]
           for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OUTCAR", "OSZICAR", "POTCAR")):
        raise ValueError("remote source differs from audited collection")
    if not any(line.split()[:3] == ["9922624", "nsgkn_chengdj3", "DONE"] for line in p.stdout.splitlines()):
        raise ValueError("source job is not authoritatively DONE")
    return result


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    review = load_json_object(QC / "independent_verification.json")
    if not source_file_manifest_valid(review) or review["status"] != "PASS":
        raise ValueError("source per-frame QC binding changed")
    frames = load_json_object(QC / "case_qc/family_0099_step020.json")["samples"]
    if len(frames) != 80 or any(r["data_qc_status"] != "PASS" or r["magnetic_review_flags"] for r in frames):
        raise ValueError("source trajectory needs electronic/magnetic review")
    receipt = load_json_object(SOURCE / "collection.json")
    for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OUTCAR", "OSZICAR"):
        if sha256_file(SOURCE / name) != receipt["remote"]["files"][name]["sha256"]:
            raise ValueError("audited source file changed")
    geometry = source_geometry(frames)
    save_once(OUTPUT / "geometry_review.json", geometry)
    budget = timing_budget(SOURCE / "OUTCAR")
    save_once(OUTPUT / "budget.json", budget)
    live_precheck()
    destination = OUTPUT / "inputs"
    if destination.exists():
        raise ValueError("preserve prepared inputs;use existing plan rather than overwrite")
    destination.mkdir()
    (destination / "POSCAR").write_bytes((SOURCE / "CONTCAR").read_bytes())
    metadata = build_fe110_adsorption_relaxation(destination, cores=32, screening=False, write_local_moments=True)
    save_once(destination / "candidate_manifest.json", {"relaxation_stage": "routine_production", "write_local_moments": True,
        "source_job_id": "9922624", "source_structure_sha256": sha256_file(SOURCE / "CONTCAR"),
        "purpose": "existing_C3_trajectory_continuation_for_low_force_labels", "accepted_endpoint": False})
    source_incar = read_incar_values(SOURCE / "INCAR")
    new_incar = read_incar_values(destination / "INCAR")
    differences = {k: [source_incar.get(k), new_incar.get(k)] for k in source_incar.keys() | new_incar.keys()
                   if source_incar.get(k) != new_incar.get(k)}
    if differences != {"NSW": ["80", "300"]}:
        raise ValueError("unexpected continuation INCAR change " + str(differences))
    metadata_path = BASE / "grouped_inputs_20261025_v1/optimizations/family_0099_step020/POTCAR.metadata.json"
    (destination / "POTCAR.metadata.json").write_bytes(metadata_path.read_bytes())
    save_once(destination / "input_profile.json", metadata)
    argv = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(destination),
        "--incar", str(destination / "INCAR"), "--poscar", str(destination / "POSCAR"),
        "--calculation-type", "adsorption_GO", "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
    p = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=40, check=False)
    (destination / "incar_custodian_validation.json").write_bytes(p.stdout)
    if p.returncode:
        raise ValueError("custodian validation command failed")
    validation = load_json_object(destination / "incar_custodian_validation.json")
    if validation["blockers"] or validation["status"] != "VALIDATION_ONLY":
        raise ValueError("custodian blocked continuation")
    check = preflight(destination, "adsorption_relaxation", write_report=False)
    save_once(destination / "submission_preflight.json", check)
    if not check["passed"]:
        raise ValueError("native continuation preflight failed " + str(check["errors"]))
    sources = [Path(__file__), CUSTODIAN, ROOT / "configs/true_fe110_production.yaml", ROOT / "scripts/vasp_inputs.py",
        ROOT / "scripts/adsorption/preflight_fe110_adsorption.py", QC / "independent_verification.json",
        QC / "case_qc/family_0099_step020.json", SOURCE / "collection.json", OUTPUT / "geometry_review.json",
        OUTPUT / "budget.json", OUTPUT / "remote_precheck.json", *[SOURCE / n for n in ("POSCAR", "CONTCAR", "INCAR", "OUTCAR", "OSZICAR")],
        *[destination / n for n in [*check["files"], "POTCAR.metadata.json", "input_profile.json", "incar_custodian_validation.json", "submission_preflight.json"]]]
    plan = {"status": "PREPARED_NOT_SUBMITTED_AWAITING_COST_CONFIRMATION", "source_job_id": "9922624",
        "directory": str(destination), "remote_target": REMOTE_TARGET, "cores": 32, "maximum_additional_steps": 300,
        "force_convergence_eV_A": .02, "training_frame_force_threshold_eV_A": .05, "changes": differences,
        "source_CONTCAR_sha256": sha256_file(SOURCE / "CONTCAR"), "bundle_sha256": check["bundle_sha256"],
        "input_hashes": check["files"], "budget": budget, "geometry_review": geometry["status"],
        "scheduler_quota_target_POTCAR_and_native_execution_gate_recheck_required": True,
        "automatic_retry_or_continuation": False, "execution_authorized": False, "uploaded": False, "submitted": False,
        "training_started": False, "source_files": source_file_manifest(sources)}
    save_once(OUTPUT / "plan.json", plan)
    print({k: plan[k] for k in ("status", "cores", "maximum_additional_steps", "force_convergence_eV_A", "bundle_sha256")})
    return plan


if __name__ == "__main__":
    run()
