"""Independent counts, fresh SOAP and permutation-enumerated force-pair checks."""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from itertools import permutations, product
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid
from .run import CONFIG, ROOT, load, save_once


def verify_pair(pair, lookup, package):
    one, two = lookup[pair["first"]], lookup[pair["second"]]
    a = read(package/one["structure_path"], format="vasp")
    b = read(package/two["structure_path"], format="vasp")
    symbols = a.get_chemical_symbols()
    groups = [[i for i in range(45, len(a)) if symbols[i] == s] for s in sorted(set(symbols[45:]))]
    best, best_mapping = np.inf, None
    for choices in product(*(permutations(group) for group in groups)):
        mapping = np.arange(len(a))
        for first, second in zip(groups, choices, strict=True):
            mapping[first] = second
        _, lengths = find_mic(a.positions[45:]-b.positions[mapping[45:]], a.cell, [True, True, False])
        cost = float(np.sum(lengths**2))
        if cost < best:
            best, best_mapping = cost, mapping
    delta = np.array(two["forces_eV_per_A"])[best_mapping]-np.array(one["forces_eV_per_A"])
    for name, indices in {"adsorbate": slice(45, None), "movable": slice(18, None), "movable_Fe": slice(18, 45)}.items():
        norms = np.linalg.norm(delta[indices], axis=1)
        assert np.isclose(np.sqrt(np.mean(norms**2)), pair[name]["vector_RMSE_difference_eV_A"], atol=1e-12, rtol=0)
    _, fe = find_mic(a.positions[18:45]-b.positions[18:45], a.cell, [True, True, False])
    distance = max(np.sqrt(best/(len(a)-45)), np.sqrt(np.mean(fe**2)))
    assert np.isclose(distance, pair["geometry_RMSD_A"], atol=1e-12, rtol=0)


def verify():
    from dscribe.descriptors import SOAP

    config = load(CONFIG)
    output = ROOT/config["output"]
    summary = load(output/"summary.json")
    assert source_file_manifest_valid(summary)
    assert source_file_manifest_valid(load(output/"output_inventory.json"))
    manifest_path = ROOT/config["inputs"]["manifest"]["path"]
    assert sha256_file(manifest_path) == config["inputs"]["manifest"]["sha256"]
    manifest = load(manifest_path)
    original = {r["sample_id"]: r for r in manifest["splits"]["train"]}
    training = load(output/"training_environments.json")["frames"]
    pool = load(output/"pool_environments.json")["frames"]
    table = load(output/"training_joint_force.json")
    assert len(training) == len(original) == 366 and len(pool) == 1597
    assert all(r["partition"] == "train" for r in training+pool)
    bins = config["force_edges_eV_A"]
    for composition, report in table.items():
        subset = [r for r in training if r["composition"] == composition]
        assert len(subset) == report["frames"] == sum(report["fmax_histogram"].values())
        groups = [(subset, report)] + [([r for r in subset if r["joint_signature"] == item["joint_signature"]], item)
                                      for item in report["strata"]]
        for group, item in groups:
            values = [float(np.max(np.linalg.norm(np.array(original[r["sample_id"]]["forces_eV_per_A"])[18:], axis=1))) for r in group]
            counts = Counter(bisect_right(bins, value)-1 for value in values)
            assert list(item["fmax_histogram"].values()) == [counts[i] for i in range(len(bins))]
            assert sum(v <= .05 for v in values) == item["low_force_le_0p05"]
            assert item["magnetic_review_levels"] == dict(Counter(original[r["sample_id"]]["magnetic_review_level"] for r in group))
    prior = load(ROOT/config["inputs"]["prior_frames"]["path"])["frames"]
    by_id = {r["sample_id"]: r for r in pool}
    for row in prior:
        for key in ("graph_signature", "joint_signature", "coordination_signature"):
            assert row[key] == by_id[row["sample_id"]][key]
    for comp, dimensions in summary["chemical_coverage"].items():
        subset = [r for r in pool if r["composition"] == comp]
        refs = [r for r in training if r["composition"] == comp]
        for key, item in dimensions.items():
            target, represented = {r[key] for r in subset}, {r[key] for r in refs}
            assert len(target-represented) == item["current_missing"]
    inventory = load(output/"descriptor_inventory.json")
    soap = SOAP(**inventory["descriptor"]["soap"])
    fresh = []
    for comp in ("C2HO", "C2H2O", "C2H3", "C3H2O"):
        item = next(r for r in inventory["files"][:366] if original[r["sample_id"]]["composition"] == comp)
        atoms = read(manifest_path.parent/original[item["sample_id"]]["structure_path"], format="vasp")
        atoms.pbc = [True, True, False]
        with np.load(item["path"], allow_pickle=False) as cache:
            vectors = soap.create(atoms, centers=cache["centers"], n_jobs=1)
            vectors /= np.linalg.norm(vectors, axis=1)[:, None]
            assert np.allclose(vectors, cache["vectors"], atol=1e-12, rtol=0)
        fresh.append(item["sample_id"])
    # Direct NumPy comparison for the eight largest pool novelty ratios.
    cache_map = {r["sample_id"]: r for r in inventory["files"]}
    checked = []
    for query in sorted(pool, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))[:8]:
        with np.load(cache_map[query["sample_id"]]["path"], allow_pickle=False) as data:
            atoms = read(query["structure_path"], format="vasp")
            roles = np.array(atoms.get_chemical_symbols())[data["centers"]]
            vectors = data["vectors"]
        for role in set(roles):
            refs = []
            for row in training:
                if row["composition"] != query["composition"]:
                    continue
                item = cache_map[row["sample_id"]]
                with np.load(item["path"], allow_pickle=False) as data:
                    symbols = np.array(original[row["sample_id"]]["symbols"])[data["centers"]]
                    refs.extend(data["vectors"][symbols == role])
            distances = 1-np.clip(vectors[roles == role] @ np.array(refs).T, -1, 1)
            worst = float(np.max(np.min(distances, axis=1)))
            assert np.isclose(worst, query["worst_cosine_distance_by_element"][role], atol=1e-12, rtol=0)
        checked.append(query["sample_id"])
    pairs = load(output/"nearby_force_pairs.json")["pairs"]
    choices = pairs[:3] + [r for r in pairs if r["first"].startswith("10_B") and r["second"].startswith("10_B")]
    for pair in choices:
        verify_pair(pair, original, manifest_path.parent)
    receipt = {"status": "PASS", "training_frames": len(training), "pool_frames": len(pool),
               "fresh_SOAP_frames": fresh, "direct_SOAP_nearest_frames": checked,
               "independent_permutation_force_pairs": len(choices), "fixed_bins_and_all_joint_strata_checked": True,
               "unchanged_original_manifest_sha256": sha256_file(manifest_path),
               "source_files": source_file_manifest([Path(__file__), output/"summary.json", output/"output_inventory.json"])}
    save_once(output/"independent_verification.json", receipt)
    print({k:v for k,v in receipt.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
