"""Bounded, read-only registry and existing-geometry inventory; no calculators."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import subprocess

from scripts.artifact_io import sha256_file, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "c2_c4_gap_inventory_20261114_v1"
CARE = Path("C:/Users/86177/Desktop/sbqCode/care_barrier_fitting/data/processed")
TABLES = ("calculations", "jobs", "files", "results", "calculation_compatibility",
          "reviews", "ts_barriers", "ts_validations")
HEADER_LIMIT = 16 * 1024
GEOMETRY_LIMIT = 2 * 1024**2


def vasp5_header(data: bytes) -> dict:
    """Read species/counts only; never interpret the title as a composition."""
    lines = data.decode("utf-8-sig", errors="replace").splitlines()
    if len(lines) < 8:
        return {"status": "INVALID_OR_INCOMPLETE_HEADER"}
    species = lines[5].split()
    if not species or not all(re.fullmatch(r"[A-Z][a-z]?", s) for s in species):
        return {"status": "VASP4_OR_UNSUPPORTED_SPECIES_NEEDS_CONFIRMATION"}
    try:
        counts = [int(s) for s in lines[6].split()]
    except ValueError:
        return {"status": "INVALID_COUNTS"}
    if len(counts) != len(species) or min(counts) < 0 or sum(counts) <= 0:
        return {"status": "INVALID_COUNTS"}
    totals = Counter()
    for symbol, count in zip(species, counts, strict=True):
        totals[symbol] += count
    return {"status": "VASP5_HEADER_ONLY", "species": species, "counts": counts,
            "composition_counts": dict(totals), "natoms": sum(counts),
            "total_C": totals["C"], "Fe_count": totals["Fe"]}


def registry_snapshot() -> dict:
    database = ROOT / "data/project_registry.sqlite3"
    before = sha256_file(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        connection.execute("BEGIN")
        snapshot = {name: [dict(r) for r in connection.execute("SELECT * FROM " + name)]
                    for name in TABLES}
        connection.rollback()
    finally:
        connection.close()
    after = sha256_file(database)
    if before != after:
        raise ValueError("registry file changed during read-only snapshot")
    return {"read_only": True, "database_path": str(database), "database_sha256": before,
            "created_at": datetime.now(timezone.utc).isoformat(), "tables": snapshot,
            "counts": {name: len(rows) for name, rows in snapshot.items()},
            "source_files": source_file_manifest([Path(__file__)])}


def listed_geometries(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["rg", "--files", "--no-ignore", str(root), "-g", "POSCAR", "-g", "CONTCAR",
         "-g", "*.vasp"], capture_output=True, text=True, encoding="utf-8", check=False)
    if completed.returncode not in (0, 1):
        raise RuntimeError(completed.stderr[:2000])
    paths = [Path(s) for s in completed.stdout.splitlines()]
    if len(paths) > 50000:
        raise ValueError("geometry path scope exceeds 50000; narrow before reading")
    return paths


def header_inventory(snapshot: dict) -> dict:
    registered = {}
    for record in snapshot["tables"]["files"]:
        name = record.get("filename", "")
        if name not in ("POSCAR", "CONTCAR") and not name.lower().endswith(".vasp"):
            continue
        if record.get("local_path"):
            path = Path(record["local_path"])
            if not path.is_absolute():
                path = ROOT / path
            registered.setdefault(str(path.resolve()), []).append({
                key: record.get(key) for key in ("file_id", "calculation_id", "sha256", "remote_path")})
    paths = {str(p.resolve()): p.resolve() for p in listed_geometries(ROOT / "calculations")}
    # The existing CARE export is an internal geometry source, not a DFT label.
    paths.update({str(p.resolve()): p.resolve() for p in listed_geometries(CARE)})
    for path in registered:
        if Path(path).is_file():
            paths.setdefault(path, Path(path))
    rows = []
    for name, path in sorted(paths.items()):
        row = {"path": name, "registered_aliases": registered.get(name, []),
               "scope": "CARE_PROCESSED" if path.is_relative_to(CARE) else "WORK_EXISTING"}
        try:
            before = path.stat()
            row["byte_size"] = before.st_size
            if before.st_size > GEOMETRY_LIMIT:
                row["status"] = "SKIPPED_OVER_2MIB"
            else:
                with path.open("rb") as handle:
                    row.update(vasp5_header(handle.read(HEADER_LIMIT)))
                row["sha256"] = sha256_file(path)
                after = path.stat()
                row["stable_during_read"] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
                row["registered_hash_matches"] = [r["sha256"] == row["sha256"] for r in row["registered_aliases"]
                                                  if r.get("sha256")]
        except (OSError, UnicodeError) as error:
            row["status"] = "READ_ERROR"
            row["error"] = type(error).__name__ + ": " + str(error)
        rows.append(row)
    high = [r for r in rows if 4 <= r.get("total_C", 0) <= 6]
    return {"read_only": True, "roots": [str(ROOT / "calculations"), str(CARE)],
            "not_a_complete_unregistered_remote_server_search": True,
            "path_count": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
            "carbon_frame_alias_counts": dict(Counter(str(r.get("total_C", "unknown")) for r in rows)),
            "C4_C5_C6_alias_count": len(high), "C4_C5_C6_unique_byte_hashes": len({r["sha256"] for r in high}),
            "records": rows,
            "source_files": source_file_manifest([Path(__file__), OUT / "registry_snapshot.json"])}


def run():
    snapshot = registry_snapshot()
    write_json_exclusive(OUT / "registry_snapshot.json", snapshot)
    print({"registry_counts": snapshot["counts"]}, flush=True)
    geometries = header_inventory(snapshot)
    write_json_exclusive(OUT / "local_geometry_headers.json", geometries)
    print({key: geometries[key] for key in ("path_count", "status_counts", "carbon_frame_alias_counts",
                                          "C4_C5_C6_alias_count", "C4_C5_C6_unique_byte_hashes")}, flush=True)


if __name__ == "__main__":
    run()
