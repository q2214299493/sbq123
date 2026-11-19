"""Recompute the scoped geometry, lineage and split proof without touching either package."""

from itertools import combinations
from pathlib import Path
import re
import yaml
from scripts.artifact_io import source_file_manifest, write_json_exclusive
from ase.io import read
from archive.fe110_joint_priority_20261117.analyze import BASE, ROOT, SLAB, guard_hashes, load, sha
from archive.fe110_c2_c4_joint_candidates_20261114.audit import external_c2_proposals
from archive.fe110_c2_c4_joint_candidates_20261114.geometry import canonical_iron, composition_key, distance_metrics, iron_maps, packed_pose
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_chemical_environments import chemical_environment


def nearest_by_group(xyz, refs, maps, protect_names):
    first_fe = canonical_iron(xyz, maps["clean_frac"])
    key = composition_key(xyz)
    distances = {}
    for name, entries in refs.items():
        if name.startswith("512_") and name != "512_train":
            continue
        matched = [(distance_metrics(xyz, r, first_fe), r) for r in entries if key == r["key"]]
        if not matched:
            distances[name] = None
            continue
        field = "minimum_ads_pose_RMSD_A" if name in protect_names else "full_RMSD_A"
        best, ref = min(matched, key=lambda pair: (pair[0][field], pair[1]["id"]))
        distances[name] = {"reference": ref["id"], "rmsd_A": round(best[field], 8), "compared": len(matched)}
    return distances


def checked_packages():
    packs = {}
    for name, n in (("combined_force_package_20261027_v3", 512), ("combined_force_package_20261113_v1", 536)):
        d = BASE / name
        manifest = load(d / "training_manifest.json")
        splits = {**manifest["splits"], "observed_heldout": manifest["quarantined_observed_heldout"]}
        assert {k: len(v) for k, v in splits.items()} == {"train": n, "development": 78, "heldout": 53, "observed_heldout": 16}
        packs[n] = (d, splits)

    def signature(row):
        return tuple(
            row.get(k)
            for k in (
                "sample_id",
                "source_job_id",
                "calculation_group",
                "structure_sha256",
                "source_OUTCAR_sha256",
                "source_force_table_sha256",
                "family_id",
            )
        )

    for split in ("development", "heldout", "observed_heldout"):
        assert list(map(signature, packs[512][1][split])) == list(map(signature, packs[536][1][split]))
    assert set(map(signature, packs[512][1]["train"])) <= set(map(signature, packs[536][1]["train"]))
    return packs


def return_file_hashes(sampling):
    return_hash = {}
    for parent in (sampling, BASE / "sampling6_v1"):
        returned = parent / "returned"
        for r in load(returned / "return_manifest.json")["files"]:
            return_hash[(returned / Path(r["path"])).resolve()] = r["sha256"]
    return return_hash


def same_composition_pairs(data, pose_by_id, ops, maps):
    pairs = []
    for x, y in combinations(data, 2):
        a, b = pose_by_id[x["id"]], pose_by_id[y["id"]]
        if composition_key(a) == composition_key(b):
            d = distance_metrics(a, packed_pose(b, ops, maps))["full_RMSD_A"]
            pairs.append((d, x["id"], y["id"]))
    return pairs


def require_reference_hashes(paths, hashes):
    for path in paths:
        assert sha(path) == hashes.get(str(path.resolve())), f"reference provenance changed: {path}"


def main():
    run = BASE / "c2_c3_label9_lsf_20261118_v1"
    output = BASE / "force545_increment9_20261119_v2"
    source = BASE / "c2_c3_label_preflight_20261118_v1/review.json"
    plan = load(run / "final_submission_list.json")
    assert sha(run / "final_submission_list.json") == "4ac145dc610571030b1738bef87f5b4b6be0190c0ce49104bbf1eea93537b388"
    assert sha(source) == plan["source_preflight_sha256"]
    assert guard_hashes() == plan["frozen_hashes"]
    preflight = {r["id"]: r for r in load(source)["DFT_first_ten"]}
    joint = load(BASE / "joint_priority614_20261117_v1/results_v2/joint_priority.json")
    candidates = {r["candidate_id"]: r for r in joint["candidate_audit"]}
    sampling = BASE / "sampling93_v1"
    return_hash = return_file_hashes(sampling)
    prior_jobs = (
        load(sampling / "dft_inputs_v1/batch_request.json")["samples"]
        + load(BASE / "sampling6_v1/dft_review6_v1/batch_request.json")["samples"]
    )
    old_ids = {r["sample_id"] for r in prior_jobs}
    old_geometry = {r["structure_sha256"] for r in prior_jobs}

    reference_path = BASE / "c2_c4_joint_candidates_20261114_v1/coordinate_site_isolation_audit_v4.json"
    previous = load(reference_path)
    hashes = {str(Path(r["path"]).resolve()): r["sha256"] for r in previous["source_files"]}
    cfgpath = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    config = load(cfgpath)
    prior_manifest = ROOT / config["prior_manifest"]
    inventory_path = ROOT / config["inventory"]
    seed_file = BASE / "c3_independent_validation_proposal_20261113_v1/proposal_evidence.json"
    near_dir = BASE / "independent_nearstable_inventory_20261113_v1"
    sidecar_file = BASE / "energy_reaction_sidecar_20261113_v1/energy_label_sidecar_final_v2.json"
    require_reference_hashes(
        [
            cfgpath,
            prior_manifest,
            inventory_path,
            seed_file,
            sidecar_file,
            near_dir / "source_plan.json",
            near_dir / "physical_inventory.json",
        ],
        hashes,
    )
    inventory = load(inventory_path)
    inventory_by_id = {r["sample_id"]: r for r in inventory["frames"]}
    slab = read_poscar(SLAB)
    ops = surface_pose_symmetries(slab)
    assert len(ops) == 36
    maps = iron_maps(slab, ops)

    packs = checked_packages()

    cache = {}

    def add(row, path, check_prior=False):
        digest = sha(path)
        if row.get("structure_sha256"):
            assert digest == row["structure_sha256"], f"geometry hash mismatch {row.get('sample_id')}"
        if check_prior:
            assert digest == hashes.get(str(path.resolve())), f"unbound geometry {path}"
        if digest not in cache:
            cache[digest] = packed_pose(read_poscar(path), ops, maps)
        return {
            **cache[digest],
            "id": row["sample_id"],
            "source": str(path),
            "sha": digest,
            "family_id": row.get("family_id"),
            "source_job_id": row.get("source_job_id"),
            "calculation_group": row.get("calculation_group"),
        }

    refs = {}
    for n, (p, splits) in packs.items():
        for split, rows in splits.items():
            refs[f"{n}_{split}"] = [add(r, p / r["structure_path"]) for r in rows]
    reserved = reserved_geometries(
        inventory, load(prior_manifest), prior_manifest.parent, [ROOT / p for p in config["reserved_geometry_catalogs"]]
    )
    assert len(reserved) == 513 and config["reserved_geometry_isolation_A"] == 0.20
    refs["legacy_reserved"] = [add(r, Path(r["structure_path"]), True) for r, _ in reserved]
    refs["c3_seed"] = [
        add({"sample_id": r["candidate_id"]}, Path(r["proposed_pose_file"]), True)
        for r in load(seed_file)["candidates"]
        if r["proposed_pose_file"]
    ]
    refs["external_C2"], c2_files = external_c2_proposals(ops, maps)
    assert all(sha(p) == hashes.get(str(p.resolve())) for p in c2_files)
    refs["path_holdout"] = [add({"sample_id": r["record_id"]}, Path(r["structure_path"])) for r in joint["path_labels"] if r["protected"]]
    assert len(refs["c3_seed"]) == 3 and len(refs["external_C2"]) == 26 and len(refs["path_holdout"]) == 6
    assert all(r["key"] == (("C", 1), ("H", 1)) for r in refs["path_holdout"])
    catalog = load(sidecar_file)["records"]
    catalog_unique = {}
    for row in catalog:
        path = Path(row["structure_path"])
        digest = sha(path)
        if digest not in catalog_unique:
            catalog_unique[digest] = add(row, path, True)
    refs["existing_labels"] = list(catalog_unique.values())
    assert len(refs["existing_labels"]) == 861

    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))["connectivity"]
    scales = ("1.2", "1.25", "1.3")

    def envs(path):
        atoms = read(path, format="vasp")
        return {s: chemical_environment(atoms, rules, scale=float(s))["joint_signature"] for s in scales}

    def family_tag(row):
        v = row.get("family_id")
        if v:
            return v
        m = re.search(r"family_\d{4}", str(row.get("calculation_group") or row.get("sample_id") or row.get("id") or ""))
        return m[0] if m else None

    protect_names = ["536_development", "536_heldout", "536_observed_heldout", "legacy_reserved", "external_C2", "c3_seed", "path_holdout"]
    protect_families = {family_tag(ref) for k in protect_names for ref in refs[k]}
    protect_jobs = {str(ref.get("source_job_id")) for k in protect_names for ref in refs[k]}
    seen_output_hashes = {str(r.get("source_OUTCAR_sha256")) for r in catalog}
    source_jobs = {str(r.get("source_job_id")) for r in catalog}

    pose_by_id = {}
    data = []
    for row in plan["jobs"]:
        sid = row["id"]
        p = preflight[sid]
        c = candidates[sid]
        inv = inventory_by_id[sid]
        folder = Path(row["local_input_directory"])
        src = Path(p["coordinate_path"])
        seed = src.with_name("step_000.vasp")
        frame = Path(c["frame_metadata_path"])
        fam = p["family_id"]
        asserted_step = int(sid.rsplit("step", 1)[1])
        assert inv["partition"] == "train" and inv["family_id"] == c["family_id"] == fam and Path(inv["structure_path"]) == src
        assert sha(frame) == c["frame_metadata_sha256"] == inv["frame_metadata_sha256"] == return_hash[frame.resolve()]
        assert (
            sha(src)
            == p["coordinate_sha256"]
            == c["source_sha256"]
            == inv["structure_sha256"]
            == row["input_sha256"]["POSCAR"]
            == return_hash[src.resolve()]
            == sha(folder / "POSCAR")
        )
        assert sha(seed) == p["validated_source_seed_sha256"] == return_hash[seed.resolve()]
        meta = load(frame)
        assert meta["step"] == asserted_step and meta["structure_sha256"] == sha(src) and meta["structure_path"] == src.name
        assert not meta["geometry_audit"]["failures"] and not p["fresh_geometry"]["pair_guard_failures"]
        assert sid not in old_ids and sha(src) not in old_geometry
        source_jobs_in_train = sorted({str(r["source_job_id"]) for r in packs[536][1]["train"] if family_tag(r) == fam})
        bind_record = load(folder / "submission_geometry_review.json")
        assert bind_record["coordinate_source"]["sha256"] == sha(src) and bind_record["reviewed_input"]["sha256"] == sha(source)
        rec = load(folder / "submission_record.json")
        job = rec["job_id"]
        assert job not in source_jobs and job not in protect_jobs
        assert fam not in protect_families and len(source_jobs_in_train) >= 1
        xyz = read_poscar(src)
        pose_by_id[sid] = xyz
        distances = nearest_by_group(xyz, refs, maps, protect_names)
        near_train = distances["536_train"]
        train_ref = next(r for r in refs["536_train"] if r["id"] == near_train["reference"])
        mine = envs(src)
        assert mine == p["joint_by_scale"] == c["joint_by_scale"]
        ref_env = envs(train_ref["source"])
        protect_min = min((v["rmsd_A"], k, v["reference"]) for k, v in distances.items() if k in protect_names and v is not None)
        extra = {
            "id": sid,
            "job": job,
            "source_step": asserted_step,
            "source_poscar_sha": sha(src),
            "existing_training_job_ids_same_family": source_jobs_in_train,
            "existing_train_frames_same_family": sum(family_tag(r) == fam for r in packs[536][1]["train"]),
            "exact_train_or_existing_label_match": any(
                v["rmsd_A"] <= 1e-7 for k, v in distances.items() if k in ("512_train", "536_train", "existing_labels") and v is not None
            ),
            "nearest": distances,
            "min_protected": protect_min,
            "matches_nearest_training_joint_signature_scales": [s for s in scales if mine[s] == ref_env[s]],
            "compatible_training_source_family": bool(source_jobs_in_train),
        }
        if (
            protect_min[0] <= 0.20
            or near_train["rmsd_A"] < 0.10
            or distances["existing_labels"]["rmsd_A"] < 0.10
            or extra["exact_train_or_existing_label_match"]
        ):
            raise ValueError(f"Protected or duplicate geometry: {sid}")
        if extra["matches_nearest_training_joint_signature_scales"]:
            raise ValueError(f"Candidate coverage changed: {sid}")
        extra["source_bindings"] = source_file_manifest([src, seed, frame, folder / "submission_record.json"])
        extra["family_id"] = fam
        data.append(extra)
    pairs = same_composition_pairs(data, pose_by_id, ops, maps)
    assert len(pairs) == 13
    assert min(pairs)[0] >= 0.10 and guard_hashes() == plan["frozen_hashes"]
    assert len(data) == len({x["family_id"] for x in data}) == 9
    proof_inputs = [
        source,
        run / "final_submission_list.json",
        reference_path,
        cfgpath,
        prior_manifest,
        inventory_path,
        seed_file,
        sidecar_file,
        SLAB,
        Path(__file__),
        ROOT / "configs/adsmind_lite/analysis_rules.yaml",
        BASE / "joint_priority614_20261117_v1/results_v2/joint_priority.json",
        *[p / "training_manifest.json" for p, _ in packs.values()],
        *[BASE / name / "returned/return_manifest.json" for name in ("sampling6_v1", "sampling93_v1")],
        *[Path(r["source"]) for r in refs["path_holdout"]],
        *c2_files,
    ]
    write_json_exclusive(
        output / "isolation_review.json",
        {
            "schema_version": 1,
            "status": "NINE_TRAIN_ONLY_SOURCE_AND_GEOMETRY_ISOLATION_PASS",
            "source_files": source_file_manifest(proof_inputs),
            "surface_operations": len(ops),
            "reference_counts": {k: len(v) for k, v in refs.items()},
            "protected_families_checked": len(protect_families - {None}),
            "existing_catalog_OUTCAR_hash_count": len(seen_output_hashes - {"None"}),
            "distance_method": "Fe(110) symmetry and same-element permutations, preserving fixed vs movable Fe",
            "protected_adsorbate_distance_minimum_exclusive_A": 0.20,
            "training_movable_Fe_and_adsorbate_distance_minimum_inclusive_A": 0.10,
            "heldout_label_values_used": False,
            "frozen_guards_unchanged": True,
            "samples": data,
            "same_composition_pair_distances_A": pairs,
            "closest_batch_pair": min(pairs),
            "training_authorized": False,
        },
    )
    print("9 source-isolation rows and 13 pair comparisons passed")


if __name__ == "__main__":
    main()
