"""Compare reviewed final geometries against accepted registry states only."""
from dataclasses import replace
from pathlib import Path
import json

import networkx as nx
import yaml

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.registry_connection import open_registry
from .collect import OUT, ROOT


def graph(pose):
    symbols = expanded_symbols(pose)
    ads = list(range(45, len(symbols)))
    result = nx.Graph()
    result.add_nodes_from((i, {"element": symbols[i]}) for i in ads)
    result.add_edges_from((ads[a], ads[b]) for a, b in connectivity(pose, ads))
    return result


def compare(first, second, slab, operations):
    matcher = nx.algorithms.isomorphism.GraphMatcher(graph(first), graph(second),
                 node_match=nx.algorithms.isomorphism.categorical_node_match("element", ""))
    seen, matches = set(), []
    symbols = expanded_symbols(first)
    for mapping in matcher.isomorphisms_iter():
        heavy = tuple(mapping[i] for i in range(45, len(symbols)) if symbols[i] != "H")
        if heavy in seen:
            continue
        seen.add(heavy)
        order = list(range(45)) + [mapping[i] for i in range(45, len(symbols))]
        mapped = replace(second, symbols=first.symbols, counts=first.counts,
                         frac=second.frac[order], flags=[second.flags[i] for i in order])
        metrics = surface_equivalence(first, mapped, slab, operations)
        matches.append({**metrics, "second_indices_in_first_order": order})
    return min(matches, key=lambda r: max(r["adsorbate_RMSD_A"],r["slab_RMSD_A"])) if matches else None


def main():
    target = OUT / "duplicate_review_v2.json"
    if target.exists():
        raise SystemExit("Duplicate evidence exists; inspect it instead of replacing.")
    analysis = load_json_object(OUT / "completion_geometry_review.json")
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())["duplicate_detection"]
    slab_file = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    slab = read_poscar(slab_file)
    operations = surface_pose_symmetries(slab)
    old = []
    with open_registry(ROOT / "data/project_registry.sqlite3") as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT c.calculation_id,r.result_id,r.numeric_value,f.local_path FROM calculations c "
                          "JOIN results r USING(calculation_id) JOIN files f ON f.file_id=r.source_file_id "
                          "WHERE c.module='adsorption_workflow' "
                          "AND c.workflow_status NOT IN ('rejected','failed','duplicate','needs_review','cancelled') "
                          "AND lower(r.result_name)='final_toten' AND r.validation_status='accepted_compatible_final_energy' "
                          "AND r.reference_convention='fe110_converged_toten_sigma0p20_v1'").fetchall()
        for row in rows:
            source = Path(row["local_path"]).parent / "CONTCAR" if row["local_path"] else None
            if source is None or not source.exists():
                continue
            registered = db.execute("SELECT sha256 FROM files WHERE calculation_id=? AND filename='CONTCAR' AND local_path=?",
                                    (row["calculation_id"],str(source))).fetchone()
            if registered is None:
                continue
            pose = read_poscar(source)
            if len(pose.frac) < 48 or expanded_symbols(pose).count("C") != 2:
                continue
            if sha256_file(source) != registered[0]:
                raise ValueError("Accepted structure changed: " + str(source))
            old.append({"name": row["calculation_id"], "calculation_id": row["calculation_id"],
                        "result_id": row["result_id"], "energy": row["numeric_value"],
                        "structure": str(source), "pose": pose, "existing_accepted": True})
    comparisons, decisions = [], []
    pool = list(old)
    for row in sorted(analysis["records"], key=lambda r:r["TOTEN_eV"]):
        if not row["eligible_for_scientific_review"]:
            decisions.append({"name":row["name"],"decision":"not_eligible","blockers":row["blockers"]})
            continue
        current = read_poscar(Path(row["directory"]) / "CONTCAR")
        duplicate = None
        for prior in sorted(pool,key=lambda r:r["energy"]):
            metrics = compare(current,prior["pose"],slab,operations)
            if metrics is None:
                continue
            de = abs(row["TOTEN_eV"]-prior["energy"])
            matched = max(metrics["adsorbate_RMSD_A"],metrics["slab_RMSD_A"]) <= rules["geometry_rmsd_tolerance_angstrom"] and de <= rules["energy_tolerance_ev"]
            comparisons.append({"name":row["name"],"reference":prior["name"],"reference_existing_accepted":prior["existing_accepted"],
                                "energy_difference_eV":de,"duplicate":matched,**metrics})
            if matched:
                duplicate = prior["name"]
                break
        decisions.append({"name":row["name"],"decision":"duplicate" if duplicate else "unique_candidate", "duplicate_of":duplicate})
        if duplicate is None:
            pool.append({"name":row["name"],"energy":row["TOTEN_eV"],"pose":current,"existing_accepted":False})
    write_json_exclusive(target,{"status":"NUMERIC_SURFACE_SYMMETRY_AND_CHEMICAL_MAPPING_REVIEW", "thresholds":rules,
        "existing_accepted_C2_references":len(old),"decisions":decisions,"comparisons":comparisons,
        "source_files":source_file_manifest([OUT/"completion_geometry_review.json",slab_file,Path(__file__)]+[Path(r['structure']) for r in old])})
    print(json.dumps({"thresholds":rules,"references":len(old),"decisions":decisions},ensure_ascii=False))


if __name__ == "__main__":
    main()
