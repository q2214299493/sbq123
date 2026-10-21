"""Deduplicate reclassified endpoints without accepting results or deleting data."""
from pathlib import Path

from archive.fe110_c2_dedup_20261021.review import CLEAN, DEST, POLICY
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def main():
    source_path = DEST / "review.json"
    evidence = load_json_object(source_path)
    if (evidence["policy_sha256"] != sha256_file(POLICY)
            or evidence["clean_sha256"] != sha256_file(CLEAN)):
        raise ValueError("review references changed")
    rows = evidence["rows"]
    for row in rows:
        binding = row["source"]
        if (sha256_file(Path(binding["path"])) != binding["sha256"]
                or sha256_file(Path(row["directory"]) / "CONTCAR") != binding["final_structure_sha256"]):
            raise ValueError("review source changed:" + row["name"])
    slab = read_poscar(CLEAN)
    operations = surface_pose_symmetries(slab)
    reps, comparisons, duplicates = [], [], {}
    for row in sorted(rows, key=lambda r: (r["toten_eV"], r["name"])):
        if not row["eligible_reclassified_review"]:
            continue
        for prior in reps:
            # Exact final graph, not a shared null molecular signature.
            if (row["formula"] != prior["formula"]
                    or row["final_edges_0based"] != prior["final_edges_0based"]):
                continue
            metrics = surface_equivalence(
                read_poscar(Path(prior["directory"]) / "CONTCAR"),
                read_poscar(Path(row["directory"]) / "CONTCAR"), slab, operations,
            )
            de = abs(row["toten_eV"] - prior["toten_eV"])
            duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= .20 and de <= .05
            comparisons.append({"first": prior["name"], "second": row["name"],
                                **metrics, "dE_eV": de, "duplicate": duplicate})
            if duplicate:
                duplicates[row["name"]] = prior["name"]
                break
        if row["name"] not in duplicates:
            reps.append(row)
    by_species = {}
    for row in rows:
        if row["cohort"] == "original15" and row["eligible_target"]:
            by_species.setdefault(row["species_id"], []).append(row["name"])
    summary = {
        "review_sha256": sha256_file(source_path), "source_sha256": sha256_file(Path(__file__)),
        "policy_sha256": sha256_file(POLICY), "clean_sha256": sha256_file(CLEAN),
        "original15_target_candidates_by_species": by_species,
        "target_representatives_including_paired06C": evidence["representatives"],
        "target_unique_count": len(evidence["representatives"]),
        "reclassified_representatives": [r["name"] for r in reps],
        "reclassified_unique_count": len(reps), "reclassified_duplicate_of": duplicates,
        "reclassified_comparisons": comparisons,
        "not_qualified": [r["name"] for r in rows if not r["eligible_target"] and not r["eligible_reclassified_review"]],
        "combined_converged_structural_candidates": len(reps) + len(evidence["representatives"]),
        "borderline_retained": [{"first": "08_B", "second": "08_C",
                                 "reason": "Near duplicate; RMSD0.233A/dE0.007eV. Retain pending basin review; not proof of distinct minima."}],
        "limitations": ["Fixed reviewed C roles; genuine clean-slab symmetries and interchangeable H only.",
                        "No vibrational minimum/global-minimum proof; no new scheduler evidence inferred from OUTCAR termination.",
                        "Converged structures are review candidates, not automatic scientific/energy acceptance."],
        "registry_written": False, "files_deleted": False, "new_scientific_jobs": 0,
    }
    write_json_exclusive(DEST / "dedup_summary.json", summary)
    print("TARGET", summary["target_unique_count"], "RECLASSIFIED", len(reps),
          "COMBINED", summary["combined_converged_structural_candidates"])
    print("RECLASSIFIED_COMPARISONS", comparisons)
    print("RECLASSIFIED_DUPLICATES", duplicates)


if __name__ == "__main__":
    main()
