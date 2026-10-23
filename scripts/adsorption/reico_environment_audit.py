"""Local SOAP coverage diagnostics; no force evaluation, training or submission."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.artifact_io import sha256_file


def read_geometry(row: dict):
    path = Path(row["structure_path"])
    if sha256_file(path) != row["structure_sha256"]:
        raise ValueError(f"structure hash mismatch: {row['sample_id']}")
    atoms = read(path, format="vasp")
    fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
    if (atoms.get_chemical_symbols()[:45] != ["Fe"] * 45 or fixed != list(range(18))
            or len(atoms) <= 45 or not np.isfinite(atoms.positions).all()):
        raise ValueError("invalid Fe45 geometry or fixed mask")
    atoms.pbc = [True, True, False]
    return atoms


def train_inventory(inventory: dict, selection: dict) -> tuple[list[dict], list[dict]]:
    """Validate metadata splits, but never read reserved force/energy files."""
    seen, families = set(), {}
    for row in inventory["frames"]:
        sid, family, partition = row["sample_id"], row["family_id"], row["partition"]
        if sid in seen or partition not in {"train", "development", "final_test"}:
            raise ValueError("duplicate sample or invalid partition")
        seen.add(sid)
        if families.setdefault(family, partition) != partition:
            raise ValueError("family split leakage")
    valid = {r["sample_id"]: r for r in inventory["frames"] if not r["geometry_guard_failures"]}
    selected_ids = set()
    for row in selection["selected"]:
        sid = row["sample_id"]
        if sid in selected_ids or sid not in valid or row != valid[sid]:
            raise ValueError("selected identity/binding differs from inventory")
        selected_ids.add(sid)
    train = [r for r in valid.values() if r["partition"] == "train"]
    selected = [r for r in train if r["sample_id"] in selected_ids]
    return train, selected


def local_centers(atoms, near_fe_A: float) -> np.ndarray:
    distances = atoms.get_all_distances(mic=True)
    near = np.flatnonzero(np.min(distances[18:45, 45:], axis=1) <= near_fe_A) + 18
    return np.concatenate((np.arange(45, len(atoms)), near))


def describe(row: dict, atoms, soap, cache: Path, near_fe_A: float) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (row["structure_sha256"] + ".npz")
    centers = local_centers(atoms, near_fe_A)
    if path.exists():
        with np.load(path, allow_pickle=False) as data:
            if not np.array_equal(data["centers"], centers):
                raise ValueError("descriptor cache center mismatch")
            vectors = data["vectors"]
    else:
        vectors = soap.create(atoms, centers=centers, n_jobs=1)
        norms = np.linalg.norm(vectors, axis=1)
        if not np.isfinite(vectors).all() or np.any(norms <= 0):
            raise ValueError("invalid SOAP descriptor")
        vectors = vectors / norms[:, None]
        temporary = path.with_suffix(".partial.npz")
        np.savez_compressed(temporary, centers=centers, vectors=vectors)
        temporary.replace(path)
    if vectors.shape != (len(centers), soap.get_number_of_features()) or not np.isfinite(vectors).all():
        raise ValueError("descriptor cache shape/nonfinite failure")
    return {"sample_id": row["sample_id"], "family_id": row["family_id"],
            "composition": row["composition"], "roles": np.asarray(atoms.get_chemical_symbols())[centers],
            "vectors": vectors}


def stack(records: list[dict]) -> dict:
    result = {}
    for role in ("C", "O", "H", "Fe"):
        vectors, owners, families = [], [], []
        for index, row in enumerate(records):
            block = row["vectors"][row["roles"] == role]
            if len(block):
                vectors.append(block)
                owners.extend([index] * len(block))
                families.extend([row["family_id"]] * len(block))
        if vectors:
            result[role] = {"vectors": np.concatenate(vectors), "owners": np.asarray(owners),
                            "families": np.asarray(families)}
    return result


def nearest(query: dict, reference: dict, *, leave_family_out=False) -> dict:
    result = {}
    for role, block in query.items():
        if role not in reference:
            result[role] = np.full(len(block["vectors"]), 2.)
            continue
        ref, out = reference[role], []
        for start in range(0, len(block["vectors"]), 256):
            dot = block["vectors"][start:start + 256] @ ref["vectors"].T
            if leave_family_out:
                mask = block["families"][start:start + 256, None] == ref["families"][None, :]
                dot[mask] = -np.inf
            maximum = np.max(dot, axis=1)
            if not np.isfinite(maximum).all():
                raise ValueError("leave-family-out calibration requires two families per element")
            out.append(1. - np.clip(maximum, -1., 1.))
        result[role] = np.concatenate(out)
    return result


def calibrate(reference: dict, quantile: float) -> tuple[dict, dict]:
    if not 0 < quantile < 1:
        raise ValueError("invalid calibration quantile")
    distances = nearest(reference, reference, leave_family_out=True)
    thresholds = {role: max(float(np.quantile(values, quantile)), 1e-12) for role, values in distances.items()}
    sensitivity = {str(q): {role: float(np.quantile(v, q)) for role, v in distances.items()}
                   for q in (.90, .95, .99)}
    return thresholds, sensitivity


def frame_scores(records: list[dict], pool: dict, distances: dict, thresholds: dict) -> list[dict]:
    scores = np.zeros(len(records))
    detail = [{} for _ in records]
    for role, values in distances.items():
        worst = np.zeros(len(records))
        np.maximum.at(worst, pool[role]["owners"], values)
        scores = np.maximum(scores, worst / thresholds[role])
        for index in np.unique(pool[role]["owners"]):
            detail[index][role] = float(worst[index])
    return [{"sample_id": row["sample_id"], "family_id": row["family_id"], "composition": row["composition"],
             "novelty_ratio": float(scores[i]), "worst_cosine_distance_by_element": detail[i],
             "exceeds_internal_threshold": bool(scores[i] > 1. + 1e-9)} for i, row in enumerate(records)]


def coverage_summary(pool: dict, distances: dict, thresholds: dict) -> dict:
    return {role: {"local_environment_count": len(values), "above_internal_threshold": int(np.sum(values > thresholds[role])),
                   "fraction_within_internal_threshold": float(np.mean(values <= thresholds[role])),
                   "p95_cosine_distance": float(np.quantile(values, .95)), "maximum_cosine_distance": float(np.max(values))}
            for role, values in distances.items()}


def propose_additions(records: list[dict], selected_ids: set[str], pool: dict, distances: dict,
                      thresholds: dict, maximum: int, eligible=None) -> tuple[list[dict], dict]:
    """Greedy bounded proposal, not a proof of the globally smallest dataset."""
    if maximum < 0:
        raise ValueError("negative proposal budget")
    current = {key: value.copy() for key, value in distances.items()}
    proposed, families = [], set()
    record_map = {row["sample_id"]: row for row in records}
    while len(proposed) < maximum:
        ranked = sorted(frame_scores(records, pool, current, thresholds),
                        key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
        chosen = next((r for r in ranked if r["sample_id"] not in selected_ids and r["family_id"] not in families
                       and r["exceeds_internal_threshold"] and (eligible is None or eligible(r, proposed))), None)
        if chosen is None:
            break
        proposed.append(chosen)
        families.add(chosen["family_id"])
        added = nearest(pool, stack([record_map[chosen["sample_id"]]]))
        for role in current:
            current[role] = np.minimum(current[role], added[role])
    return proposed, current


def source_counts(rows: list[dict]) -> dict:
    return {"frames": len(rows), "families": len({r["family_id"] for r in rows}),
            "compositions": dict(Counter(r["composition"] for r in rows))}
