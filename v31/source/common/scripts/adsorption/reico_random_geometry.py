"""Bounded, deterministic REICO-inspired atom sampling on a verified Fe45 slab.

Only local CPU geometry is produced. No potential, relaxation or scheduler is used.
"""
from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from pathlib import Path

import ase
import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.geometry import get_distances
from ase.io import read, write

from scripts.artifact_io import canonical_json, sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[2]
PARTITIONS = ("train", "development", "final_test")


def immutable_bytes(path: Path, data: bytes) -> None:
    """Resume identical artifacts; refuse modified or incomplete existing bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"existing artifact differs; refusing overwrite: {path}")
        return
    with path.open("xb") as handle:
        handle.write(data)


def immutable_json(path: Path, payload: dict) -> None:
    immutable_bytes(path, (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def pair_key(a: str, b: str) -> str:
    return "-".join(sorted((a, b)))


def fixed_indices(atoms: Atoms) -> list[int]:
    if len(atoms.constraints) != 1 or not isinstance(atoms.constraints[0], FixAtoms):
        raise ValueError("expected one complete FixAtoms constraint")
    return sorted(int(i) for i in atoms.constraints[0].get_indices())


def validate_config(config: dict) -> None:
    if config.get("schema_version") != 1 or config.get("purpose") != "CPU_RANDOM_GEOMETRY_REVIEW_ONLY":
        raise ValueError("unsupported geometry configuration")
    if config.get("element_order") != ["C", "O", "H"]:
        raise ValueError("expected Fe followed by C/O/H order")
    if type(config.get("base_seed")) is not int or config["base_seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    if type(config.get("max_attempts_per_family")) is not int or not 1 <= config["max_attempts_per_family"] <= 20:
        raise ValueError("attempt budget must be 1..20")
    required = {pair_key(a, b) for a in ("Fe", "C", "O", "H") for b in ("C", "O", "H")}
    pairs = config["pair_minimum_A"]
    if set(pairs) != required or any(not np.isfinite(v) or v <= 0 for v in pairs.values()):
        raise ValueError("pair guards must cover exactly all adsorbate/contact element pairs")
    for key in ("lateral_half_width_A", "maximum_nearest_neighbor_A", "maximum_closest_heavy_atom_Fe_A",
                "minimum_periodic_vacuum_gap_A"):
        if not np.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"invalid positive finite value: {key}")
    for symbol in config["element_order"]:
        low, high = config["height_above_top_Fe_A"][symbol]
        if not np.isfinite([low, high]).all() or not 0 < low < high:
            raise ValueError(f"invalid height interval: {symbol}")
    validate_compositions(config["compositions"])


def validate_compositions(compositions: list[dict]) -> None:
    names = set()
    for composition in compositions:
        if composition["name"] in names:
            raise ValueError("duplicate composition name")
        names.add(composition["name"])
        counts = composition["counts"]
        if set(counts) != {"C", "O", "H"} or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError("invalid composition counts")
        if counts["C"] not in (2, 3) or not 3 <= sum(counts.values()) <= 7:
            raise ValueError("outside bounded C2/C3 pilot scope")
        groups = composition["families"]
        if set(groups) != set(PARTITIONS) or any(type(v) is not int or v < 0 for v in groups.values()):
            raise ValueError("invalid family partition")
    total = sum(sum(c["families"].values()) for c in compositions)
    if not 1 <= total <= 100:
        raise ValueError("family budget must be 1..100")


def load_slab(path: Path, expected_sha256: str) -> Atoms:
    if sha256_file(path) != expected_sha256:
        raise ValueError("source slab SHA256 mismatch")
    slab = read(path, format="vasp")
    if slab.get_chemical_symbols() != ["Fe"] * 45 or not slab.pbc.all():
        raise ValueError("expected periodic Fe45 slab")
    if not np.isfinite(slab.positions).all() or not np.isfinite(slab.cell).all() or slab.cell.volume <= 0:
        raise ValueError("invalid slab coordinates or cell")
    if not np.allclose(np.asarray(slab.cell)[:2, 2], 0, atol=1e-10) or not np.allclose(slab.cell[2, :2], 0, atol=1e-10):
        raise ValueError("requires slab normal along Cartesian z")
    if fixed_indices(slab) != list(range(18)) or set(np.argsort(slab.positions[:, 2])[:18]) != set(range(18)):
        raise ValueError("expected bottom 18 Fe fixed in the preserved source order")
    return slab


def family_plan(config: dict) -> list[dict]:
    """Assign entire families before coordinates, labels or predictions exist."""
    queues = []
    for serial, composition in enumerate(config["compositions"]):
        groups = [group for group in PARTITIONS for _ in range(composition["families"][group])]
        rng = np.random.default_rng(np.random.SeedSequence([config["base_seed"], 0, serial]))
        rng.shuffle(groups)
        queues.append([{"composition": composition["name"], "counts": composition["counts"], "partition": g} for g in groups])
    families = []
    for offset in range(max(map(len, queues))):
        for queue in queues:
            if offset < len(queue):
                index = len(families) + 1
                families.append({**queue[offset], "family_id": f"family_{index:04d}", "seed_components": [config["base_seed"], index]})
    return families


def draw_atoms(slab: Atoms, counts: dict, config: dict, rng: np.random.Generator) -> Atoms:
    symbols = [symbol for symbol in config["element_order"] for _ in range(counts[symbol])]
    anchor = rng.uniform(0, 1, 2) @ np.asarray(slab.cell)[:2]
    positions = np.empty((len(symbols), 3))
    positions[:, :2] = anchor[:2] + rng.uniform(-1, 1, (len(symbols), 2)) * config["lateral_half_width_A"]
    top = float(slab.positions[:, 2].max())
    for i, symbol in enumerate(symbols):
        positions[i, 2] = top + rng.uniform(*config["height_above_top_Fe_A"][symbol])
    fractional = positions @ np.linalg.inv(slab.cell)
    fractional[:, :2] %= 1
    adsorbate = Atoms(symbols, positions=fractional @ slab.cell)
    return slab + adsorbate


def audit_geometry(atoms: Atoms, slab: Atoms, config: dict) -> dict:
    if not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell).all():
        return {"reasons": ["NONFINITE_GEOMETRY"]}
    unchanged = (np.allclose(atoms.positions[:45], slab.positions, rtol=0, atol=1e-12)
                 and np.allclose(atoms.cell, slab.cell, rtol=0, atol=1e-12)
                 and np.array_equal(atoms.pbc, slab.pbc) and atoms.get_chemical_symbols()[:45] == ["Fe"] * 45
                 and fixed_indices(atoms) == fixed_indices(slab))
    if not unchanged:
        return {"reasons": ["SLAB_OR_CONSTRAINT_CHANGED"]}
    symbols = atoms.get_chemical_symbols()
    _, distances = get_distances(atoms.positions[45:], atoms.positions, cell=atoms.cell, pbc=atoms.pbc)
    minima, reasons, nearest_fe = {}, [], {}
    for i in range(45, len(atoms)):
        row = distances[i - 45]
        for j in range(i):
            key, distance = pair_key(symbols[i], symbols[j]), float(row[j])
            minima[key] = min(minima.get(key, float("inf")), distance)
            if distance < config["pair_minimum_A"][key]:
                reasons.append(f"SHORT_CONTACT:{key}")
        candidates = row.copy()
        candidates[i] = np.inf
        if candidates.min() >= config["maximum_nearest_neighbor_A"]:
            reasons.append("ISOLATED_ADSORBATE_ATOM")
        nearest_fe[str(i)] = {"element": symbols[i], "Fe_index_zero_based": int(row[:45].argmin()),
                              "distance_A": float(row[:45].min())}
    top = float(slab.positions[:, 2].max())
    heights = atoms.positions[45:, 2] - top
    for symbol, height in zip(symbols[45:], heights, strict=True):
        low, high = config["height_above_top_Fe_A"][symbol]
        if height < low - 1e-10 or height > high + 1e-10:
            reasons.append("HEIGHT_OUTSIDE_SAMPLING_RANGE")
    closest_heavy = min(v["distance_A"] for v in nearest_fe.values() if v["element"] != "H")
    if closest_heavy > config["maximum_closest_heavy_atom_Fe_A"]:
        reasons.append("NO_HEAVY_ATOM_SURFACE_CONTACT")
    z = np.sort(atoms.positions[:, 2] % atoms.cell[2, 2])
    gap = float(np.diff(np.r_[z, z[0] + atoms.cell[2, 2]]).max())
    if gap < config["minimum_periodic_vacuum_gap_A"]:
        reasons.append("PERIODIC_VACUUM_TOO_SMALL")
    return {"reasons": sorted(set(reasons)), "pair_minima_A": minima, "nearest_Fe": nearest_fe,
            "adsorbate_heights_A": heights.tolist(), "periodic_vacuum_gap_A": gap}


def geometry_key(atoms: Atoms) -> str:
    """Only PBC/equal-element exact duplicates; preserve absolute surface height."""
    fractional = atoms.get_scaled_positions(wrap=False).copy()
    fractional[:, :2] %= 1
    fractional = np.round(fractional, 8)
    fractional[:, :2] %= 1
    fractional[fractional == 0] = 0.0
    rows = sorted((s, *p.tolist()) for s, p in zip(atoms.get_chemical_symbols(), fractional, strict=True))
    return sha256_bytes(canonical_json({"cell": np.asarray(atoms.cell).tolist(), "atoms": rows}))


def render_poscar(atoms: Atoms) -> bytes:
    stream = io.StringIO()
    write(stream, atoms, format="vasp", direct=True, sort=False, vasp5=True)
    return stream.getvalue().encode("utf-8")


def generate_family(family: dict, slab: Atoms, config: dict, directory: Path, seen: set[str]) -> dict:
    rng = np.random.default_rng(np.random.SeedSequence(family["seed_components"]))
    attempts, accepted, result = [], None, None
    for attempt in range(1, config["max_attempts_per_family"] + 1):
        atoms = draw_atoms(slab, family["counts"], config, rng)
        audit = audit_geometry(atoms, slab, config)
        key = geometry_key(atoms)
        if key in seen:
            audit["reasons"].append("EXACT_DUPLICATE_IN_THIS_RUN")
        attempts.append({"attempt": attempt, "adsorbate_positions_A": atoms.positions[45:].tolist(), "audit": audit})
        if not audit["reasons"]:
            accepted, result = atoms, {"status": "CPU_GEOMETRY_CANDIDATE", "geometry_key": key, "geometry_audit": audit}
            break
    if accepted is None:
        result = {"status": "ATTEMPT_BUDGET_EXHAUSTED", "geometry_key": None}
    else:
        data = render_poscar(accepted)
        roundtrip = read(io.StringIO(data.decode("utf-8")), format="vasp")
        if audit_geometry(roundtrip, slab, config)["reasons"]:
            raise ValueError("POSCAR roundtrip geometry changed")
        if not np.allclose(roundtrip.positions, accepted.positions, rtol=0, atol=1e-12) or fixed_indices(roundtrip) != list(range(18)):
            raise ValueError("POSCAR roundtrip coordinates or constraints changed")
        immutable_bytes(directory / "POSCAR", data)
        result["poscar_sha256"] = sha256_bytes(data)
    log = b"".join(canonical_json(row) + b"\n" for row in attempts)
    immutable_bytes(directory / "attempts.jsonl", log)
    result.update({**family, "attempts": len(attempts), "attempts_sha256": sha256_bytes(log),
                   "is_relaxed": False, "has_dft_labels": False, "scientifically_accepted": False})
    immutable_json(directory / "family.json", result)
    return result


def run(config_path: Path, output: Path, *, root: Path = ROOT, limit: int | None = None) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config)
    slab_path = root / config["source_slab"]
    slab = load_slab(slab_path, config["source_slab_sha256"])
    families = family_plan(config)
    count = len(families) if limit is None else limit
    if type(count) is not int or not 1 <= count <= len(families):
        raise ValueError("limit must be within the frozen family plan")
    binding = {"config_sha256": sha256_file(config_path), "slab_sha256": sha256_file(slab_path),
               "generator_sha256": sha256_file(Path(__file__)), "ase_version": ase.__version__, "numpy_version": np.__version__}
    immutable_json(output / "plan.json", {"binding": binding, "families": families, "purpose": config["purpose"]})
    immutable_bytes(output / "inputs" / "config.json", config_path.read_bytes())
    immutable_bytes(output / "inputs" / "slab.POSCAR", slab_path.read_bytes())
    seen, results = set(), []
    for family in families[:count]:
        directory = output / "families" / family["family_id"]
        record = directory / "family.json"
        if record.exists():
            result = json.loads(record.read_text(encoding="utf-8"))
            if result.get("status") not in {"CPU_GEOMETRY_CANDIDATE", "ATTEMPT_BUDGET_EXHAUSTED"}:
                raise ValueError(f"unknown family status: {record}")
            if any(result.get(k) != v for k, v in family.items()):
                raise ValueError(f"changed family binding: {record}")
            if sha256_file(directory / "attempts.jsonl") != result["attempts_sha256"]:
                raise ValueError(f"changed attempt log: {directory}")
            if result["status"] == "CPU_GEOMETRY_CANDIDATE":
                if sha256_file(directory / "POSCAR") != result["poscar_sha256"]:
                    raise ValueError(f"changed POSCAR: {directory}")
                if geometry_key(read(directory / "POSCAR", format="vasp")) != result["geometry_key"]:
                    raise ValueError(f"changed geometry key: {directory}")
                if audit_geometry(read(directory / "POSCAR", format="vasp"), slab, config)["reasons"]:
                    raise ValueError(f"invalid saved geometry: {directory}")
        else:
            result = generate_family(family, slab, config, directory, seen)
        if result["geometry_key"] is not None:
            if result["geometry_key"] in seen:
                raise ValueError("duplicate accepted family")
            seen.add(result["geometry_key"])
        results.append(result)
    successful = [r for r in results if r["status"] == "CPU_GEOMETRY_CANDIDATE"]
    summary = {"binding": binding, "requested_families_this_checkpoint": count, "frozen_plan_families": len(families),
               "generated": len(successful), "failed": len(results) - len(successful), "attempts": sum(r["attempts"] for r in results),
               "composition_counts": dict(Counter(r["composition"] for r in successful)),
               "partition_counts": dict(Counter(r["partition"] for r in successful)),
               "gpu_jobs": 0, "dft_jobs": 0, "training_runs": 0, "optimized_frames": 0,
               "final_diversity_selection_done": False, "scientific_acceptance": False,
               "families": [{k: r[k] for k in ("family_id", "composition", "partition", "status", "geometry_key")} for r in results]}
    immutable_json(output / f"summary_{count:04d}.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Stop after this prefix of the frozen family plan; identical reruns resume.")
    args = parser.parse_args()
    summary = run(args.config, args.output, limit=args.limit)
    print(json.dumps({k: summary[k] for k in ("generated", "failed", "attempts", "gpu_jobs", "dft_jobs", "training_runs")}))


if __name__ == "__main__":
    main()
