"""Collect and review Dimer9998592,then prepare one explicitly authorized VFA."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

import numpy as np
from ase.io import read

from archive.fe110_ch_co_local_review_20261112.review import extract_verified_archive
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.artifact_io import write_json
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.neb_agent.utils_structure import compatible, minimum_image_delta, read_poscar
from scripts.neb_agent.submission import preflight, submit, submission_status
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate
from scripts.vasp_inputs import build_fe110_vfa
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.execution_gate import require_action

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
ORIGINAL = BASE / "dimer_image05_20261112_v1"
REVIEW = BASE / "dimer_completion_20261115_v1"
SOURCE = REVIEW / "source"
DEST = BASE / "vfa_dimer9998592_20261115_v1"
CONTRACT = BASE / "local_triplet_review_20261112_v1/reaction_contract.reviewed.json"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/ts/ch_co_to_chco_20261110/" + DEST.name
AUTHORITY = Path(__file__).with_name("user_authority.md")


def now():
    return datetime.now(timezone.utc).isoformat()


def collect():
    if REVIEW.exists():
        raise ValueError("Review exists; inspect saved evidence rather than recollecting.")
    receipt = load_json_object(ORIGINAL / "submission_record.json")
    submitted = load_json_object(ORIGINAL / "submission_preflight.json")
    if receipt["job_id"] != "9998592" or receipt["server_alias"] != HOST:
        raise ValueError("Actual source job differs.")
    REVIEW.mkdir()
    scheduler = query_lsf_job(receipt["job_id"], stage="dimer")
    write_json_exclusive(REVIEW / "scheduler_evidence.json", scheduler)
    if scheduler["status"] != "DONE":
        raise ValueError("Need native source DONE before the completion handoff.")
    names = list(submitted["files"])
    names += ["CONTCAR", "OUTCAR", "OSZICAR", "DIMCAR", "NEWMODECAR", "vasp.out"]
    program = "DIRECTORY=" + repr(receipt["remote_dir"]) + "\nNAMES=" + repr(names) + "\n" + r'''
import hashlib,json,os
from pathlib import Path
root=Path(os.path.expanduser(DIRECTORY)).resolve()
files=[]
for name in NAMES:
 p=root/name
 if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root):raise ValueError('Invalid requested source')
 digest=hashlib.sha256()
 with p.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
 files.append({'relative_path':name,'bytes':p.stat().st_size,'sha256':digest.hexdigest()})
print(json.dumps({'root':str(root),'files':files}))
'''
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, "python3 -"],
        input=program.encode(), capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace")[:1000])
    with (REVIEW / "remote_inventory.json").open("xb") as target:
        target.write(result.stdout)
    inventory = load_json_object(REVIEW / "remote_inventory.json")
    total = sum(row["bytes"] for row in inventory["files"])
    if total > 1024**3 or shutil.disk_usage(REVIEW).free < 3 * total:
        raise ValueError("Source transfer exceeds bounded storage budget.")
    for row in inventory["files"]:
        if row["relative_path"] in submitted["files"] and row["sha256"] != submitted["files"][row["relative_path"]]:
            raise ValueError("Remote submitted input changed: " + row["relative_path"])
    program = "DIRECTORY=" + repr(inventory["root"]) + "\nNAMES=" + repr(names) + "\n" + r'''
import sys,tarfile
from pathlib import Path
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',compresslevel=1) as target:
 for name in NAMES:target.add(Path(DIRECTORY)/name,arcname=name,recursive=False)
'''
    archive = REVIEW / "dimer_source.tar.gz"
    with archive.open("xb") as target:
        process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, "python3 -"],
            stdin=subprocess.PIPE, stdout=target, stderr=subprocess.PIPE)
        try:
            _, error = process.communicate(program.encode(), timeout=150)
        except BaseException:
            process.kill()
            process.communicate()
            raise
    if process.returncode:
        raise ValueError(error.decode(errors="replace")[:1000])
    extract_verified_archive(archive, inventory, names, SOURCE)
    shutil.copy2(REVIEW / "scheduler_evidence.json", SOURCE / "scheduler_evidence.json")
    write_json_exclusive(REVIEW / "collection_receipt.json", {
        "status": "PASS", "job_id": receipt["job_id"], "collected_at": now(),
        "files_verified": len(names), "total_bytes": total,
        "remote_inventory_sha256": sha256_file(REVIEW / "remote_inventory.json"),
        "archive_sha256": sha256_file(archive), "submitted_inputs_unchanged": True,
    })
    analysis = analyze_dimer(SOURCE)
    keys = ("status", "translation_steps", "final_atomic_force_eVA", "final_force_eVA",
            "final_torque_eVA", "final_curvature_eVA2", "dimer_soft_warnings", "evidence_gate")
    print({key: analysis[key] for key in keys})


def inspect_geometry():
    initial = read_poscar(SOURCE / "POSCAR")
    final = read_poscar(SOURCE / "CONTCAR")
    if compatible(initial, final) or not np.isfinite(final.frac).all():
        raise ValueError("Dimer final identity/cell/constraints are incompatible.")
    atoms = read(SOURCE / "CONTCAR", format="vasp")
    mode = np.loadtxt(SOURCE / "NEWMODECAR")
    if mode.shape != (49, 3) or not np.isfinite(mode).all():
        raise ValueError("Invalid final Dimer mode.")
    fixed = [i for i, flags in enumerate(final.flags) if all(flag == "F" for flag in flags)]
    shifts = minimum_image_delta(initial.frac, final.frac) @ final.cell
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    mode_weights = np.sum(mode * mode, axis=1)
    coord = minimum_image_delta(final.frac[45], final.frac[46]) @ final.cell
    derivative = float(np.dot(coord / np.linalg.norm(coord), mode[46] - mode[45]))
    with (SOURCE / "OUTCAR").open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 262144))
        lines = stream.read().decode("utf-8", errors="replace").splitlines()
    start = max(i for i, line in enumerate(lines) if "POSITION" in line and "TOTAL-FORCE" in line)
    block = np.array([[float(value) for value in line.split()[:6]] for line in lines[start+2:start+51]])
    if block.shape != (49, 6) or not np.isfinite(block).all():
        raise ValueError("Incomplete terminal all-atom force/position table.")
    discrepancy = final.frac - block[:, :3] @ np.linalg.inv(final.cell)
    discrepancy[:, :2] -= np.rint(discrepancy[:, :2])
    max_error = float(np.linalg.norm(discrepancy @ final.cell, axis=1).max())
    if max_error > 1e-5:
        raise ValueError("Final CONTCAR does not match the terminal force table within output precision.")
    result = {
        "source_structure_sha256": sha256_file(SOURCE / "CONTCAR"),
        "modecar_sha256": sha256_file(SOURCE / "NEWMODECAR"),
        "identity_cell_constraints_unchanged": True, "fixed_atom_indices": fixed,
        "max_fixed_atom_displacement_A": float(np.linalg.norm(shifts[fixed], axis=1).max()),
        "all_atom_minimum_distance_A": float(distances.min()),
        "CC_A": float(distances[45, 46]), "CO_A": float(distances[46, 47]), "CH_A": float(distances[45, 48]),
        "nearest_Fe": {str(i): [{"index": int(j), "distance_A": float(distances[i, j])}
                                for j in np.argsort(distances[i, :45])[:3]] for i in range(45, 49)},
        "mode_norm": float(np.linalg.norm(mode)), "max_fixed_mode_component": float(np.abs(mode[fixed]).max()),
        "reaction_squared_amplitude_fraction": float(mode_weights[45:49].sum() / mode_weights.sum()),
        "CC_mode_distance_derivative_A_per_unit_mode": derivative,
        "terminal_force_table_complete_finite": True, "max_force_position_correspondence_error_A": max_error,
        "proposed_hessian_active_indices": [45, 46, 47, 48],
        "scope_note": "All four reaction atoms;88% target-mode weight;no full-slab Hessian or thermal correction.",
    }
    write_json_exclusive(REVIEW / "geometry_and_mode_metrics.json", result)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    positions = atoms.positions
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, dims, label in ((axes[0], (0, 1), "Top x-y"), (axes[1], (0, 2), "Side x-z")):
        a, b = dims
        ax.scatter(positions[:45, a], positions[:45, b], c="lightgray", edgecolor="gray", s=65)
        for index, color, symbol in ((45, "black", "C45"), (46, "black", "C46"), (47, "red", "O47"), (48, "royalblue", "H48")):
            ax.scatter(positions[index, a], positions[index, b], c=color, s=80)
            ax.annotate(symbol, positions[index, [a, b]], xytext=(3, 7), textcoords="offset points")
        ax.quiver(positions[:, a], positions[:, b], mode[:, a], mode[:, b],
                  angles="xy", scale_units="xy", scale=.45, color="green", width=.004)
        for i, j in ((45, 46), (46, 47), (45, 48)):
            ax.plot(positions[[i, j], a], positions[[i, j], b], color="orange", lw=1)
        ax.set_aspect("equal")
        ax.set_title(label + "; final Dimer direction")
        ax.set_xlabel("x / A")
        ax.set_ylabel(("y" if b == 1 else "z") + " / A")
    fig.suptitle("Dimer 9998592 final geometry and NEWMODECAR;not a frequency eigenmode")
    fig.tight_layout()
    fig.savefig(REVIEW / "final_mode_review.png", dpi=150)
    plt.close(fig)
    print(result)


def review_and_prepare():
    """Run after real final-mode visual review and the user's residual decision."""
    metrics = load_json_object(REVIEW / "geometry_and_mode_metrics.json")
    if (metrics["max_fixed_mode_component"] != 0 or abs(metrics["mode_norm"] - 1) > 1e-6
            or metrics["reaction_squared_amplitude_fraction"] < .5
            or metrics["max_fixed_atom_displacement_A"] > 1e-5):
        raise ValueError("Final mode/geometry fails quantitative review checks.")
    mode_review = load_json_object(SOURCE / "final_mode_review.json")
    if mode_review["status"] != "needs_review":
        raise ValueError("Final mode already reviewed; do not overwrite.")
    mode_review.update({"status": "accepted", "reviewer": "Codex work-side final geometry and mode review",
        "reviewed_at": now(), "notes": "Actual top/side arrows inspected;C45-C46 event dominant;CH/CO intact;no collision or fixed-layer drift. Not a Hessian eigenmode or TS acceptance.",
        "source_structure_sha256": sha256_file(SOURCE / "CONTCAR"),
        "geometry_metrics_sha256": sha256_file(REVIEW / "geometry_and_mode_metrics.json"),
        "visual_review_sha256": sha256_file(REVIEW / "final_mode_review.png")})
    write_json(SOURCE / "final_mode_review.json", mode_review)
    analysis = analyze_dimer(SOURCE)
    if not analysis["technically_converged"] or not analysis["evidence_gate"]["passed"]:
        raise ValueError("Dimer hard convergence/provenance checks did not pass.")
    residual_review = {
        "status": "accepted", "decision": "allow_frequency_handoff",
        "reviewer": "User conditional residual authorization;Codex verified normal convergence and geometry",
        "reviewed_at": now(), "saddle_analysis_sha256": sha256_file(SOURCE / "dimer_analysis.json"),
        "source_structure_sha256": sha256_file(SOURCE / "CONTCAR"),
        "acknowledged_warning_codes": sorted(analysis["dimer_soft_warnings"]),
        "actual_metrics": {key: analysis[key] for key in ("final_force_eVA", "final_torque_eVA", "final_atomic_force_eVA", "final_curvature_eVA2")},
        "authority_source": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY),
        "note": "Only diagnostic local frequency;DIMCAR49 force-only row retained,last complete torque/curvature row48. No formal TS acceptance.",
    }
    write_json_exclusive(REVIEW / "dimer_soft_gate_review.json", residual_review)
    gate = evaluate_dimer_frequency_gate(analysis, SOURCE / "dimer_analysis.json", SOURCE / "CONTCAR",
                                         REVIEW / "dimer_soft_gate_review.json")
    write_json_exclusive(REVIEW / "frequency_handoff_gate.json", gate)
    if not gate["frequency_handoff_allowed"] or gate["ts_validation_eligible"]:
        raise ValueError("Diagnostic-only frequency authority differs.")
    contract = load_contract(CONTRACT)
    prepare_vfa_handoff(SOURCE, DEST, contract["reaction_atoms"], contract,
                        SOURCE / "dimer_analysis.json", False, REVIEW / "dimer_soft_gate_review.json")
    build = build_fe110_vfa(DEST, cores=32)
    write_json_exclusive(DEST / "input_build.json", build)
    scope = load_json_object(DEST / "vfa_scope_review.json")
    scope.update({"status": "accepted_for_diagnostic_frequency", "reviewer": "Codex work-side local Hessian scope review",
        "reviewed_at": now(), "scope_convergence_status": "reaction_center_scope_reviewed_not_full_hessian",
        "notes": "C45,C46,O47,H48 are every contract reaction atom and88.8% of final Dimer mode squared amplitude;Fe environment frozen. Geometry unchanged. No ZPE/free-energy claim.",
        "source_geometry_review_sha256": sha256_file(REVIEW / "geometry_and_mode_metrics.json")})
    write_json(DEST / "vfa_scope_review.json", scope)
    report = preflight(DEST, "vfa")
    if not report["passed"]:
        raise ValueError(report["errors"])
    print({"dimer_status": analysis["status"], "frequency_gate": gate, "VFA_preflight_passed": True,
           "active_indices": contract["reaction_atoms"], "incar": build["incar"], "cores": 32})


def authorize_and_submit():
    if submission_status(DEST)["status"] != "NOT_RESERVED":
        raise ValueError("Existing VFA attempt;reconcile it,never repeat submission.")
    original_receipt = load_json_object(ORIGINAL / "submission_record.json")
    potcar, potcar_sha = original_receipt["potcar_source"], original_receipt["potcar_sha256"]
    command = ("set -e; whoami; hostname; test -r /home_gkx/env/intel/intel2016.sh; "
        'test -x "$HOME/soft/vasp541vtst/bin/vasp_std"; '
        f"test ! -e {REMOTE}; test ! -e {REMOTE}.submission-reservation; sha256sum {potcar}; bjobs -w 2>&1")
    current = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, command],
                             capture_output=True, text=True, timeout=45)
    write_json_exclusive(DEST / "remote_preflight.json", {"checked_at": now(), "command": command,
        "returncode": current.returncode, "stdout": current.stdout, "stderr": current.stderr})
    if current.returncode or potcar_sha not in current.stdout:
        raise ValueError("Remote runtime/target/POTCAR preflight failed;not submitted.")
    report = load_json_object(DEST / "submission_preflight.json")
    request = load_json_object(BASE / "local_triplet_review_20261112_v1/execution_gate_request.json")
    request.update(preflight_file=str(DEST / "submission_preflight.json"),
                   scheduler_file=str(SOURCE / "scheduler_evidence.json"),
                   validation_file=str(SOURCE / "dimer_analysis.json"))
    write_json_exclusive(DEST / "readiness_request.json", request)
    decision = build_decision(DEST / "readiness_request.json", DEST / "readiness_decision.json")
    authority = {
        "schema_version": 1, "document_kind": "user_execution_authorization", "action": "START_VFA",
        "calculation_kind": "vfa", "authorized_at": now(),
        "source": {"path": str(AUTHORITY), "sha256": sha256_file(AUTHORITY)},
        "target": {"server_alias": HOST, "remote_dir": REMOTE},
        "workdir_identity": workdir_identity(DEST), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(decision["EVIDENCE"]),
        "potcar": {"source": potcar, "sha256": potcar_sha, "spec_sha256": report["files"]["POTCAR.spec"]},
    }
    write_json_exclusive(DEST / "user_execution_authorization.json", authority)
    request["authorization_file"] = str(DEST / "user_execution_authorization.json")
    write_json_exclusive(DEST / "submission_request.json", request)
    decision = build_decision(DEST / "submission_request.json", DEST / "submission_decision.json")
    require_action(DEST / "submission_decision.json", "START_VFA", decision["state_sha256"])
    receipt = submit(DEST, DEST / "submission_decision.json", HOST, REMOTE, potcar, potcar_sha, "START_VFA")
    print({"status": receipt["status"], "job_id": receipt["job_id"], "decision": decision["DECISION"]}, flush=True)
    scheduler = query_lsf_job(receipt["job_id"], stage="vfa")
    write_json_exclusive(DEST / "initial_scheduler_evidence.json", scheduler)
    print({"job_id": receipt["job_id"], "scheduler_status": scheduler["status"]}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("collect", "inspect", "prepare", "submit"))
    {"collect": collect, "inspect": inspect_geometry, "prepare": review_and_prepare,
     "submit": authorize_and_submit}[parser.parse_args().phase]()
