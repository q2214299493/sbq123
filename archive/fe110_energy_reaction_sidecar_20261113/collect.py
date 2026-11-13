"""Index existing evidence for a read-only sidecar; never register or submit."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "energy_reaction_sidecar_20261113_v1"
PACKAGE = BASE / "combined_force_package_20261113_v1"


def raw_index():
    index = {}
    sources = []

    def add(digest, paths, evidence, potcar=None):
        if not digest or not paths.get("OUTCAR"):
            return
        value = {"paths": {k: str(v) for k, v in paths.items()}, "evidence": str(evidence),
                 "POTCAR_sha256": potcar}
        if value not in index.setdefault(digest, []):
            index[digest].append(value)

    listing = subprocess.run(["rg", "--files", str(BASE), "-g", "collection.json"],
                             capture_output=True, text=True, check=True)
    for name in listing.stdout.splitlines():
        path = Path(name)
        data = load_json_object(path)
        remote = data.get("remote", {}).get("files", {})
        if not remote.get("OUTCAR", {}).get("sha256"):
            continue
        paths = {n: path.parent / n for n in ("OUTCAR", "INCAR", "KPOINTS", "POSCAR", "OSZICAR") if (path.parent / n).is_file()}
        add(remote["OUTCAR"]["sha256"], paths, path, data.get("submission", {}).get("potcar_sha256"))
        sources.append(path)
    for name in ("registry_ts_snapshot.json", "registry_dependency_snapshot.json"):
        snapshot = OUT / name
        data = load_json_object(snapshot)
        groups = {}
        for row in data["files"]:
            if row["filename"] in ("OUTCAR", "INCAR", "KPOINTS", "POSCAR", "CONTCAR", "OSZICAR") and row["local_path"]:
                groups.setdefault(row["calculation_id"], []).append(row)
        for rows in groups.values():
            paths = {r["filename"]: Path(r["local_path"]) for r in rows}
            for row in rows:
                if row["filename"] == "OUTCAR":
                    add(row["sha256"], {**paths, "OUTCAR": Path(row["local_path"])}, snapshot)
        sources.append(snapshot)
    physical = BASE / "independent_nearstable_inventory_20261113_v1/physical_inventory.json"
    for row in load_json_object(physical)["source_summaries"]:
        files = {Path(f["path"]).name: Path(f["path"]) for f in row["source_files"]}
        force_source = next(f for f in row["source_files"] if Path(f["path"]).name == "OUTCAR")
        add(force_source["sha256"], files, physical)
    c3 = PACKAGE / "provenance/c3_candidates/source"
    add(sha256_file(c3 / "OUTCAR"), {n: c3 / n for n in ("OUTCAR", "INCAR", "KPOINTS", "POSCAR", "OSZICAR") if (c3 / n).is_file()}, c3 / "OUTCAR")
    sources.append(physical)
    write_json_exclusive(OUT / "raw_source_index.json", {
        "read_only": True, "entries": index, "outcar_hash_count": len(index),
        "note": "Index pointers are not label acceptance; audit verifies actual bytes.",
        "source_files": source_file_manifest(sources)})
    print(json.dumps({"indexed_OUTCAR_hashes": len(index), "collection_metadata": len(listing.stdout.splitlines())}))


if __name__ == "__main__":
    raw_index()
