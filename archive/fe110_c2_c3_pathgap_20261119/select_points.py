"""Revalidate the exact REICO20 and expand from bound, unlabeled path environments."""

from collections import Counter
from scripts.artifact_io import source_file_manifest, write_json_exclusive
from pathlib import Path
from archive.fe110_joint_priority_20261117.analyze import BASE, SLAB, load, sha
from archive.fe110_c2_c4_joint_candidates_20261114.collect_sources import PRIOR
from archive.fe110_c2_c4_joint_candidates_20261114.geometry import iron_maps, packed_pose, distance_metrics, composition_key, canonical_iron
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries


def main():
    base = BASE / "joint_priority614_20261117_v1/results_v2"
    RUN = BASE / "c2_c3_reico_pathgap_20261119_v1"
    EXPECTED_IDS = {
        f"family_{a}_step{b}"
        for a, b in (
            x.split("/")
            for x in "0007/004 0013/004 0050/006 0003/013 0065/004 0062/006 0023/005 0035/003 0039/006 0039/013 0056/014 0060/014 0077/014 0078/014 0091/014 0092/004 0094/014 0096/013 0100/004 0100/014".split()
        )
    }

    path = load(BASE / "c2_c3_path_label_audit_20261118_v1/reviewed_v2/path_audit.json")
    j = load(base / "joint_priority.json")
    pool = load(BASE / "joint_coverage_20261023_v3/pool_environments.json")["frames"]
    bindings = {x["sample_id"]: x["label_status"] for x in load(PRIOR / "reico_pool_label_bindings_v3.json")["records"]}
    use = {r["id"]: r for r in path["candidate_decisions"]}
    ranks = {r["id"]: r["rank"] for r in path["selected"]}
    new = load(BASE / "force545_increment9_20261119_v2/increment_manifest.json")["samples"]
    newloc = BASE / "force545_increment9_20261119_v2"
    newids = {x["sample_id"] for x in new}
    new_shas = {x["structure_sha256"] for x in new}
    idx = {r["sample_id"]: r for r in pool}
    frozen545 = load(BASE / "force545_training_package_20261119_v1/training_manifest.json")
    rows = {r["sample_id"]: r for r in frozen545["splits"]["train"]}
    training = {x["sample_id"]: x for x in j["frames"] if x["partition"] == "train"}
    scales = ("1.2", "1.25", "1.3")
    coverage = {k: set() for k in scales}
    for k, x in rows.items():
        y = idx[k] if k in newids else training[k]
        assert y["structure_sha256"] == x["structure_sha256"]
        for s in scales:
            coverage[s].add((x["composition"], y["joint_by_scale"][s]))
    backup = {
        (x["composition"], x["joint_signature_at_default_scale"])
        for x in j["backup_labels"]
        if x["coordinate_force_match"]
        and x["raw_positive_Fe_local_moments"]
        and x["compatibility"]["active_PBE_Fe45_sigma0p20_branch_observed"]
    }

    def signature(row):
        return (row["composition"], row["joint_by_scale"]["1.25"])

    def robust(row):
        return all((row["composition"], row["joint_by_scale"][k]) not in coverage[k] for k in scales)

    broad = [
        x
        for x in pool
        if x["partition"] == "train"
        and bindings[x["sample_id"]] == "NO_SAME_COORDINATE_DFT_LABEL_IN_AUDITED_CATALOG"
        and not x["geometry_guard_failures"]
        and x["structure_sha256"] not in new_shas
        and robust(x)
        and signature(x) not in backup
    ]
    print("broader unreviewed pool", len(broad), Counter(a for (a, b) in {signature(x) for x in broad}))
    print(
        "existing backup labels",
        len(j["backup_labels"]),
        "default joint signatures fill 545 gap",
        Counter(a for (a, b) in backup - coverage["1.25"]),
    )

    from archive.fe110_joint_priority_20261117.analyze import ROOT
    from archive.fe110_c2_c4_joint_candidates_20261114.audit import external_c2_proposals
    from scripts.adsorption.reico_dataset_audit import reserved_geometries
    from collections import defaultdict

    slab = read_poscar(SLAB)
    ops = surface_pose_symmetries(slab)
    mp = iron_maps(slab, ops)
    ref_cfg = load(ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json")
    prior = ROOT / ref_cfg["prior_manifest"]
    reserved = reserved_geometries(
        load(ROOT / ref_cfg["inventory"]), load(prior), prior.parent, [ROOT / x for x in ref_cfg["reserved_geometry_catalogs"]]
    )
    assert len(reserved) == 513
    mroot = BASE / "force545_training_package_20261119_v1"
    known_categories = defaultdict(list)
    cache = {}

    def add(refs, name, path, row=None):
        d = sha(path)
        if row and row.get("structure_sha256"):
            assert d == row["structure_sha256"], str(path)
        if d not in cache:
            cache[d] = packed_pose(read_poscar(path), ops, mp)
        v = cache[d]
        refs[v["key"]].append((name, v))

    protected = defaultdict(list)
    known = defaultdict(list)
    protected_fams = {r.get("family_id") for r, x in reserved if r.get("family_id")}
    for r, _ in reserved:
        add(protected, r["sample_id"], Path(r["structure_path"]), r)
    for group, arr in {**frozen545["splits"], "quarantine": frozen545["quarantined_observed_heldout"]}.items():
        for r in arr:
            add(known if group == "train" else protected, r["sample_id"], mroot / r["structure_path"], r)
            if group != "train" and r.get("family_id"):
                protected_fams.add(r["family_id"])
    for r in load(BASE / "c3_independent_validation_proposal_20261113_v1/proposal_evidence.json")["candidates"]:
        if r["proposed_pose_file"]:
            add(protected, r["candidate_id"], Path(r["proposed_pose_file"]))
    c2, _ = external_c2_proposals(ops, mp)
    for r in c2:
        protected[r["key"]].append((r["id"], r))
    c2_start = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/final_review_20261101_v1/sources/11_B/POSCAR"
    c3_start = ROOT / "calculations/fe110_care8_isomers_20260716/revised/05_C3H2O_FLJNAOYG_cfg2/POSCAR"
    historical_c3 = ROOT / "calculations/fe110_c3_existing_recovery_20261023/collection_v1/9629858/POSCAR"
    for name, p in (("11_B", c2_start), ("05_cfg2", c3_start), ("G08_9629858", historical_c3)):
        add(protected, name, p)
    side = load(BASE / "energy_reaction_sidecar_20261113_v1/energy_label_sidecar_final_v2.json")["records"]
    for r in side:
        add(known, r["sample_id"], Path(r["structure_path"]), r)
    # Compare each distinct pose once per list; aliases are already bound by hash.
    for label in (protected, known):
        for key, values in label.items():
            label[key] = list({id(x): (name, x) for name, x in values}.values())
    print(
        "ref geometry",
        sum(map(len, protected.values())),
        sum(map(len, known.values())),
        "selected prior 20 still eligible",
        sum(x["sample_id"] in ranks for x in broad),
        flush=True,
    )
    set_guard = {row["candidate_id"]: row for row in j["candidate_audit"]}
    rejection = Counter()
    qualified = []
    for row in sorted((x for x in broad if x["sample_id"] in EXPECTED_IDS), key=lambda r: (ranks.get(r["sample_id"], 100), r["sample_id"])):
        sid = row["sample_id"]
        if (
            row["family_id"] in protected_fams
            or row["family_id"] in {"family_0028", "family_0086", "family_0021"}
            or sid == "family_0001_step002"
        ):
            rejection["protected, pre-existing family risk or deferred O-Fe"] += 1
            continue
        previous = set_guard.get(sid, {})
        if previous.get("new_SP_review_blockers"):
            rejection["prior blockers"] += 1
            continue
        # Deduplicate within and against planned train coverage only after reviewing coordinates.
        source = Path(row["structure_path"])
        meta = Path(row["frame_metadata_path"])
        assert sha(source) == row["structure_sha256"] and sha(meta) == row["frame_metadata_sha256"]
        assert load(meta)["structure_sha256"] == row["structure_sha256"] and not load(meta)["geometry_audit"]["failures"]
        pose = read_poscar(source)
        k = composition_key(pose)
        fe = canonical_iron(pose, mp["clean_frac"])
        minprot = min((distance_metrics(pose, v, fe)["minimum_ads_pose_RMSD_A"] for _, v in protected[k]), default=float("inf"))
        if minprot <= 0.2:
            rejection["protected near"] += 1
            continue
        minold = min((distance_metrics(pose, v, fe)["full_RMSD_A"] for _, v in known[k]), default=float("inf"))
        if minold < 0.10:
            rejection["existing labeled near"] += 1
            continue
        qualified.append((row, pose, k, fe, minold, minprot))
    print(
        "qualified individual",
        len(qualified),
        "identities per group",
        Counter(x[0]["composition"] for x in qualified),
        "reject",
        rejection,
        flush=True,
    )
    planned = defaultdict(list)
    seen = set()
    selected = []
    for row, pose, k, fe, old, prot in qualified:
        signature_key = signature(row)
        if signature_key in seen:
            rejection["same environment already represented"] += 1
            continue
        match = min((distance_metrics(pose, v, fe)["full_RMSD_A"] for v in planned[k]), default=float("inf"))
        if match < 0.10:
            rejection["near another selected point"] += 1
            continue
        seen.add(signature_key)
        planned[k].append(packed_pose(pose, ops, mp))
        selected.append(
            (
                row["sample_id"],
                row["composition"],
                row["adsorbate_component_count"],
                row["bond_counts"],
                round(old, 3),
                round(prot, 3),
                ranks.get(row["sample_id"]),
            )
        )
    budget = {"C2H3": 48, "C2H2O": 48, "C2HO": 72, "C3H2O": 72}
    print(
        "selected",
        len(selected),
        Counter(x[1] for x in selected),
        "core hours nominal",
        sum(budget[x[1]] for x in selected),
        "reject",
        rejection,
        "selected single-component C3",
        sum(x[1] == "C3H2O" and x[2] == 1 for x in selected),
    )

    assert {x[0] for x in selected} == EXPECTED_IDS
    planned_rows = []
    for sid, composition, components, bonds, d_old, d_protected, rank in selected:
        x = idx[sid]
        planned_rows.append(
            {
                "id": sid,
                "composition": composition,
                "source": x["structure_path"],
                "source_sha256": x["structure_sha256"],
                "source_metadata": x["frame_metadata_path"],
                "source_metadata_sha256": x["frame_metadata_sha256"],
                "case_type": "REICO_EXISTING_SAMPLED_FIXED_GEOMETRY",
                "chemical_groups": components,
                "bond_counts": bonds,
                "Fe_contacts": x["coordination_by_element"],
                "joint_signatures": x["joint_by_scale"],
                "nearest_known_rmsd_A": d_old,
                "nearest_protected_adsorbate_rmsd_A": d_protected,
                "compatible_same_coordinate_label": False,
                "why": "Three contact cutoffs show a missing bonding/Fe-coordination combination in 545.",
            }
        )
    strict = defaultdict(list)
    for r in frozen545["splits"]["train"]:
        add(strict, r["sample_id"], mroot / r["structure_path"], r)
    for r in side:
        if (
            r.get("coordinate_force_match")
            and r.get("raw_positive_Fe_local_moments")
            and r.get("normal_completion")
            and r.get("electronic_raw_pass")
            and (r.get("compatibility") or {}).get("active_PBE_Fe45_sigma0p20_branch_observed")
        ):
            add(strict, r["sample_id"], Path(r["structure_path"]), r)
    reused = []
    for r in path["path_labels"]:
        if r["qualification"] == "FORCE_REUSE_REVIEW_CANDIDATE_NO_NEW_DFT":
            p = Path(r["coordinate_source"])
            assert sha(p) == r["coordinate_file_sha256"]
            add(strict, r["id"], p)
            reused.append(r["id"])
    extra = []
    path_deferrals = {}
    for r in path["path_labels"]:
        name = r["id"]
        # Internal frames on the actual C–C approach and H migration paths only;
        # structures/forces already bound as validation and unreviewed path seeds stay out.
        if not (name.startswith("job9994246_") or (name.startswith("9796856_image") and name[-2:] in {"01", "02", "03", "04", "05"})):
            continue
        g = r["geometry"]
        if (
            r["local_moment_tables"] != 0
            or not r["coordinate_check"]
            or not r["method_and_potcar_pass"]
            or not r["EDIFF_pass_before_NELM"]
            or not g["bottom18_only_fixed"]
            or not g["same_clean_cell_within1e-6A"]
            or g["pair_guard_failures"]
        ):
            path_deferrals[name] = "source or geometry gate"
            continue
        p = Path(r["coordinate_source"])
        outcar = Path(r["OUTCAR"])
        assert sha(p) == r["coordinate_file_sha256"] and sha(outcar) == r["OUTCAR_sha256"]
        pose = read_poscar(p)
        k = composition_key(pose)
        fe = canonical_iron(pose, mp["clean_frac"])
        pr = min((distance_metrics(pose, v, fe)["minimum_ads_pose_RMSD_A"] for _, v in protected[k]), default=float("inf"))
        old = min((distance_metrics(pose, v, fe)["full_RMSD_A"] for _, v in strict[k]), default=float("inf"))
        nearest = min((distance_metrics(pose, v, fe)["full_RMSD_A"] for v in planned[k]), default=float("inf"))
        if pr <= 0.20 or min(old, nearest) < 0.10:
            path_deferrals[name] = {"protected": pr, "compatible_label": old, "planned": nearest}
            continue
        composition = "C2HO" if name.startswith("job9994246_") else "C2H2O"
        path_name = "CH+CO C–C approach" if name.startswith("job9994246_") else "INT06→MID surface H migration"
        extra.append(
            {
                "id": name,
                "composition": composition,
                "source": str(p),
                "source_sha256": sha(p),
                "source_outcar": str(outcar),
                "source_outcar_sha256": r["OUTCAR_sha256"],
                "old_label_status": r["qualification"],
                "original_force_reusable_for_diagnostics": True,
                "compatible_same_coordinate_label": False,
                "case_type": "EXISTING_PATH_GEOMETRY_NEEDS_TRAINING_GRADE_MAGNETIC_LABEL",
                "chemical_groups": g["graph"]["adsorbate_components"],
                "bond_counts": g["environment"]["bond_counts"],
                "Fe_contacts": g["environment"]["coordination_by_element"],
                "joint_signatures": r["joint_by_scale"],
                "nearest_known_rmsd_A": old,
                "nearest_protected_adsorbate_rmsd_A": pr,
                "observed_pair_1based": r["observed_pair_1based"],
                "observed_pair_distance_A": r["observed_pair_distance_A"],
                "why": path_name + "; same-coordinate force exists without local Fe moments, no compatible nearby force label.",
            }
        )
        planned[k].append(packed_pose(pose, ops, mp))
    models = BASE / "force536_545_comparison_20261119_v1"
    metrics = load(models / "comparison_summary.json")
    pair = {}
    for arm in ("control536", "increment545"):
        p = models / arm / "candidate.pt"
        assert sha(p) == metrics["arms"][arm]["candidate_sha256"]
        pair[arm] = {"path": str(p), "sha256": sha(p)}
    locked = {
        "common_start_11B": {"path": str(c2_start), "sha256": sha(c2_start), "reference_job": "9927794"},
        "common_start_complete_C3_05_cfg2": {"path": str(c3_start), "sha256": sha(c3_start), "reference_job": None},
        "models": pair,
        "fixed_Fe_count": 18,
        "DFT_force_target_eV_A": 0.02,
        "complete_C3_DFT_relaxation": "SEPARATE_NOT_SUBMITTED_NO_COMPATIBLE_INTACT_CONVERGED_REFERENCE",
        "ML_or_DFT_optimization_authorized": False,
    }
    assert locked["common_start_11B"]["sha256"] == "47bb81fa660493b965bd9ef8545a28538de71faaed7b0c831d29637f2f0d1e82"
    assert locked["common_start_complete_C3_05_cfg2"]["sha256"] == "6ed0169ab43c93e3b53092ea2bc76a5179f833752e9f1ccb0eabc61b76a63868"
    RUN.mkdir(exist_ok=False)
    write_json_exclusive(RUN / "locked_optimization_starts.json", locked)
    write_json_exclusive(
        RUN / "point_selection.json",
        {
            "samples": planned_rows + extra,
            "reuse_existing_path_statics": reused,
            "other_historical_path_forces_retained_as_diagnostics": True,
            "path_deferrals": path_deferrals,
            "bound_sources": source_file_manifest(
                [
                    Path(__file__),
                    c2_start,
                    c3_start,
                    models / "comparison_summary.json",
                    base / "joint_priority.json",
                    BASE / "joint_coverage_20261023_v3/pool_environments.json",
                    BASE / "c2_c3_path_label_audit_20261118_v1/reviewed_v2/path_audit.json",
                ]
            ),
            "optimization_submission_enabled": False,
        },
    )
    print("selected REICO", len(planned_rows), "new path statics", len(extra), "reusing", len(reused))
    for r in extra:
        print(r["id"], r["observed_pair_distance_A"], r["composition"], r["why"])
    print("path rejected", list(path_deferrals))


if __name__ == "__main__":
    main()
