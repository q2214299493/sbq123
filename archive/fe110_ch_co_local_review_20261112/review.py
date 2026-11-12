"""Bounded local review of completed NEB9994246; never submits calculations."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import tarfile
from dataclasses import replace
import math
import re
import sys

import numpy as np
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.scheduler_evidence import query_lsf_job
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.utils_structure import read_poscar, write_poscar
from scripts.neb_agent.path_quality_service import PathQualityRequest, build_path_quality_report
from scripts.ts_strategy_engine.contract import load_contract, normalize_contract
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.execution_gate import require_action, validate_decision

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
INITIAL = PARENT / "vasp_ordinary_neb_20261110_v1"
OUT = PARENT / "local_triplet_review_20261112_v1"
RAW = OUT / "raw"
WORK = OUT / "path"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/ts/ch_co_to_chco_20261110/vasp_ordinary_neb_20261110_v1"


def collect():
    if OUT.exists():
        raise ValueError("Review already exists; inspect its receipts instead of recollecting.")
    OUT.mkdir()
    evidence = query_lsf_job("9994246", stage="ordinary_neb")
    write_json_exclusive(OUT / "scheduler_evidence.json", evidence)
    if evidence["status"] != "DONE":
        raise ValueError("Completed-source review requires native DONE.")
    names = ["INCAR", "KPOINTS", "script.lsf"]
    names += [f"{i:02d}/POSCAR" for i in range(8)]
    names += [f"{i:02d}/{name}" for i in range(1, 7) for name in ("CONTCAR", "OUTCAR", "OSZICAR", "XDATCAR")]
    inventory_program = "ROOT=" + repr(REMOTE) + "\nNAMES=" + repr(names) + "\n" + r'''
from pathlib import Path
import os,hashlib,json
root=Path(os.path.expanduser(ROOT)).resolve()
files=[]
for name in NAMES:
 p=root/name
 if os.path.commonpath([str(p.resolve()),str(root)])!=str(root) or p.is_symlink():raise ValueError('Source outside the exact calculation')
 digest=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):digest.update(chunk)
 files.append({'relative_path':name,'bytes':p.stat().st_size,'sha256':digest.hexdigest()})
print(json.dumps({'root':str(root),'files':files}))
'''
    inventory = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, "python3 -"],
        input=inventory_program.encode(), capture_output=True, timeout=90)
    if inventory.returncode:
        raise ValueError("Inventory failed: " + inventory.stderr.decode(errors="replace")[:1000])
    with (OUT / "remote_inventory.json").open("xb") as target:
        target.write(inventory.stdout)
    manifest = load_json_object(OUT / "remote_inventory.json")
    total = sum(row["bytes"] for row in manifest["files"])
    if shutil.disk_usage(OUT).free < total * 3:
        raise ValueError("Insufficient space for preserved raw source and independent analysis copy.")
    archive = OUT / "remote_source.tar.gz"
    archive_program = "ROOT=" + repr(manifest["root"]) + "\nNAMES=" + repr(names) + "\n" + r'''
import sys,tarfile
from pathlib import Path
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',compresslevel=1) as target:
 for name in NAMES:target.add(Path(ROOT)/name,arcname=name,recursive=False)
'''
    with archive.open("xb") as target:
        process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, "python3 -"],
            stdin=subprocess.PIPE, stdout=target, stderr=subprocess.PIPE)
        try:
            _, error = process.communicate(archive_program.encode(), timeout=150)
        except BaseException:
            process.kill()
            process.communicate()
            raise
    if process.returncode:
        raise ValueError("Source transfer failed: " + error.decode(errors="replace")[:1000])
    expected, seen = extract_verified_archive(archive, manifest, names, RAW)
    preflight = load_json_object(INITIAL / "submission_preflight.json")
    for name, digest in preflight["files"].items():
        if name in expected and expected[name]["sha256"] != digest:
            raise ValueError("Submitted input changed: " + name)
    shutil.copytree(RAW, WORK)
    for name in ("reaction_contract.normalized.json", "path_generation_report.json"):
        shutil.copyfile(INITIAL / name, WORK / name)
    endpoint_check = load_json_object(PARENT / "review_ready_v2/registered_endpoint_check.json")
    endpoint_sources = []
    with open_registry(ROOT / "data/project_registry.sqlite3") as db:
        db.execute("PRAGMA query_only=ON")
        for role, image in (("initial", "00"), ("final", "07")):
            endpoint = endpoint_check["endpoints"][role]
            row = db.execute("SELECT * FROM files WHERE file_id=?", (endpoint["source_file_id"],)).fetchone()
            if row is None or not row["local_path"]:
                raise ValueError("Accepted endpoint source not available locally.")
            source = Path(row["local_path"])
            if sha256_file(source) != endpoint["source_sha256"]:
                raise ValueError("Accepted endpoint source changed.")
            shutil.copyfile(source, WORK / image / "OUTCAR")
            endpoint_sources.append({"role": role, "image": image, "path": str(source),
                "sha256": endpoint["source_sha256"], "energy_eV": endpoint["numeric_value"],
                "note": "Accepted scalar endpoint energy;FS structure uses previously reviewed whole-slab symmetry mapping."})
    write_json_exclusive(OUT / "collection_receipt.json", {"status": "PASS", "job_id": "9994246",
        "checked_at": datetime.now(timezone.utc).isoformat(), "files_verified": len(seen), "source_bytes": total,
        "remote_inventory_sha256": sha256_file(OUT / "remote_inventory.json"),
        "source_archive_sha256": sha256_file(archive), "endpoint_sources": endpoint_sources,
        "remote_writes_or_submissions": False})
    print("COLLECTED", len(seen), "files", round(total / 1048576, 2), "MiB;accepted endpoint sources checked", flush=True)


def extract_verified_archive(archive, manifest, names, destination):
    """Extract only manifest-listed regular files, preserving and checking source bytes."""
    expected = {row["relative_path"]: row for row in manifest["files"]}
    seen = set()
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("Unexpected archive member.")
            path = destination / member.name
            if not path.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Archive target outside raw-source directory.")
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with source.extractfile(member) as incoming, path.open("xb") as target:
                for chunk in iter(lambda: incoming.read(1048576), b""):
                    target.write(chunk)
                    digest.update(chunk)
            row = expected[member.name]
            if digest.hexdigest() != row["sha256"] or path.stat().st_size != row["bytes"]:
                raise ValueError("Transferred source differs: " + member.name)
            seen.add(member.name)
    if seen != set(names):
        raise ValueError("Incomplete source snapshot.")
    return expected, seen


def analyze_local():
    if (OUT / "local_geometry_review.json").exists() or (OUT / "periodic_normalization.json").exists():
        raise ValueError("Analysis already exists; inspect saved results before resuming.")
    receipt = load_json_object(OUT / "collection_receipt.json")
    if receipt["status"] != "PASS":
        raise ValueError("Source collection was not verified.")
    inventory = load_json_object(OUT / "remote_inventory.json")
    for row in inventory["files"]:
        if sha256_file(RAW / row["relative_path"]) != row["sha256"]:
            raise ValueError("Preserved raw source changed.")
    previous = None
    normalization = []
    for i in range(8):
        name = "CONTCAR" if 0 < i < 7 else "POSCAR"
        source = RAW / f"{i:02d}" / name
        old = read_poscar(source)
        shifts = np.zeros_like(old.frac)
        if previous is not None:
            shifts[:, :2] = np.rint(previous[:, :2] - old.frac[:, :2])
        frac = old.frac + shifts
        if not np.allclose(frac - old.frac, shifts, atol=1e-14, rtol=0):
            raise ValueError("Periodic operation was not an integer lattice translation.")
        if np.any(shifts):
            write_poscar(WORK / f"{i:02d}" / name, replace(old, frac=frac))
        normalization.append({"image": f"{i:02d}", "source_path": str(source), "source_sha256": sha256_file(source),
            "review_path": str(WORK / f"{i:02d}" / name), "review_sha256": sha256_file(WORK / f"{i:02d}" / name),
            "integer_fractional_shifts": shifts.astype(int).tolist()})
        previous = frac
    write_json_exclusive(OUT / "periodic_normalization.json", {"method": "Sequential nearest-image integer XY lattice translations only",
        "raw_sources_preserved": True, "atom_map_cell_fixed_mask_unchanged": True, "images": normalization})
    atoms = [read(WORK / f"{i:02d}" / ("CONTCAR" if 0 < i < 7 else "POSCAR"), format="vasp") for i in range(8)]
    primary = [float(a.get_distance(45, 46, mic=True)) for a in atoms]
    original = load_contract(INITIAL / "reaction_contract.normalized.json")
    raw_contract = {key: value for key, value in original.items()
        if key not in ("atom_map_sha256", "compatibility_sha256", "contract_sha256")}
    interval = [math.floor(min(primary[4:7]) * 100) / 100, math.ceil(max(primary[4:7]) * 100) / 100]
    raw_contract["reaction_coordinates"] = [{"name": "C45_C46_formation", "kind": "distance", "atoms": [45, 46],
        "important_interval_A": interval, "role": "primary"}]
    contract = normalize_contract(raw_contract)
    if contract["atom_map_sha256"] != original["atom_map_sha256"] or contract["compatibility_sha256"] != original["compatibility_sha256"]:
        raise ValueError("Review annotation altered atom map or physical compatibility.")
    write_json_exclusive(OUT / "reaction_contract.reviewed.json", contract)
    write_json_exclusive(OUT / "reaction_coordinate_annotation.json", {"original_contract_sha256": original["contract_sha256"],
        "reviewed_contract_sha256": contract["contract_sha256"], "reason": "Original contract declares C45-C46 formation but has no primary distance coordinate",
        "interval_basis": "Observed04-05-06 C-C span rounded outward to0.01A;review diagnostic only,not a universal physical threshold",
        "important_interval_A": interval, "no_DFT_parameter_change": True})
    generation = load_json_object(WORK / "path_generation_report.json")
    shutil.copyfile(WORK / "path_generation_report.json", WORK / "initial_path_generation_report.json")
    generation.update(method="Review-only integer-lattice representation of completed VASP NEB;no physical path interpolation",
        contract_sha256=contract["contract_sha256"], atom_map_sha256=contract["atom_map_sha256"],
        compatibility_sha256=contract["compatibility_sha256"], fingerprint_id=build_fingerprint(contract)["fingerprint_id"],
        parent_seed_generation_sha256=sha256_file(WORK / "initial_path_generation_report.json"),
        completed_source_inventory_sha256=sha256_file(OUT / "remote_inventory.json"),
        periodic_normalization_sha256=sha256_file(OUT / "periodic_normalization.json"))
    # Only this new review copy is replaced; its exact initial report remains preserved.
    from scripts.artifact_io import write_json
    write_json(WORK / "path_generation_report.json", generation)
    thresholds = ROOT / "configs/neb_agent/default_thresholds.yaml"
    geometry = diagnose(WORK, ["45", "46", "47", "48"], [], thresholds, reaction_pairs=[[45, 46]], expected_interior=6)
    analysis = analyze(WORK, thresholds, contract["reaction_atoms"])
    binding = validate_path_binding(WORK, contract)
    analysis.update(contract_sha256=contract["contract_sha256"], atom_map_sha256=contract["atom_map_sha256"],
        compatibility_sha256=contract["compatibility_sha256"], path_binding=binding, path_binding_valid=binding["valid"],
        path_reviewed=False, geometry_validated=geometry["status"] == "PASS", transition_state_validated=False)
    write_json(WORK / "neb_analysis.json", analysis)
    quality = build_path_quality_report(PathQualityRequest(WORK, (45, 46), tuple(interval),
        ROOT / "configs/neb_path_quality_control_v2.yaml", thresholds, monitor={}, configured_nelm=200))
    write_json_exclusive(WORK / "neb_path_quality.json", quality)
    triad = evaluate_candidate_triad(WORK / "04/CONTCAR", WORK / "05/CONTCAR", WORK / "06/CONTCAR",
        analysis, contract["reaction_atoms"], analysis_root=WORK)
    write_json_exclusive(OUT / "candidate_triad_gate.json", triad)
    rows = []
    for i in (4, 5, 6):
        a = atoms[i]
        nearest = {}
        for atom in (45, 46, 47, 48):
            distances = a.get_distances(atom, list(range(45)), mic=True)
            nearest[str(atom)] = [{"Fe_index_zero_based": int(j), "distance_A": float(distances[j])}
                for j in np.argsort(distances)[:3]]
        rows.append({"image": f"{i:02d}", "C_C_A": primary[i], "C_O_A": float(a.get_distance(46, 47, mic=True)),
            "C_H_A": float(a.get_distance(45, 48, mic=True)), "nearest_Fe": nearest})
    positions = [read_poscar(WORK / f"{i:02d}/CONTCAR") for i in (4, 5, 6)]
    left = (positions[1].frac - positions[0].frac) @ positions[1].cell
    right = (positions[2].frac - positions[1].frac) @ positions[1].cell
    left[:18] = 0
    right[:18] = 0
    tangent = left + right
    tangent_fraction = float(np.sum(tangent[45:] ** 2) / np.sum(tangent ** 2))
    angle = float(np.degrees(np.arccos(np.clip(np.sum(left * right) / np.linalg.norm(left) / np.linalg.norm(right), -1, 1))))
    write_json_exclusive(OUT / "local_geometry_review.json", {"rows": rows, "geometry_status": geometry["status"],
        "geometry_errors": geometry["errors"], "triad_hard_gate_passed": triad["hard_gate_passed"],
        "central_tangent_reaction_atom_squared_fraction": tangent_fraction, "left_right_step_angle_degrees": angle,
        "tangent_scope": "Displacement diagnostic only;no MODECAR or Dimer handoff prepared", "no_submission": True})
    render_triad(atoms, rows)
    print("ANALYZED", geometry["status"], quality["PATH_QUALITY_STATUS"], "triad_hard", triad["hard_gate_passed"],
        "global_technical", analysis["technically_converged"], "interval", interval, flush=True)


def render_triad(atoms, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(10, 7))
    points = np.concatenate([atoms[i].positions[45:] for i in (4, 5, 6)])
    colors = ["#202c39", "#202c39", "#dc2626", "#38bdf8"]
    for col, (i, row) in enumerate(zip((4, 5, 6), rows, strict=True)):
        cart = atoms[i].positions
        surface = np.argsort(cart[:45, 2])[-9:]
        for r, dims in enumerate(((0, 1), (0, 2))):
            ax = axes[r, col]
            ax.scatter(cart[surface, dims[0]], cart[surface, dims[1]], s=100, c="#a1a1aa")
            for atom, color in zip(range(45, 49), colors, strict=True):
                ax.scatter(cart[atom, dims[0]], cart[atom, dims[1]], s=70, c=color, zorder=3)
                ax.annotate(str(atom), cart[atom, list(dims)], xytext=(4, 4), textcoords="offset points", fontsize=8)
            for pair in ([45, 48], [46, 47], [45, 46]):
                ax.plot(cart[pair, dims[0]], cart[pair, dims[1]], c="#64748b", lw=1)
            ax.set_xlim(points[:, dims[0]].min() - 1.7, points[:, dims[0]].max() + 1.7)
            ax.set_ylim(points[:, dims[1]].min() - 1.7, points[:, dims[1]].max() + 1.7)
            ax.set_aspect("equal")
        axes[0, col].set_title(row["image"] + " C-C=" + format(row["C_C_A"], ".3f") + " A")
    fig.suptitle("Completed NEB9994246 local triad:review only,not a validated TS")
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(OUT / "triad_review.png", dpi=160)
    plt.close(fig)


def finalize_review():
    if (OUT / "execution_decision.json").exists():
        raise ValueError("Current decision already exists; do not silently replace its binding.")
    review = load_json_object(OUT / "local_geometry_review.json")
    if review["geometry_status"] != "PASS":
        raise ValueError("Review geometry did not pass.")
    distances = []
    for i in range(7):
        left = WORK / f"{i:02d}" / ("CONTCAR" if i else "POSCAR")
        right = WORK / f"{i+1:02d}" / ("CONTCAR" if i+1 < 7 else "POSCAR")
        result = subprocess.run(["C:/Program Files/Git/usr/bin/perl.exe",
            (ROOT / "archive/vtst_review_job9745217/dist.pl").as_posix(), left.as_posix(), right.as_posix()],
            capture_output=True, text=True, check=True, timeout=10)
        distances.append({"left": f"{i:02d}", "right": f"{i+1:02d}", "distance_A": float(result.stdout.strip())})
    write_json_exclusive(WORK / "dist_final.json", {"tool_sha256": sha256_file(ROOT / "archive/vtst_review_job9745217/dist.pl"),
        "pairs": distances, "source": "Completed CONTCARs;fixed endpoint POSCARs"})
    movie = subprocess.run(["C:/Program Files/Git/bin/bash.exe", "--noprofile", "--norc", "-c",
        "export PATH=/usr/bin:/bin:$PATH; /usr/bin/perl /c/Users/86177/Desktop/work/archive/vtst_review_job9745217/nebmovie.pl 1"],
        cwd=WORK, capture_output=True, text=True, timeout=60)
    write_json_exclusive(OUT / "completed_movie_command.json", {"exit_code": movie.returncode,
        "stdout": movie.stdout, "stderr": movie.stderr, "mode": 1})
    if movie.returncode or not (WORK / "movie").is_file():
        raise ValueError("Completed VTST movie failed.")
    energy_rows = []
    force_correspondence = []
    for i in range(8):
        path = WORK / f"{i:02d}/OUTCAR"
        with path.open("rb") as source:
            source.seek(0, 2)
            source.seek(max(0, source.tell() - 262144))
            tail = source.read().decode("utf-8", errors="replace")
        values = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)", tail)
        if not values:
            raise ValueError("Final TOTEN missing.")
        energy_rows.append({"image": f"{i:02d}", "final_OUTCAR_TOTEN_eV": float(values[-1])})
        if 0 < i < 7:
            lines = tail.splitlines()
            start = max(j for j, line in enumerate(lines) if "POSITION" in line and "TOTAL-FORCE" in line)
            block = np.array([[float(x) for x in line.split()[:6]] for line in lines[start+2:start+51]])
            if block.shape != (49, 6) or not np.isfinite(block).all():
                raise ValueError("Incomplete final all-atom force block.")
            structure = read_poscar(WORK / f"{i:02d}/CONTCAR")
            delta = structure.frac - block[:, :3] @ np.linalg.inv(structure.cell)
            delta[:, :2] -= np.rint(delta[:, :2])
            error = float(np.max(np.linalg.norm(delta @ structure.cell, axis=1)))
            if error > 1e-5:
                raise ValueError("Force-coordinate correspondence failed.")
            force_correspondence.append({"image": f"{i:02d}", "max_MIC_position_error_A": error, "all_atom_force_values_finite": True})
    peak = energy_rows[5]["final_OUTCAR_TOTEN_eV"]
    for row in energy_rows:
        row["energy_relative_to_image05_eV"] = row["final_OUTCAR_TOTEN_eV"] - peak
    write_json_exclusive(OUT / "local_energy_force_review.json", {"energy_convention": "final_OUTCAR_TOTEN_SIGMA0.20",
        "energy_rows": energy_rows, "force_coordinate_checks": force_correspondence,
        "note": "Owning NEB analyzer separately uses its historical sigma0 profile for stage diagnostics;no final TS/barrier is reported."})
    chemical_review = {"status": "accepted", "reviewer": "Codex work-side chemical and visual review explicitly requested by user",
        "reviewed_at": datetime.now(timezone.utc).isoformat(), "dist_file": str(WORK / "dist_final.json"),
        "dist_sha256": sha256_file(WORK / "dist_final.json"), "nebmovie_file": str(WORK / "movie"),
        "nebmovie_sha256": sha256_file(WORK / "movie"), "path_generation_sha256": sha256_file(WORK / "path_generation_report.json"),
        "review_scope": "Visual chemistry,identity,periodic equivalence and geometric continuity;resolution evidence remains a separate gate",
        "notes": "04-05-06 plot actually viewed;CH and CO retained,CC forms;no collision/fixed-layer drift/chemical switching. Persistent04-05 CC sampling gap retained,not waived.",
        "no_execution_authorization": True}
    write_json_exclusive(WORK / "path_review.json", chemical_review)
    analysis = load_json_object(WORK / "neb_analysis.json")
    analysis.update(path_reviewed=True, path_review=chemical_review,
        path_review_source=str(WORK / "path_review.json"), scientifically_valid=False, transition_state_validated=False)
    from scripts.artifact_io import write_json
    write_json(WORK / "neb_analysis.json", analysis)
    request = {"geometry_file": str(WORK / "path_geometry_diagnosis.json"), "analysis_file": str(WORK / "neb_analysis.json"),
        "thresholds_file": str(ROOT / "configs/neb_agent/default_thresholds.yaml"), "climb": False, "path_reviewed": True,
        "path_quality_file": str(WORK / "neb_path_quality.json"),
        "scheduler_file": str(OUT / "ordinary_neb_scheduler_evidence.json")}
    write_json_exclusive(OUT / "execution_gate_request.json", request)
    decision = build_decision(OUT / "execution_gate_request.json", OUT / "execution_decision.json")
    print("REVIEW_GATE", decision["DECISION"], decision["ALLOWED_ACTIONS"], decision["REASON_CODES"], flush=True)


def rsi_review():
    if (OUT / "rsi_invocation.json").exists():
        raise ValueError("This request already invoked RSI;no retry or duplicate model run.")
    profile = ROOT.parent / "fe110_rsi_experiments/rsi_runtime_policy_20261030/daily_profile.json"
    settings = load_json_object(profile)
    run = Path(settings["output_root"]) / "20261112_chco_local_triad_review_v1"
    if run.exists():
        raise ValueError("RSI output exists;inspect its receipt and resume only if appropriate.")
    entry = ROOT.parent / "fe110_rsi_experiments/rsi_usage_dashboard_20261030/use_research.py"
    argv = [sys.executable, "-X", "utf8", str(entry), "run", "--goal", "审核 **04–05–06** 局部路径，再决定精修方式",
        "--intent", "compare", "--workdir", str(INITIAL), "--scope", str(OUT), "--output-dir", str(run),
        "--max-turns", "3", "--max-actions", "10", "--timeout-seconds", "360"]
    write_json_exclusive(OUT / "rsi_invocation.json", {"argv": argv, "run_directory": str(run),
        "scope": "Review/compare only,no scientific submission authority", "automatic_retry": False})
    with (OUT / "rsi_stdout.json").open("xb") as stdout, (OUT / "rsi_stderr.txt").open("xb") as stderr:
        process = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=420)
    write_json_exclusive(OUT / "rsi_process_exit.json", {"exit_code": process.returncode, "run_directory": str(run),
        "scientific_jobs_submitted": 0})
    receipt = run / "run_receipt.json"
    if receipt.is_file():
        result = load_json_object(receipt)
        print("RSI_RESULT", result["status"], result.get("first_failure_stage"), result.get("problem"), flush=True)
    else:
        print("RSI_NO_RECEIPT", process.returncode, flush=True)


def verify():
    inventory = load_json_object(OUT / "remote_inventory.json")
    for row in inventory["files"]:
        if sha256_file(RAW / row["relative_path"]) != row["sha256"]:
            raise ValueError("Original collected evidence changed.")
    normalization = load_json_object(OUT / "periodic_normalization.json")
    error = 0.0
    for row in normalization["images"]:
        old = read_poscar(Path(row["source_path"]))
        current = read_poscar(Path(row["review_path"]))
        shifts = np.array(row["integer_fractional_shifts"])
        if old.symbols != current.symbols or old.counts != current.counts or old.flags != current.flags:
            raise ValueError("Normalization changed atom identities or fixed mask.")
        error = max(error, float(np.max(np.abs((current.frac - old.frac) - shifts))))
    if error > 1e-10:
        raise ValueError("Periodic equivalence failed.")
    original = load_contract(INITIAL / "reaction_contract.normalized.json")
    current = load_contract(OUT / "reaction_contract.reviewed.json")
    if any(original[name] != current[name] for name in ("atom_map_sha256", "compatibility_sha256")):
        raise ValueError("Physical branch changed.")
    if not validate_path_review(WORK / "path_review.json", WORK / "path_generation_report.json")[0]:
        raise ValueError("Actual review/tool/source binding failed.")
    triad = load_json_object(OUT / "candidate_triad_gate.json")
    if not triad["hard_gate_passed"]:
        raise ValueError("Expected local hard checks did not pass.")
    path = OUT / "execution_decision.json"
    decision = load_json_object(path)
    validate_decision(decision)
    require_action(path, "REBUILD_PATH", decision["state_sha256"])
    for forbidden in ("START_DIMER", "ENABLE_CI_NEB", "SUBMIT_VASP"):
        try:
            require_action(path, forbidden, decision["state_sha256"])
        except PermissionError:
            pass
        else:
            raise ValueError("Forbidden execution action was admitted.")
    force = load_json_object(OUT / "local_energy_force_review.json")
    maximum = max(row["max_MIC_position_error_A"] for row in force["force_coordinate_checks"])
    if maximum > 1e-5:
        raise ValueError("Force/structure correspondence failed.")
    write_json_exclusive(OUT / "verification.json", {"status": "PASS", "source_files_hash_checked": len(inventory["files"]),
        "periodic_translation_residual_fractional_max": error, "force_position_residual_A_max": maximum,
        "triad_hard_checks_pass": True, "current_gate_revalidated": True,
        "allowed_actions": decision["ALLOWED_ACTIONS"], "negative_action_checks": ["START_DIMER", "ENABLE_CI_NEB", "SUBMIT_VASP"],
        "new_scientific_jobs": 0, "accepted_TS_or_barrier": False})
    print("VERIFIED_SOURCE_PERIODICITY_REVIEW_AND_GATE;three forbidden execution actions rejected", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("collect", "analyze", "finalize", "rsi", "verify"))
    {"collect": collect, "analyze": analyze_local, "finalize": finalize_review, "rsi": rsi_review,
     "verify": verify}[parser.parse_args().phase]()
