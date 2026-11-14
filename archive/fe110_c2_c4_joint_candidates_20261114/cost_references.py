"""Read native timing of already completed compatible CPU statics only."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.vasp_result_gate import read_incar_values
from .collect_sources import BASE, OUT


def timing(path):
    if path.stat().st_size > 250 * 1024**2:
        return None
    with path.open("rb") as handle:
        header = handle.read(16384)
        handle.seek(max(0, path.stat().st_size - 20000))
        tail = handle.read()
    cores = re.search(rb"running on\s+(\d+)\s+(?:total\s+)?cores", header)
    elapsed = re.search(rb"Elapsed time \(sec\):\s*([0-9.]+)", tail)
    if not cores or not elapsed:
        return None
    return {"MPI_ranks_observed": int(cores[1]), "VASP_elapsed_seconds": float(elapsed[1]),
            "allocated_core_hour_estimate": int(cores[1]) * float(elapsed[1]) / 3600,
            "cost_scope": "MPI ranks times VASP-native elapsed;not scheduler-billed corehours"}


def run():
    side = BASE / "energy_reaction_sidecar_20261113_v1"
    labels_path = side / "energy_label_sidecar_final_v2.json"
    index_path = side / "raw_source_index.json"
    labels = load_json_object(labels_path)["records"]
    index = load_json_object(index_path)["entries"]
    counts = Counter()
    seen = set()
    records, errors = [], []
    bound = {Path(__file__), labels_path, index_path}
    for label in labels:
        comp = label["composition"]
        digest = label["source_OUTCAR_sha256"]
        if comp not in {"C2HO", "C2H2O", "C2H3", "C3H2O"} or not label.get("energy_force_evidence_ready_for_review") or digest in seen or counts[comp] >= 6:
            continue
        for entry in index.get(digest, []):
            p = Path(entry["paths"]["OUTCAR"])
            incar = Path(entry["paths"].get("INCAR", p.parent / "INCAR"))
            if not p.is_file() or not incar.is_file():
                continue
            settings = read_incar_values(incar)
            if float(settings.get("NSW", -999)) != 0 or float(settings.get("IBRION", 0)) != -1:
                continue
            native = timing(p)
            if native is None or native["MPI_ranks_observed"] != 32:
                continue
            if sha256_file(p) != digest:
                errors.append({"path": str(p), "error": "raw_source_hash_changed"})
                continue
            records.append({"sample_id": label["sample_id"], "composition": comp, "source_job_id": label["source_job_id"],
                            "OUTCAR_path": str(p), "OUTCAR_sha256": digest, "INCAR_path": str(incar),
                            "static_NSW": settings["NSW"], "IBRION": settings["IBRION"],
                            "existing_compatibility": label["compatibility"], **native})
            counts[comp] += 1
            seen.add(digest)
            bound.update([p, incar])
            break
    stats = {}
    for comp in sorted(counts):
        values = [r["VASP_elapsed_seconds"] for r in records if r["composition"] == comp]
        stats[comp] = {"n_reference_statics": len(values), "median_seconds": float(np.median(values)),
                       "p90_seconds": float(np.quantile(values, .9)), "maximum_seconds": max(values),
                       "ranks": 32, "small_empirical_sample_not_runtime_guarantee": True}
    write_json_exclusive(OUT / "static_cost_references.json", {"records": records, "statistics": stats, "errors": errors,
                         "new_compute_or_scheduler_queries": False, "source_files": source_file_manifest(sorted(bound))})
    print({"reference_count": len(records), "statistics": stats, "errors": errors}, flush=True)


if __name__ == "__main__":
    run()
