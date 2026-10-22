"""Geometry-only selection of off-equilibrium Fe45 frames with frozen family splits."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read
from scipy.optimize import linear_sum_assignment

from scripts.artifact_io import sha256_file


def frame_distance(first, second) -> float:
    """Max of adsorbate/permuted and movable-Fe vector RMSD, in Angstrom.

    Fe indices, slab origin and cell stay fixed. XY periodic images and equal
    adsorbate-element permutations are equivalent; rigid molecular alignment is
    deliberately absent because it would erase adsorption-site information.
    """
    if (Counter(first.get_chemical_symbols()) != Counter(second.get_chemical_symbols())
            or not np.allclose(first.cell, second.cell, atol=1e-12, rtol=0)):
        return float("inf")
    a, b = first.get_chemical_symbols(), second.get_chemical_symbols()
    squared = 0.
    for element in sorted(set(a[45:])):
        one = [i for i in range(45, len(a)) if a[i] == element]
        two = [i for i in range(45, len(b)) if b[i] == element]
        vectors = first.positions[one, None, :] - second.positions[None, two, :]
        _, lengths = find_mic(vectors.reshape(-1, 3), first.cell, [True, True, False])
        cost = lengths.reshape(len(one), len(two)) ** 2
        rows, columns = linear_sum_assignment(cost)
        squared += float(cost[rows, columns].sum())
    ads = np.sqrt(squared / (len(a) - 45))
    _, lengths = find_mic(first.positions[18:45] - second.positions[18:45], first.cell, [True, True, False])
    fe = np.sqrt(np.mean(lengths ** 2))
    return float(max(ads, fe))


def _read_frames(records):
    if len({r["sample_id"] for r in records}) != len(records):
        raise ValueError("duplicate sample identity")
    families, atoms = defaultdict(list), {}
    rejected = []
    for row in records:
        families[row["family_id"]].append(row)
        if row["partition"] not in {"train", "development", "final_test"}:
            raise ValueError("unknown frozen partition")
    for group in families.values():
        if len({(r["composition"], r["partition"]) for r in group}) != 1:
            raise ValueError("family split/composition leakage")
        if len({r["step"] for r in group}) != len(group):
            raise ValueError("duplicate trajectory step")
    for row in records:
        if row["geometry_guard_failures"]:
            if row.get("already_DFT_labeled"):
                raise ValueError("existing label has unresolved geometry guard")
            rejected.append({"sample_id": row["sample_id"], "reason": "geometry_guard_boundary_preserved"})
            continue
        path = Path(row["structure_path"])
        if sha256_file(path) != row["structure_sha256"]:
            raise ValueError("frame bytes changed")
        current = read(path, format="vasp")
        fixed = sorted(int(i) for c in current.constraints for i in c.get_indices())
        if (current.get_chemical_symbols()[:45] != ["Fe"] * 45 or fixed != list(range(18))
                or len(current) <= 45 or not np.isfinite(current.positions).all()):
            raise ValueError("invalid Fe45 frame")
        atoms[row["sample_id"]] = current
    return families, atoms, rejected


def select_frames(records: list[dict], *, maximum_per_family=3, maximum_total=300,
                  rmsd_A=.10) -> dict:
    """Keep existing labels, then select farthest frames within each family.

    This selects a deduplicated subset, not an exhaustive clustering of every
    trajectory frame. Model energies, model errors and convergence are unused.
    """
    if maximum_per_family < 1 or maximum_total < 1 or rmsd_A <= 0:
        raise ValueError("invalid selection bounds")
    families, atoms, rejected = _read_frames(records)
    labeled = [r for r in records if r.get("already_DFT_labeled")]
    if len(labeled) > maximum_total:
        raise ValueError("existing labels already exceed total budget")
    label_counts = Counter(r["family_id"] for r in labeled)
    if any(n > maximum_per_family for n in label_counts.values()):
        raise ValueError("existing family labels exceed quota")
    selected, selected_ids = [], set()
    counts = Counter()
    comparisons = {}

    def distance(one, two):
        key = tuple(sorted((one["sample_id"], two["sample_id"])))
        if key not in comparisons:
            comparisons[key] = frame_distance(atoms[key[0]], atoms[key[1]])
        return comparisons[key]

    def append(row, mandatory=False):
        for earlier in selected:
            if earlier["composition"] == row["composition"] and distance(row, earlier) < rmsd_A:
                if mandatory:
                    raise ValueError("existing DFT labels need duplicate/split review")
                rejected.append({"sample_id": row["sample_id"], "duplicate_of": earlier["sample_id"],
                    "reason": "near_duplicate_cross_partition" if row["partition"] != earlier["partition"] else "near_duplicate"})
                return False
        selected.append(dict(row))
        selected_ids.add(row["sample_id"])
        counts[row["family_id"]] += 1
        return True

    for row in sorted(labeled, key=lambda r: (r["family_id"], r["step"])):
        append(row, mandatory=True)
    priorities = {"final_test": 0, "development": 1, "train": 2}
    order = sorted(families, key=lambda k: (priorities[families[k][0]["partition"]], k))
    for family in order:
        group = [r for r in families[family] if r["sample_id"] in atoms and r["sample_id"] not in selected_ids]
        group.sort(key=lambda r: r["step"])
        while group and counts[family] < maximum_per_family and len(selected) < maximum_total:
            anchors = [r for r in selected if r["family_id"] == family]
            row = max(group, key=lambda r: (min(distance(r, a) for a in anchors), r["step"])) if anchors else group[0]
            group.remove(row)
            append(row)
    selected.sort(key=lambda r: (r["family_id"], r["step"]))
    return {"document_kind": "geometry_only_reico_selected_frames", "selected": selected,
            "input_frame_count": len(records), "guard_valid_frame_count": len(atoms),
            "selected_count": len(selected), "existing_DFT_labels": len(labeled),
            "new_DFT_candidates": len(selected) - len(labeled), "maximum_total": maximum_total,
            "maximum_per_family": maximum_per_family, "threshold_vector_RMSD_A": rmsd_A,
            "partition_counts": dict(Counter(r["partition"] for r in selected)),
            "composition_counts": dict(Counter(r["composition"] for r in selected)),
            "short_families": {f: counts[f] for f in sorted(families) if counts[f] < maximum_per_family},
            "rejected": rejected, "unused_frame_count": len(records) - len(selected) - len(rejected),
            "deduplication_scope": "selected subset;XY periodic and equal-element permutations;fixed slab origin;no full surface-space-group symmetry",
            "model_accuracy_or_convergence_filter": False, "training_performed": False}
