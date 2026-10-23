"""Independent real-frame checks for the completed local stratified audit."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from ase.data import atomic_numbers, covalent_radii
from dscribe.descriptors import SOAP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.adsorption.reico_environment_audit import read_geometry  # noqa: E402
from scripts.adsorption.reico_chemical_environments import chemical_environment  # noqa: E402
from scripts.artifact_io import sha256_file, sha256_json, source_file_manifest_valid, write_json  # noqa: E402


def review_examples(output: Path, frames: list, selected: set) -> list:
    examples = json.loads((output / "candidate_catalog.json").read_text(encoding="utf-8"))["priority_examples"]
    reference = {}
    for row in frames:
        if row["sample_id"] in selected:
            atoms = read_geometry(row)
            for scale in (1.20, 1.25, 1.30):
                environment = chemical_environment(atoms, {"covalent_radius_scale": scale, "minimum_bond_distance_angstrom": .35})
                key = (row["composition"], scale)
                reference.setdefault(key, {"graph_signature": set(), "joint_signature": set()})
                for name in reference[key]:
                    reference[key][name].add(environment[name])
    results = []
    for row in examples:
        atoms = read_geometry(row)
        scales = {}
        for scale in (1.20, 1.25, 1.30):
            environment = chemical_environment(atoms, {"covalent_radius_scale": scale, "minimum_bond_distance_angstrom": .35})
            scales[str(scale)] = {name: environment[name] not in reference[(row["composition"], scale)][name]
                                 for name in ("graph_signature", "joint_signature")}
        results.append({"sample_id": row["sample_id"], "composition": row["composition"],
                        "missing_from_selected_by_scale": scales,
                        "joint_missing_at_all_three_scales": all(v["joint_signature"] for v in scales.values())})
    write_json(output / "priority_sensitivity.json", {"examples": results, "DFT_required_inferred": False})
    return results


def verify(output: Path) -> dict:
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "AUDIT_COMPLETE"
    assert source_file_manifest_valid(summary)
    frames = json.loads((output / "frame_environments.json").read_text(encoding="utf-8"))["frames"]
    assert len(frames) == 1597 and all(r["partition"] == "train" for r in frames)
    old_root = ROOT / "calculations/fe110_reico_pilot300_20261022/coverage_audit_v1"
    old = json.loads((old_root / "audit_summary.json").read_text(encoding="utf-8"))
    assert source_file_manifest_valid(old)
    selected_rows = json.loads(Path(old["config"]["selection"]).read_text(encoding="utf-8"))["selected"]
    selected = {r["sample_id"] for r in selected_rows if r["partition"] == "train"}
    assert len(selected_rows) == 292 and len(selected) == 233
    binding = json.loads((old_root / "coverage.json").read_text(encoding="utf-8"))["descriptor"]
    cache = old_root / "descriptor_cache" / sha256_json(binding)
    soap = SOAP(**binding["soap"])
    results = []
    for composition in sorted({r["composition"] for r in frames}):
        subset = [r for r in frames if r["composition"] == composition]
        query = min(subset, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
        atoms = read_geometry(query)
        with np.load(cache/(query["structure_sha256"]+".npz"), allow_pickle=False) as d:
            vectors, centers = d["vectors"], d["centers"]
        fresh = soap.create(atoms, centers=centers, n_jobs=1)
        fresh /= np.linalg.norm(fresh, axis=1)[:, None]
        np.testing.assert_allclose(fresh, vectors, atol=1e-12, rtol=0)
        roles = np.asarray(atoms.get_chemical_symbols())[centers]
        reference = {}
        for row in subset:
            if row["sample_id"] not in selected:
                continue
            other = read_geometry(row)
            with np.load(cache/(row["structure_sha256"]+".npz"), allow_pickle=False) as d:
                other_roles = np.asarray(other.get_chemical_symbols())[d["centers"]]
                for element in set(other_roles):
                    reference.setdefault(element, []).append(d["vectors"][other_roles == element])
        for element in set(roles):
            direct = float(np.max(1-np.clip(np.max(vectors[roles == element] @ np.concatenate(reference[element]).T, axis=1), -1., 1.)))
            assert abs(direct-query["worst_cosine_distance_by_element"][element]) < 1e-12
        ads = atoms.get_chemical_symbols()[45:]
        numbers = atoms.numbers[45:]
        distances = atoms.get_all_distances(mic=True)[45:, :45]
        cutoffs = 1.25*(covalent_radii[atomic_numbers["Fe"]]+covalent_radii[numbers])
        counts = np.count_nonzero((distances >= .35) & (distances <= cutoffs[:,None]), axis=1).tolist()
        assert counts == query["Fe_coordination_by_adsorbate_index"]
        assert len(ads) == len(counts)
        for key in ("graph_signature", "coordination_signature", "joint_signature"):
            pool = Counter(r[key] for r in subset)
            refs = Counter(r[key] for r in subset if r["sample_id"] in selected)
            saved = summary["chemical_strata"][composition][key]
            assert len(pool) == saved["pool_strata"]
            assert sum(s not in refs for s in pool) == saved["missing_strata"]
            assert sum(n for s,n in pool.items() if s not in refs) == saved["frames_in_missing_strata"]
        results.append({"composition": composition, "real_frame": query["sample_id"],
                        "fresh_SOAP_matches_cache": True, "direct_numpy_distances_match": True,
                        "Fe_contact_counts_match": True, "all_strata_counts_match": True})
    result = {"status": "PASS", "real_frame_checks": results, "source_bindings_valid": True,
              "original_selection_unchanged": True, "training_only": True,
              "new_DFT_ML_or_training": False, "summary_sha256": sha256_file(output/"summary.json")}
    examples = review_examples(output, frames, selected)
    result["priority_examples_checked_at_three_scales"] = len(examples)
    result["joint_missing_at_all_three_scales"] = sum(r["joint_missing_at_all_three_scales"] for r in examples)
    write_json(output / "independent_verification.json", result)
    return result


if __name__ == "__main__":
    result = verify(ROOT / "calculations/fe110_reico_pilot300_20261022/stratified_audit_v1")
    print(json.dumps({"status": result["status"], "real_frame_checks": len(result["real_frame_checks"])}))
