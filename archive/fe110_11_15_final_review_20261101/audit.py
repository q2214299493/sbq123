"""Bounded existing-output audit; no job, registry, workbook or acceptance writes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import itertools
from pathlib import Path
import subprocess

import yaml

from archive.fe110_adsorption_acceptance_20261029 import collect as collector
from archive.fe110_adsorption_acceptance_20261029 import review as reviewer
from scripts.adsorption.build_fe110_adsorption import read_poscar, expanded_symbols
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"
UPDATE = BASE / "ft512_gpu_20261029_v1/nsw300_update_20261029_v1"
OUT = BASE / "final_review_20261101_v1"
CLEAN = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"


def initialize():
    if OUT.exists():
        raise FileExistsError(OUT)
    current = load_json_object(UPDATE / "final_status.json")["records"]
    original = {r["name"]: r for r in load_json_object(UPDATE / "scope.json")["jobs"]}
    continuations = {r["name"]: r for r in load_json_object(UPDATE / "continuation_submitted.json")["jobs"]}
    amendments = {r["name"]: r for r in load_json_object(UPDATE / "pending_amendment_receipt.json")["records"]}
    source = BASE / "candidates_v5/candidate_review.json"
    candidates = {r["name"]: r for r in load_json_object(source)["candidates"]}
    if len(current) != 15 or len({r["job_id"] for r in current}) != 15:
        raise ValueError("expected 15 distinct current jobs")
    rows = []
    with open_registry(ROOT / "data/project_registry.sqlite3") as db:
        db.execute("PRAGMA query_only=ON")
        for r in current:
            name = r["name"]
            binding = continuations.get(name, amendments.get(name))
            if binding is None or binding["job_id"] != r["job_id"]:
                raise ValueError("missing amended input/job binding: " + name)
            directory = UPDATE / "inputs300" / name
            for filename, digest in binding["new_files"].items():
                if sha256_file(directory / filename) != digest:
                    raise ValueError("changed submitted local input: " + name + "/" + filename)
            jobs = db.execute("SELECT * FROM jobs WHERE scheduler_job_id=?", (r["job_id"],)).fetchall()
            if len(jobs) != 1 or jobs[0]["remote_directory"] != r["remote_dir"]:
                raise ValueError("registry job/path mismatch: " + name)
            c = candidates[name]
            target = Path(c["source_path"])
            if sha256_file(target) != c["source_sha256"]:
                raise ValueError("target geometry provenance changed: " + name)
            rows.append({"name": name, "job_id": r["job_id"], "remote_dir": r["remote_dir"],
                         "workdir": str(directory), "potcar_sha256": original[name]["potcar_sha256"],
                         "calculation_id": jobs[0]["calculation_id"], "species_id": c["species_id"],
                         "formula": c["formula"], "connectivity": c["connectivity"],
                         "target_path": str(target), "target_sha256": c["source_sha256"],
                         "expected_input_hashes": binding["new_files"]})
    OUT.mkdir()
    write_json_exclusive(OUT / "sources.json", {"records": rows, "request": "开始核验",
        "scope": "Existing 11-15 final outputs, chemistry and conservative duplicate audit only",
        "no_compute": True, "scientific_acceptance": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_metadata": {str(p): sha256_file(p) for p in (source, UPDATE / "final_status.json",
            UPDATE / "scope.json", UPDATE / "continuation_submitted.json", UPDATE / "pending_amendment_receipt.json")}})
    print("INITIALIZED", len(rows), flush=True)


def collect(only):
    collector.OUT = OUT
    rows = load_json_object(OUT / "sources.json")["records"]
    if only:
        rows = [r for r in rows if r["name"] == only]
    if not rows:
        raise ValueError("empty collection selection")
    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(collector.collect_snapshot, r): r for r in rows}
        for job in as_completed(jobs):
            r = jobs[job]
            try:
                result = job.result()
                print("COLLECTED", r["name"], "OUTCAR_bytes", result["remote"]["files"]["OUTCAR"]["byte_size"], flush=True)
            except Exception as exc:
                errors.append({"name": r["name"], "error": str(exc)})
                print("BLOCKED", r["name"], str(exc)[:350], flush=True)
    if errors:
        write_json_exclusive(OUT / ("failures_" + datetime.now(timezone.utc).strftime("%H%M%S") + ".json"), {"errors": errors})
        raise SystemExit(1)


def scheduler():
    rows = load_json_object(OUT / "sources.json")["records"]
    directory = OUT / "scheduler"
    directory.mkdir(exist_ok=False)
    command = "bjobs -a -w " + " ".join(r["job_id"] for r in rows)
    result = subprocess.run(["ssh", *collector.ssh_options(collector.IDENTITY),
        "sunboquan-codex", command], capture_output=True, timeout=45)
    # Preserve exact bytes independently of derived JSON observations.
    for stream in ("stdout", "stderr"):
        with (directory / (stream + ".txt")).open("xb") as handle:
            handle.write(getattr(result, stream))
    states = {}
    for line in result.stdout.decode(errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] in {r["job_id"] for r in rows}:
            states[fields[0]] = fields[2]
    write_json_exclusive(directory / "receipt.json", {"checked_at": datetime.now(timezone.utc).isoformat(),
        "command": command, "returncode": result.returncode, "states": states,
        "stdout_sha256": sha256_file(directory / "stdout.txt"), "stderr_sha256": sha256_file(directory / "stderr.txt"),
        "unobserved_job_ids": [r["job_id"] for r in rows if r["job_id"] not in states],
        "unobserved_is_not_failure": True})
    print("QUEUE_OBSERVED", states, flush=True)


def bond_details(path, rules):
    from ase.io import read
    atoms = read(path, format="vasp")
    atoms.pbc = [True, True, False]
    ids = list(range(45, len(atoms)))
    edges = connectivity_edges(atoms, ids, rules["covalent_radius_scale"], rules["minimum_bond_distance_angstrom"])
    return [{"atoms_zero_based": [ids[a], ids[b]], "elements": [atoms[ids[a]].symbol, atoms[ids[b]].symbol],
             "distance_A": float(atoms.get_distance(ids[a], ids[b], mic=True))} for a, b in sorted(edges)]


def analyze():
    target = OUT / "analysis.json"
    if target.exists():
        raise FileExistsError(target)
    rows = load_json_object(OUT / "sources.json")["records"]
    policy = yaml.safe_load(reviewer.POLICY.read_text())
    slab = read_poscar(CLEAN)
    production = reviewer.production_settings()
    records = []
    for source in rows:
        directory = OUT / "sources" / source["name"]
        cache = directory / "analysis.json"
        if cache.exists():
            row = load_json_object(cache)
            if row["collection_sha256"] != sha256_file(directory / "collection.json"):
                raise ValueError("cached source changed")
        else:
            row = reviewer.analyze_one(directory, slab, policy, production)
            row["requested_signature"] = molecular_signature(read_poscar(Path(source["target_path"])))
            row["requested_graph_preserved"] = row["final_signature"] == row["requested_signature"]
            row["submitted_bonds"] = bond_details(directory / "POSCAR", policy["connectivity"])
            row["final_bonds"] = bond_details(directory / "CONTCAR", policy["connectivity"])
            write_json_exclusive(cache, row)
        records.append(row)
        print(row["name"], "steps", row["ionic_steps"], "fmax", round(row["fmax_eV_A"], 6),
              "fragments", row["measurements"]["fragments"], "target_preserved", row["requested_graph_preserved"],
              "blockers", row["blockers"], flush=True)
    ops = surface_pose_symmetries(slab)
    poses = {r["name"]: read_poscar(Path(r["directory"]) / "CONTCAR") for r in records}
    comparisons = []
    for a, b in itertools.combinations(records, 2):
        if a["formula"] != b["formula"] or a["final_signature"] != b["final_signature"]:
            continue
        if expanded_symbols(poses[a["name"]]) != expanded_symbols(poses[b["name"]]):
            continue
        metrics = surface_equivalence(poses[a["name"]], poses[b["name"]], slab, ops)
        de = abs(a["toten_eV"] - b["toten_eV"])
        duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= policy["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"] and de <= policy["duplicate_detection"]["energy_tolerance_ev"]
        comparisons.append({"first": a["name"], "second": b["name"], **metrics, "energy_difference_eV": de,
            "duplicate": duplicate, "carbon_roles_fixed": True})
    write_json_exclusive(target, {"records": records, "comparisons": comparisons,
        "clean_sha256": sha256_file(CLEAN), "policy_sha256": sha256_file(reviewer.POLICY),
        "production_config_sha256": sha256_file(ROOT / "configs/true_fe110_production.yaml"),
        "adapter_sha256": sha256_file(Path(__file__)), "canonical_analyzer_sha256": sha256_file(Path(reviewer.__file__)),
        "scientific_acceptance": False, "registry_written": False,
        "duplicate_scope": "this batch only; fixed reviewed C roles; true slab symmetries and H permutations"})
    print("ANALYZED", len(records), "duplicate_pairs", sum(r["duplicate"] for r in comparisons), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("initialize", "collect", "scheduler", "analyze"))
    parser.add_argument("--only")
    args = parser.parse_args()
    {"initialize": initialize, "scheduler": scheduler, "analyze": analyze,
     "collect": lambda: collect(args.only)}[args.phase]()
