"""Source-bound mode12 assignment only;no TS approval,registry writes or jobs."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

import numpy as np
from ase.io import read

from archive.fe110_ch_co_local_review_20261112.review import extract_verified_archive
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_outcar, parse_oszicar
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_validation.analyze_vfa import FREQUENCY_PATTERN, _frequency_modes
from scripts.ts_validation.analyze_vfa import analyze_vfa, same_vfa_geometry, vfa_scope_checks
from scripts.ts_strategy_engine.contract import load_contract

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
INITIAL = BASE / "vfa_dimer9998592_20261115_v1"
DIMER = BASE / "dimer_completion_20261115_v1/source"
OUT = BASE / "vfa_mode12_review_20261115_v1"
RAW = OUT / "raw"


def collect():
    if OUT.exists():
        raise ValueError("Review exists;reuse its bound source rather than overwriting it.")
    OUT.mkdir()
    receipt = load_json_object(INITIAL / "submission_record.json")
    inputs = load_json_object(INITIAL / "submission_preflight.json")["files"]
    scheduler = query_lsf_job(receipt["job_id"], stage="vfa")
    write_json_exclusive(OUT / "scheduler_evidence.json", scheduler)
    if scheduler["status"] != "DONE":
        raise ValueError("Mode review requires completed source output.")
    names = list(inputs) + ["OUTCAR", "OSZICAR", "CONTCAR", "vasp.out"]
    preamble = "DIRECTORY=" + repr(receipt["remote_dir"]) + "\nNAMES=" + repr(names) + "\n"
    program = preamble + r'''
import hashlib,json,os
from pathlib import Path
root=Path(os.path.expanduser(DIRECTORY)).resolve()
files=[]
for name in NAMES:
 p=root/name
 if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root):raise ValueError('Invalid source')
 digest=hashlib.sha256()
 with p.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
 files.append({'relative_path':name,'bytes':p.stat().st_size,'sha256':digest.hexdigest()})
print(json.dumps({'root':str(root),'files':files}))
'''
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", receipt["server_alias"], "python3 -"]
    result = subprocess.run(ssh, input=program.encode(), capture_output=True, timeout=45)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace")[:1000])
    with (OUT / "remote_inventory.json").open("xb") as target:
        target.write(result.stdout)
    inventory = load_json_object(OUT / "remote_inventory.json")
    if sum(item["bytes"] for item in inventory["files"]) > 100_000_000:
        raise ValueError("Review exceeds bounded transfer budget.")
    for item in inventory["files"]:
        if item["relative_path"] in inputs and item["sha256"] != inputs[item["relative_path"]]:
            raise ValueError("Submitted input changed: " + item["relative_path"])
    program = preamble + r'''
import os,sys,tarfile
from pathlib import Path
root=Path(os.path.expanduser(DIRECTORY)).resolve()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',compresslevel=1) as target:
 for name in NAMES:target.add(root/name,arcname=name,recursive=False)
'''
    archive = OUT / "frequency_source.tar.gz"
    with archive.open("xb") as target:
        process = subprocess.Popen(ssh, stdin=subprocess.PIPE, stdout=target, stderr=subprocess.PIPE)
        try:
            _, error = process.communicate(program.encode(), timeout=90)
        except BaseException:
            process.kill()
            process.communicate()
            raise
    if process.returncode:
        raise ValueError(error.decode(errors="replace")[:1000])
    extract_verified_archive(archive, inventory, names, RAW)
    write_json_exclusive(OUT / "collection_receipt.json", {"status": "PASS", "files_verified": len(names),
        "job_id": receipt["job_id"], "collected_at": datetime.now(timezone.utc).isoformat(),
        "inventory_sha256": sha256_file(OUT / "remote_inventory.json"), "inputs_unchanged": True})
    print("PASS", len(names), "source files;no remote writes")


def full_mode(text, index, natoms):
    """Read the sole Cartesian dynamical-matrix block,not a truncated top-ten list."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if (match := FREQUENCY_PATTERN.search(line))
              and int(match.group(1)) == index]
    if len(starts) != 1:
        raise ValueError("Expected one native mode block;review multiple representations explicitly.")
    start = starts[0]
    header = next((line for line in reversed(lines[:start]) if "Eigenvectors" in line), "")
    if "Eigenvectors and eigenvalues of the dynamical matrix" not in header:
        raise ValueError("Unknown eigenvector representation.")
    rows = []
    for line in lines[start+1:]:
        fields = line.split()
        if len(fields) == 6:
            try:
                row = [float(value) for value in fields]
            except ValueError:
                if rows:
                    break
                continue
            rows.append(row)
            if len(rows) == natoms:
                break
        elif rows:
            break
    result = np.array(rows)
    if result.shape != (natoms, 6) or not np.isfinite(result).all():
        raise ValueError("Incomplete or nonfinite mode rows.")
    return result[:, :3], result[:, 3:], header


def bond_derivatives(atoms, vector):
    result = {}
    for label, i, j in (("CC", 45, 46), ("CO", 46, 47), ("CH", 45, 48)):
        bond = atoms.get_distance(i, j, mic=True, vector=True)
        result[label] = float(np.dot(bond / np.linalg.norm(bond), vector[j] - vector[i]))
    return result


def measure():
    text = (RAW / "OUTCAR").read_text(encoding="utf-8", errors="replace")
    state = parse_outcar(RAW / "OUTCAR")
    oz = parse_oszicar(RAW / "OSZICAR")
    modes = _frequency_modes(text)
    imaginary = [mode for mode in modes if mode["imaginary"]]
    if not state["normal_completion"] or state["fatal_keywords"] or len(modes) != 12:
        raise ValueError("Frequency calculation is not complete/clean.")
    if len(imaginary) != 1 or imaginary[0]["mode_index"] != 12:
        raise ValueError("Expected sole imaginary mode12.")
    atoms = read(RAW / "POSCAR", format="vasp")
    positions, eigenvector, representation = full_mode(text, 12, len(atoms))
    differences = (positions - atoms.positions) @ np.linalg.inv(atoms.cell.array)
    differences[:, :2] -= np.rint(differences[:, :2])
    position_error = float(np.linalg.norm(differences @ atoms.cell.array, axis=1).max())
    if position_error > 1e-5:
        raise ValueError("Mode reference positions do not match submitted saddle.")
    masses_by_species = [float(value) for value in re.findall(r"(?m)^\s*POMASS\s*=\s*([-+0-9.Ee]+)", text)]
    if len(masses_by_species) < 4 or any(value <= 0 for value in masses_by_species[:4]):
        raise ValueError("Actual OUTCAR species masses are missing/invalid.")
    masses = np.repeat(masses_by_species[:4], [45, 2, 1, 1])
    vector = eigenvector / np.sqrt(masses[:, None])
    vector /= np.linalg.norm(vector)
    # Sign is arbitrary;choose positive q to shorten the intended C-C bond.
    sign = -1 if bond_derivatives(atoms, vector)["CC"] > 0 else 1
    vector *= sign
    raw_vector = eigenvector / np.linalg.norm(eigenvector) * sign
    fixed = list(range(45))
    if np.abs(vector[fixed]).max() > 1e-10:
        raise ValueError("Unexpected motion outside the reviewed partial Hessian.")
    dimer = np.loadtxt(DIMER / "NEWMODECAR")
    active_dimer = dimer.copy()
    active_dimer[fixed] = 0
    def overlap(other):
        return float(abs(np.sum(other * vector)) / (np.linalg.norm(other) * np.linalg.norm(vector)))
    scale = .10 / np.linalg.norm(vector, axis=1).max()
    frames = []
    for q in (-1, 0, 1):
        frame = atoms.copy()
        frame.positions += q * scale * vector
        frames.append(frame)
    frame_distances = [{label: float(frame.get_distance(i, j, mic=True))
        for label, i, j in (("CC", 45, 46), ("CO", 46, 47), ("CH", 45, 48))} for frame in frames]
    result = {"mode_index": 12, "imaginary_frequency_cm1": imaginary[0]["frequency_cm1"],
        "normal_completion": True, "force_evaluations": oz["ionic_steps"], "modes_count": len(modes),
        "original_header": representation, "raw_eigenvector_norm": float(np.linalg.norm(eigenvector)),
        "POMASS_by_species_Fe_C_O_H": masses_by_species[:4],
        "physical_vector_conversion": "Cartesian dynamical-matrix eigenvector divided by sqrt(actual POMASS),then normalized",
        "vector_sign": "positive phase shortens C45-C46;sign itself is arbitrary",
        "physical_displacements_normalized": vector.tolist(), "raw_eigenvectors": eigenvector.tolist(),
        "position_correspondence_max_error_A": position_error,
        "derivatives_A_per_unit_norm_physical_vector": bond_derivatives(atoms, vector),
        "derivatives_raw_eigenvector_normalized": bond_derivatives(atoms, raw_vector),
        "squared_displacement_fractions": {str(i): float(np.sum(vector[i]**2)) for i in range(45, 49)},
        "dimer_overlap_full_space_abs_cosine": overlap(dimer),
        "dimer_overlap_common_active_set_abs_cosine": overlap(active_dimer),
        "three_frame_bond_lengths_A": frame_distances,
        "visualization_scale": "max atomic shift0.10A at each sign;not optimized endpoints or a connectivity test",
        "source_outcar_sha256": sha256_file(RAW / "OUTCAR"), "source_poscar_sha256": sha256_file(RAW / "POSCAR"),
        "dimer_mode_sha256": sha256_file(DIMER / "NEWMODECAR"),
        "scope": "four-atom local partial Hessian;no formal TS or kinetic eligibility"}
    write_json_exclusive(OUT / "mode12_metrics.json", result)
    render(frames, vector, frame_distances)
    print({key: value for key, value in result.items() if key not in ("physical_displacements_normalized", "raw_eigenvectors")})


def render(frames, vector, lengths):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    center = frames[1].positions
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for col, (frame, label) in enumerate(zip(frames, ("-q: C-C opening", "TS reference", "+q: C-C closing"), strict=True)):
        positions = frame.positions
        for row, (a, b) in enumerate(((0, 1), (0, 2))):
            ax = axes[row, col]
            ax.scatter(positions[:45, a], positions[:45, b], c="lightgray", edgecolor="gray", s=85)
            for i, color, name in ((45, "black", "C45"), (46, "black", "C46"), (47, "red", "O47"), (48, "royalblue", "H48")):
                ax.scatter(positions[i, a], positions[i, b], c=color, s=90)
                ax.annotate(name, positions[i, [a, b]], xytext=(3, 6), textcoords="offset points")
            for i, j in ((45, 46), (46, 47), (45, 48)):
                ax.plot(positions[[i, j], a], positions[[i, j], b], color="orange", lw=1.5)
            if col == 1:
                ax.quiver(center[45:, a], center[45:, b], vector[45:, a], vector[45:, b],
                          angles="xy", scale_units="xy", scale=1.4, color="green", width=.006)
            ax.set_xlim(center[45:, a].min()-1.2, center[45:, a].max()+1.3)
            ax.set_ylim(center[45:, b].min()-(1.4 if row == 0 else 2), center[45:, b].max()+.8)
            ax.set_aspect("equal")
            ax.set_xlabel("x / A")
            ax.set_ylabel(("y" if row == 0 else "z") + " / A")
            if row == 0:
                ax.set_title(f"{label}\nC-C {lengths[col]['CC']:.4f} A")
    fig.suptitle("2260 mode12:318.644i cm^-1;mass-corrected local displacement,not IRC or relaxed endpoints")
    fig.tight_layout()
    fig.savefig(OUT / "mode12_three_frames.png", dpi=160)
    plt.close(fig)


def finalize():
    """After quantitative review and actual visual inspection;never accepts a TS."""
    metrics = load_json_object(OUT / "mode12_metrics.json")
    contract = load_contract(BASE / "local_triplet_review_20261112_v1/reaction_contract.reviewed.json")
    if not same_vfa_geometry(DIMER / "CONTCAR", RAW / "POSCAR") or not all(vfa_scope_checks(RAW).values()):
        raise ValueError("Current saddle geometry or reviewed partial-Hessian scope differs.")
    rsi_root = Path("C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/chco_mode12_assignment_20261115_v1")
    rsi = load_json_object(rsi_root / "run_receipt.json")
    selection = load_json_object(rsi_root / "rsi_selection.json")
    review = {
        "status": "accepted_for_target_mode_review_only", "source_method": "dimer",
        "mode_assignment": "accepted", "principal_mode_index": 12, "geometry_status": "pass",
        "reviewer": "Codex work-side quantitative and actual three-frame visual review",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        **{key: contract[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")},
        "vfa_handoff": str(RAW / "vfa_handoff.json"), "vfa_handoff_sha256": sha256_file(RAW / "vfa_handoff.json"),
        "source_outcar_sha256": sha256_file(RAW / "OUTCAR"), "frequency_poscar_sha256": sha256_file(RAW / "POSCAR"),
        "quantitative_metrics_sha256": sha256_file(OUT / "mode12_metrics.json"),
        "visual_review_sha256": sha256_file(OUT / "mode12_three_frames.png"),
        "notes": "Mode12 is predominantly C45-C46 opening/closing;CO/CH remain intact. Printed mass-weighted eigenvector converted using actual OUTCAR masses;physical common-active-set cosine with Dimer0.934. Three frames are visualizations,not connectivity evidence.",
        "authorization_boundary": "Original Dimer residual review remains allow_frequency_handoff only;no formal TS,barrier,Grade A or registry promotion.",
        "rsi": {"status": rsi["status"], "problem": rsi.get("problem"), "receipt": str(rsi_root / "run_receipt.json"),
            "receipt_sha256": sha256_file(rsi_root / "run_receipt.json"), "model_turns_started": rsi["model_turns_started"],
            "host_tool_executions": rsi["host_tool_executions"], "selected_policy_count": len(selection["selected_policies"]),
            "used_as_scientific_evidence": False},
    }
    write_json_exclusive(OUT / "mode12_review.json", review)
    analysis = analyze_vfa(RAW, contract, OUT / "mode12_review.json", write_output=False)
    if analysis["grade"] != "Ungraded" or analysis["kinetic_eligible"] or analysis["dimer_technical_acceptance"]:
        raise ValueError("The diagnostic-only authorization boundary was not preserved.")
    write_json_exclusive(OUT / "vfa_analysis.diagnostic.json", analysis)
    inventory = load_json_object(OUT / "remote_inventory.json")
    if not all(sha256_file(RAW / item["relative_path"]) == item["sha256"] for item in inventory["files"]):
        raise ValueError("Raw mode-review inputs changed.")
    write_json_exclusive(OUT / "verification.json", {"status": "PASS", "raw_hashes_verified": len(inventory["files"]),
        "mode_assignment": "accepted_target_CC_event", "diagnostic_grade": analysis["grade"], "kinetic_eligible": False,
        "source_geometry_identity": True, "scope_checks_passed": True, "no_new_scientific_job": True,
        "CC_to_CO_derivative_ratio": abs(metrics["derivatives_A_per_unit_norm_physical_vector"]["CC"] / metrics["derivatives_A_per_unit_norm_physical_vector"]["CO"])})
    print({key: analysis[key] for key in ("status", "grade", "imaginary_frequency_count", "principal_mode_assignment", "dimer_technical_acceptance", "kinetic_eligible")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("collect", "measure", "finalize"))
    {"collect": collect, "measure": measure, "finalize": finalize}[parser.parse_args().phase]()
